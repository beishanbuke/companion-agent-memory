"""Current-turn emotion detection with compact conversational context.

Emotion model: 8 primary labels + None, with optional mixed-emotion
support (primary + secondary). Detection is two-tier:
- rule-based keyword scoring (instant, deterministic, offline-safe)
- LLM judge refinement (evidence-first, few-shot, low temperature),
  falling back to the rule result on any failure.

The LLM never invents labels: output is validated against the allowed
set and numeric fields are bounded before use.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from urllib import request


EMOTION_NONE = "None"
EMOTION_HAPPY = "开心"
EMOTION_SAD = "难过"
EMOTION_ANXIOUS = "焦虑"
EMOTION_ANGRY = "愤怒"
EMOTION_TIRED = "疲惫"
EMOTION_LONELY = "孤独"
EMOTION_CALM = "平静"
EMOTION_EXPECTANT = "期待"

# Display/priority order, also used to break score ties deterministically.
PRIMARY_LABELS = (
    EMOTION_HAPPY,
    EMOTION_EXPECTANT,
    EMOTION_SAD,
    EMOTION_ANXIOUS,
    EMOTION_ANGRY,
    EMOTION_TIRED,
    EMOTION_LONELY,
    EMOTION_CALM,
)

LABEL_VALENCE: dict[str, str] = {
    EMOTION_HAPPY: "positive",
    EMOTION_EXPECTANT: "positive",
    EMOTION_SAD: "negative",
    EMOTION_ANXIOUS: "negative",
    EMOTION_ANGRY: "negative",
    EMOTION_TIRED: "negative",
    EMOTION_LONELY: "negative",
    EMOTION_CALM: "neutral",
}

POSITIVE_LABELS = {EMOTION_HAPPY, EMOTION_EXPECTANT}
NEGATIVE_LABELS = {EMOTION_SAD, EMOTION_ANXIOUS, EMOTION_ANGRY, EMOTION_TIRED, EMOTION_LONELY}
NEUTRAL_LABELS = {EMOTION_CALM}

# Per-label response guidance injected into the chat prompt. This is the
# cheap, explicit version of an emotion-conditioned response policy.
LABEL_RESPONSE_GUIDANCE: dict[str, str] = {
    EMOTION_HAPPY: "先一起放大这份开心，多问一句细节。",
    EMOTION_EXPECTANT: "陪用户一起期待，可以顺势帮TA把期待落成小计划。",
    EMOTION_SAD: "先接住情绪、表达陪伴，不要急着给解决方案。",
    EMOTION_ANXIOUS: "先安抚，再给1-2个具体、马上能做的小步骤。",
    EMOTION_ANGRY: "认可TA的感受，不评判对错，不急着讲道理。",
    EMOTION_TIRED: "降低要求，温柔地建议休息，语速放慢。",
    EMOTION_LONELY: "强调陪伴感，表达「我在」。",
    EMOTION_CALM: "按正常节奏交流即可。",
}

VALENCE_ORDER = {"negative": 0, "neutral": 1, "positive": 2}


@dataclass(frozen=True)
class EmotionDetection:
    label: str
    intensity: float
    confidence: float
    reason: str
    signals: list[str]
    trend: str = "新出现"
    context_turns: int = 0
    secondary_label: str = EMOTION_NONE
    secondary_intensity: float = 0.0

    @property
    def valence(self) -> str:
        return LABEL_VALENCE.get(self.label, "neutral")


class CurrentEmotionDetector:
    """Classify the latest user turn while using a bounded conversation window."""

    ALLOWED_LABELS = {EMOTION_NONE, *PRIMARY_LABELS}
    CONTEXT_TURNS = 6

    HAPPY_TERMS = (
        "开心", "高兴", "快乐", "兴奋", "舒服", "爽", "太好了", "好棒",
        "满意", "顺利", "喜欢", "幸福", "开心死", "棒棒", "赞", "太好",
        "happy", "excited", "glad", "joy", "joyful", "great", "awesome",
        "amazing", "wonderful", "delighted", "cheerful", "thrilled", "pleased",
        "love", "fun", "cool", "nice", "good", "fantastic",
    )
    EXPECTANT_TERMS = (
        "期待", "期盼", "憧憬", "盼望", "等不及", "跃跃欲试", "想快点",
        "迫不及待", "快了", "就快",
        "looking forward", "can't wait", "cannot wait", "hopeful", "eager",
        "anticipat",
    )
    SAD_TERMS = (
        "难过", "伤心", "低落", "沮丧", "崩溃", "想哭", "哭了", "委屈", "失落",
        "不开心", "糟糕", "难受", "心痛", "心碎", "遗憾", "郁闷", "丧",
        "sad", "unhappy", "upset", "depressed", "down", "cry", "crying",
        "heartbroken", "miserable",
    )
    ANXIOUS_TERMS = (
        "焦虑", "紧张", "担心", "害怕", "不安", "慌", "恐惧", "压力", "紧绷",
        "心慌", "忐忑", "没底", "发怵", "发慌", "慌", "怕",
        "anxious", "worried", "nervous", "stressed", "afraid", "scared",
        "panic", "terrified", "uneasy", "anxiety", "stress",
    )
    ANGRY_TERMS = (
        "生气", "愤怒", "气死", "气人", "火大", "恼火", "暴躁", "不爽",
        "烦人", "讨厌", "烦死了", "烦透", "凭什么", "太过分", "可恶",
        "气不打一处来",
        "angry", "mad", "furious", "annoyed", "irritated", "pissed",
        "rage", "outraged",
    )
    TIRED_TERMS = (
        "累", "疲惫", "疲倦", "困", "撑不住", "没力气", "精疲力尽",
        "耗尽", "掏空", "提不起劲", "没精神", "好累",
        "tired", "exhausted", "sleepy", "drained", "fatigue", "weary",
        "burned out", "burnout",
    )
    LONELY_TERMS = (
        "孤独", "寂寞", "孤单", "没人陪", "孤立", "没人懂", "无助",
        "被冷落", "空虚", "一个人",
        "lonely", "alone", "isolated", "empty inside",
    )
    CALM_TERMS = (
        "平静", "淡定", "坦然", "放松", "心平气和", "还好", "挺好",
        "没什么", "无所谓",
        "calm", "relaxed", "peaceful", "at ease",
    )

    LABEL_TERMS: dict[str, tuple[str, ...]] = {
        EMOTION_HAPPY: HAPPY_TERMS,
        EMOTION_EXPECTANT: EXPECTANT_TERMS,
        EMOTION_SAD: SAD_TERMS,
        EMOTION_ANXIOUS: ANXIOUS_TERMS,
        EMOTION_ANGRY: ANGRY_TERMS,
        EMOTION_TIRED: TIRED_TERMS,
        EMOTION_LONELY: LONELY_TERMS,
        EMOTION_CALM: CALM_TERMS,
    }

    NEGATORS = ("不", "没", "没有", "不是", "别", "not", "no")

    def detect(
        self,
        message: str,
        conversation_history: list[dict[str, str]] | None = None,
        recent_emotional_state: str = "",
        llm_timeout: float | None = None,
        behavioral_signals: dict | None = None,
    ) -> EmotionDetection:
        """Rule-first detection refined by an LLM judge.

        llm_timeout overrides EMOTION_LLM_TIMEOUT for this call so the
        critical path can attempt a fast LLM pass (e.g. ~1.2s) while a
        later background pass may use the default, longer timeout.
        """
        context = self._compact_history(conversation_history or [])
        fallback = self.detect_by_rule(message)
        trend = self._infer_trend(fallback.label, context, recent_emotional_state)
        try:
            judged = self._judge_with_llm(
                message,
                context,
                recent_emotional_state,
                timeout=llm_timeout,
                behavioral_signals=behavioral_signals,
            )
            return self._detection_from_judge(judged, fallback, trend, len(context))
        except Exception:
            return EmotionDetection(
                label=fallback.label,
                intensity=fallback.intensity,
                confidence=fallback.confidence,
                reason=f"{fallback.reason};llm_judge_failed",
                signals=[*fallback.signals, "llm_judge_failed"],
                trend=trend,
                context_turns=len(context),
                secondary_label=fallback.secondary_label,
                secondary_intensity=fallback.secondary_intensity,
            )

    def detect_rule(
        self,
        message: str,
        conversation_history: list[dict[str, str]] | None = None,
        recent_emotional_state: str = "",
    ) -> EmotionDetection:
        """纯规则情绪检测（毫秒级，供关键路径 prompt/MCP 使用）。

        与 detect() 共享规则兜底与趋势推断；需要 LLM 精修时请用 detect()。
        """
        context = self._compact_history(conversation_history or [])
        fallback = self.detect_by_rule(message)
        trend = self._infer_trend(fallback.label, context, recent_emotional_state)
        return EmotionDetection(
            label=fallback.label,
            intensity=fallback.intensity,
            confidence=fallback.confidence,
            reason=f"{fallback.reason};rule_first",
            signals=[*fallback.signals, "rule_first"],
            trend=trend,
            context_turns=len(context),
            secondary_label=fallback.secondary_label,
            secondary_intensity=fallback.secondary_intensity,
        )

    def detect_by_rule(self, message: str) -> EmotionDetection:
        """Score every label's keyword set; primary + optional secondary."""
        text = (message or "").strip()
        lowered = text.lower()

        per_label: dict[str, tuple[int, list[str]]] = {}
        for label, terms in self.LABEL_TERMS.items():
            per_label[label] = self._score(lowered, terms)

        # 固定搭配修正：明确否定词指向"难过"
        if "不开心" in lowered or "不高兴" in lowered:
            score, hits = per_label[EMOTION_SAD]
            per_label[EMOTION_SAD] = (score + 2, [*hits, "不开心"])
        # 英文否定（"not happy" 应判为负面情绪，反之亦然）
        if "not happy" in lowered or "not good" in lowered or "not excited" in lowered:
            score, hits = per_label[EMOTION_SAD]
            per_label[EMOTION_SAD] = (score + 2, [*hits, "not happy"])
        if "not sad" in lowered or "not bad" in lowered or "not upset" in lowered:
            score, hits = per_label[EMOTION_HAPPY]
            per_label[EMOTION_HAPPY] = (score + 2, [*hits, "not sad"])

        ranked = sorted(
            ((label, score, hits) for label, (score, hits) in per_label.items() if score > 0),
            key=lambda item: (-item[1], PRIMARY_LABELS.index(item[0])),
        )
        if not ranked:
            return EmotionDetection(
                label=EMOTION_NONE,
                intensity=0.0,
                confidence=0.45,
                reason="no_emotion_signal",
                signals=[],
            )

        top_label, top_score, top_hits = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else 0
        secondary_label = EMOTION_NONE
        secondary_intensity = 0.0
        if len(ranked) > 1 and ranked[1][1] >= max(2, 0.4 * top_score):
            secondary_label = ranked[1][0]
            secondary_intensity = self._intensity(ranked[1][1])

        return EmotionDetection(
            label=top_label,
            intensity=self._intensity(top_score),
            confidence=self._confidence(top_score, second_score),
            reason=f"{top_label}_signal_detected",
            signals=sorted(set(top_hits)),
            secondary_label=secondary_label,
            secondary_intensity=secondary_intensity,
        )

    def _judge_with_llm(
        self,
        message: str,
        context: list[dict[str, str]],
        recent_emotional_state: str,
        timeout: float | None = None,
        behavioral_signals: dict | None = None,
    ) -> dict[str, object]:
        api_key, endpoint, model = self._api_config()
        if not api_key:
            raise RuntimeError("missing_emotion_llm_api_key")
        judge_timeout = timeout if timeout is not None else float(
            os.getenv("EMOTION_LLM_TIMEOUT", "3.5")
        )
        user_payload: dict[str, object] = {
            "recent_dialogue": context,
            "previous_memory_signal": recent_emotional_state or None,
            "user_message": message,
        }
        if behavioral_signals:
            user_payload["behavioral_signals"] = behavioral_signals
        payload = {
            "model": model,
            # 分类任务必须低温：温度过高会给标签引入随机翻转
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "chat_template_kwargs": {"enable_thinking": False},
            "messages": [
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            endpoint,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        with request.urlopen(req, timeout=judge_timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        return self._parse_json(content)

    def _api_config(self) -> tuple[str, str, str]:
        api_key = (
            os.getenv("EMOTION_LLM_API_KEY")
            or os.getenv("CHAT_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("MEMORY_LLM_API_KEY")
            or ""
        ).strip()
        endpoint = (
            os.getenv("EMOTION_LLM_URL")
            or os.getenv("CHAT_API_URL")
            or os.getenv("MEMORY_LLM_URL")
            or ""
        ).strip()
        if not endpoint:
            base_url = (os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
            endpoint = f"{base_url}/chat/completions"
        if endpoint.endswith("/chat/completion"):
            endpoint = endpoint + "s"
        elif not endpoint.endswith("/chat/completions"):
            endpoint = endpoint.rstrip("/") + "/chat/completions"
        model = (
            os.getenv("EMOTION_LLM_MODEL")
            or os.getenv("CHAT_API_MODEL")
            or os.getenv("MEMORY_LLM_MODEL")
            or os.getenv("OPENAI_MODEL")
            or "gpt-4o-mini"
        ).strip()
        return api_key, endpoint, model

    def _system_prompt(self) -> str:
        labels = "、".join([EMOTION_NONE, *PRIMARY_LABELS])
        return (
            "You are an emotion judge for a companion AI. Classify the user's current turn.\n"
            f"Allowed label values are exactly: {labels}.\n"
            "Rules:\n"
            "1. Evidence first: quote what the user actually expressed. Distinguish literal "
            "wording from the true feeling — sarcasm and denial (\"我没事\") often hide the real emotion.\n"
            "2. Use recent_dialogue only to resolve context and trend; never let an old emotion "
            "override a clearly different current turn.\n"
            "3. Mixed emotions: when two genuine emotions coexist, keep the dominant one as label "
            "and put the other in secondary_label with secondary_intensity (0-1).\n"
            "4. Label \"None\" only when there is no genuine emotion signal.\n"
            "5. behavioral_signals are aggregate messaging-pattern statistics; treat them as weak hints only.\n"
            "6. trend must be one of: 新出现, 持续, 加重, 缓解中, 趋于平稳, 波动.\n"
            "7. intensity/confidence are numbers 0-1. signals must be short quotes from the current turn or dialogue.\n\n"
            "Examples:\n"
            '{"user":"呵呵，真不错，精心准备的汇报又被打回了","label":"难过","secondary_label":"愤怒",'
            '"secondary_intensity":0.5,"reason":"反讽：呵呵/真不错与负面事实相反，真实情绪是挫败",'
            '"signals":["呵呵","真不错","又被打回"],"trend":"新出现"}\n'
            '{"user":"没事，就是最近睡不着","label":"焦虑","secondary_label":"疲惫","secondary_intensity":0.4,'
            '"reason":"否认没事加失眠线索指向担忧而非平静","signals":["没事","睡不着"],"trend":"新出现"}\n'
            '{"user":"考上好开心！但马上要离开朋友们了","label":"开心","secondary_label":"难过","secondary_intensity":0.45,'
            '"reason":"主情绪是喜悦，夹杂离别不舍","signals":["考上","开心","离开"],"trend":"新出现"}\n'
            "Return JSON only with keys: label, intensity, confidence, reason, signals, trend, "
            "secondary_label, secondary_intensity."
        )

    def _parse_json(self, content: str) -> dict[str, object]:
        if not content:
            raise ValueError("empty_emotion_judge_response")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", content, re.S)
            if not match:
                raise
            parsed = json.loads(match.group(0))
        if not isinstance(parsed, dict):
            raise ValueError("emotion_judge_response_not_object")
        return parsed

    def _detection_from_judge(
        self,
        judged: dict[str, object],
        fallback: EmotionDetection,
        fallback_trend: str,
        context_turns: int,
    ) -> EmotionDetection:
        label = str(judged.get("label") or EMOTION_NONE).strip()
        if label not in self.ALLOWED_LABELS:
            return EmotionDetection(
                label=fallback.label,
                intensity=fallback.intensity,
                confidence=fallback.confidence,
                reason=f"{fallback.reason};invalid_llm_label",
                signals=[*fallback.signals, "invalid_llm_label"],
                trend=fallback_trend,
                context_turns=context_turns,
                secondary_label=fallback.secondary_label,
                secondary_intensity=fallback.secondary_intensity,
            )
        secondary = str(judged.get("secondary_label") or EMOTION_NONE).strip()
        if secondary not in self.ALLOWED_LABELS or secondary == label:
            secondary = EMOTION_NONE
        intensity = self._bounded_number(judged.get("intensity"), fallback.intensity)
        raw_confidence = judged.get("confidence", fallback.confidence)
        try:
            confidence = float(raw_confidence)
        except (TypeError, ValueError):
            confidence = fallback.confidence
        confidence = round(max(0.0, min(1.0, confidence)), 2)
        reason = str(judged.get("reason") or "llm_judge").strip()
        raw_signals = judged.get("signals", [])
        signals = [str(item) for item in raw_signals if str(item).strip()] if isinstance(raw_signals, list) else []
        trend = str(judged.get("trend") or fallback_trend).strip()
        if trend not in {"新出现", "持续", "加重", "缓解中", "趋于平稳", "波动"}:
            trend = fallback_trend
        return EmotionDetection(
            label=label,
            intensity=intensity,
            confidence=confidence,
            reason=f"{reason};llm_judge",
            signals=[*signals, "llm_judge"],
            trend=trend,
            context_turns=context_turns,
            secondary_label=secondary,
            secondary_intensity=self._bounded_number(
                judged.get("secondary_intensity"), 0.0
            ) if secondary != EMOTION_NONE else 0.0,
        )

    def _compact_history(self, history: list[dict[str, str]]) -> list[dict[str, str]]:
        compact: list[dict[str, str]] = []
        for item in history[-self.CONTEXT_TURNS:]:
            role = str(item.get("role") or "").strip().lower()
            content = str(item.get("content") or "").strip()
            if role in {"user", "assistant"} and content:
                compact.append({"role": role, "content": content[:500]})
        return compact

    def _infer_trend(self, label: str, context: list[dict[str, str]], memory_signal: str) -> str:
        """Valence-based trend: exact match = 持续, valence change = 缓解中/加重,
        same-valence relabel (e.g. 焦虑→疲惫) counts as 持续 distress."""
        prior_labels = [self.detect_by_rule(item["content"]).label for item in context if item["role"] == "user"]
        prior = next((candidate for candidate in reversed(prior_labels) if candidate != EMOTION_NONE), "")
        if not prior and memory_signal == "negative":
            prior = EMOTION_SAD
        elif not prior and memory_signal == "positive":
            prior = EMOTION_HAPPY
        if not prior:
            return "新出现"
        if label == EMOTION_NONE:
            return "趋于平稳"
        if label == prior:
            return "持续"
        label_valence = LABEL_VALENCE.get(label, "neutral")
        prior_valence = LABEL_VALENCE.get(prior, "neutral")
        if label_valence == prior_valence:
            return "持续"
        if VALENCE_ORDER[label_valence] > VALENCE_ORDER[prior_valence]:
            return "缓解中"
        return "加重"

    @staticmethod
    def _bounded_number(value: object, default: float) -> float:
        try:
            return round(max(0.0, min(1.0, float(value))), 2)
        except (TypeError, ValueError):
            return default

    def _score(self, text: str, terms: tuple[str, ...]) -> tuple[int, list[str]]:
        score = 0
        hits: list[str] = []
        for term in terms:
            start = text.find(term)
            if start < 0:
                continue
            if self._is_negated(text, start):
                continue
            score += 2 if len(term) >= 2 else 1
            hits.append(term)
        return score, hits

    def _is_negated(self, text: str, start: int) -> bool:
        prefix = text[max(0, start - 4):start].rstrip()
        if prefix.endswith("特别"):
            return False
        return any(prefix.endswith(negator) for negator in self.NEGATORS)

    def _confidence(self, winning_score: int, other_score: int) -> float:
        margin = max(0, winning_score - other_score)
        confidence = 0.58 + min(0.32, margin * 0.08 + winning_score * 0.04)
        return round(min(0.9, confidence), 2)

    @staticmethod
    def _intensity(score: int) -> float:
        return round(min(0.9, 0.35 + score * 0.12), 2)


# Backwards-compatible aliases (older imports/tests)
EMOTION_POSITIVE = EMOTION_HAPPY
EMOTION_NEGATIVE = EMOTION_SAD
