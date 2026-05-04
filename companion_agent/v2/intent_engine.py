"""
Intent Engine v2

使用统一 LLM Runtime 进行 nuanced 意图理解。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .llm_runtime import get_llm_runtime, LLMRuntime


@dataclass
class IntentAnalysis:
    """结构化意图分析结果（信号提取器版）。"""
    # 核心意图
    primary_intent: str
    intent_confidence: float
    
    # 情绪理解
    emotional_state: str
    emotional_intensity: float
    emotional_context: str
    
    # 隐式需求
    implicit_needs: list[str]
    
    # 对话节奏
    conversation_rhythm: str
    
    # 任务相关
    task_category: str
    task_urgency: float
    
    # 状态机关键信号（新增）
    action_receptivity: float = 0.5  # 0-1，用户接受行动的意愿
    topic_shift_type: str = "none"  # emotional_escape/functional_detour/new_thread/return_to_thread/none
    pressure_signal: float = 0.0  # 0-1，压力信号强度
    thread_candidates: list[str] = None  # 可能的主线候选
    clarification_confidence: float = 0.0  # 0-1，是否需要澄清的置信度
    
    # 原始分析
    raw_analysis: str = ""


def cheap_intent_fast_path(message: str) -> dict | None:
    """超轻量规则意图识别：常见寒暄/安全场景不走 LLM，降低延迟。"""
    text = message.strip().lower()

    # 极短寒暄
    if len(text) <= 3 and text in {"你好", "hi", "hello", "在吗", "哈喽", "在", "嗯", "哦"}:
        return {
            "primary_intent": "casual",
            "intent_confidence": 0.95,
            "emotional_state": "neutral",
            "emotional_intensity": 0.1,
            "emotional_context": "简短问候",
            "implicit_needs": [],
            "conversation_rhythm": "light_chat",
            "task_category": "none",
            "task_urgency": 0.0,
            "action_receptivity": 0.2,
            "topic_shift_type": "none",
            "pressure_signal": 0.0,
            "thread_candidates": [],
            "clarification_confidence": 0.0,
        }

    # 安全危机关键词
    if any(k in text for k in ["想死", "自杀", "自残", "不想活", "活不下去", "死了算了"]):
        return {
            "primary_intent": "safety",
            "intent_confidence": 1.0,
            "emotional_state": "crisis",
            "emotional_intensity": 1.0,
            "emotional_context": "用户表达了自伤或自杀意图，需要立即响应",
            "implicit_needs": ["crisis_support", "真人介入"],
            "conversation_rhythm": "serious",
            "task_category": "safety",
            "task_urgency": 1.0,
            "action_receptivity": 0.9,
            "topic_shift_type": "none",
            "pressure_signal": 1.0,
            "thread_candidates": ["危机干预"],
            "clarification_confidence": 0.0,
        }

    return None


class IntentEngine:
    """LLM-based intent understanding engine (Unified Runtime)."""
    
    def __init__(self, runtime: LLMRuntime | None = None):
        self._runtime = runtime or get_llm_runtime()
    
    async def analyze(
        self,
        user_message: str,
        conversation_history: list[dict[str, str]] | None = None,
        current_state: dict[str, Any] | None = None,
    ) -> IntentAnalysis:
        """分析用户消息的真实意图。
        
        Fast path: 常见闲聊/推荐场景直接规则匹配，不走 LLM，降低延迟。
        """
        msg = user_message.strip()
        if len(msg) <= 2:
            return self._fallback_analysis(msg)
        
        # === Ultra Fast Path: 极短寒暄/安全危机 ===
        fast = cheap_intent_fast_path(msg)
        if fast is not None:
            return IntentAnalysis(**fast)
        
        # === Fast Path: 闲聊/推荐类场景规则匹配 ===
        fast_result = self._fast_path_analysis(msg)
        if fast_result is not None:
            return fast_result
        
        # 复杂场景走 LLM
        try:
            return await self._llm_analyze(msg, conversation_history, current_state)
        except Exception:
            return self._fallback_analysis(msg)
    
    def _fallback_analysis(self, message: str) -> IntentAnalysis:
        """轻规则兜底。"""
        t = message.lower().strip()
        
        if len(t) <= 2 or t in ["哈哈", "嗯", "哦", "好吧", "行"]:
            return IntentAnalysis(
                primary_intent="companion",
                intent_confidence=0.6,
                emotional_state="neutral",
                emotional_intensity=0.3,
                emotional_context="简短回应，可能在敷衍或不知道说什么",
                implicit_needs=["需要对方接话"],
                conversation_rhythm="chill",
                task_category="none",
                task_urgency=0.0,
                action_receptivity=0.3,
                topic_shift_type="none",
                pressure_signal=0.0,
                thread_candidates=[],
                clarification_confidence=0.0,
            )
        
        if any(kw in t for kw in ["累", "困", "不想动"]):
            return IntentAnalysis(
                primary_intent="companion",
                intent_confidence=0.7,
                emotional_state="tired",
                emotional_intensity=0.6,
                emotional_context="体力或精力透支",
                implicit_needs=["被允许休息", "不被push"],
                conversation_rhythm="venting",
                task_category="none",
                task_urgency=0.0,
                action_receptivity=0.2,
                topic_shift_type="none",
                pressure_signal=0.4,
                thread_candidates=["休息", "精力管理"],
                clarification_confidence=0.0,
            )
        
        if any(kw in t for kw in ["吃什么", "饿了", "外卖", "食堂"]):
            return IntentAnalysis(
                primary_intent="advice",
                intent_confidence=0.7,
                emotional_state="neutral",
                emotional_intensity=0.3,
                emotional_context="日常饮食决策",
                implicit_needs=["省脑子", "快速决策"],
                conversation_rhythm="seeking_help",
                task_category="food",
                task_urgency=0.5,
                action_receptivity=0.7,
                topic_shift_type="none",
                pressure_signal=0.1,
                thread_candidates=["饮食", "日常安排"],
                clarification_confidence=0.0,
            )

        if any(kw in t for kw in ["复盘", "总结", "今天都干了啥", "这周", "本周", "这段时间"]):
            return IntentAnalysis(
                primary_intent="share",
                intent_confidence=0.75,
                emotional_state="neutral",
                emotional_intensity=0.4,
                emotional_context="用户想回看阶段进展并收拢信息",
                implicit_needs=["被整理", "形成连续感", "得到下一步"],
                conversation_rhythm="reviewing",
                task_category="none",
                task_urgency=0.3,
                action_receptivity=0.6,
                topic_shift_type="return_to_thread" if any(kw in t for kw in ["这周", "这段时间"]) else "none",
                pressure_signal=0.3,
                thread_candidates=["复盘", "阶段整理"],
                clarification_confidence=0.1,
            )
        
        return IntentAnalysis(
            primary_intent="companion",
            intent_confidence=0.5,
            emotional_state="neutral",
            emotional_intensity=0.3,
            emotional_context="普通对话",
            implicit_needs=["保持对话连续性"],
            conversation_rhythm="chill",
            task_category="none",
            task_urgency=0.0,
            action_receptivity=0.5,
            topic_shift_type="none",
            pressure_signal=0.0,
            thread_candidates=[],
            clarification_confidence=0.0,
        )
    
    async def _llm_analyze(
        self,
        message: str,
        history: list[dict[str, str]] | None,
        state: dict[str, Any] | None,
    ) -> IntentAnalysis:
        """使用统一 LLM Runtime 进行 nuanced 意图分析。"""
        
        history_text = ""
        if history:
            recent = history[-5:]
            history_text = "\n".join(
                f"{'用户' if msg['role'] == 'user' else 'Agent'}: {msg['content'][:80]}"
                for msg in recent
            )
        
        state_text = ""
        if state:
            state_text = json.dumps(state, ensure_ascii=False, indent=2)
        
        prompt = f"""你是一位资深的对话理解专家。请分析以下用户消息的真实意图。

【重要原则】
- 不要只看表面关键词，要理解语境和潜台词
- 区分"用户在发泄"和"用户在求助"
- 区分"用户想被逗"和"用户想安静"
- 考虑对话历史，判断这是延续还是转折
- 评估用户现在"能不能被推动做一件事"
- 检测用户是否在逃避某个话题或切换主线

【最近对话】
{history_text}

【当前对话状态】
{state_text}

【用户消息】
{message!r}

请输出 JSON（只输出 JSON，不要有其他文字）：
{{
  "primary_intent": "companion|joke|advice|execute|quiet|share|vent",
  "intent_confidence": 0.0-1.0,
  "emotional_state": "tired|anxious|sad|happy|angry|neutral|mixed|excited|lonely",
  "emotional_intensity": 0.0-1.0,
  "emotional_context": "简要说明为什么会有这种情绪",
  "implicit_needs": ["用户没说出口但可能想要的需求"],
  "conversation_rhythm": "venting|confiding|seeking_help|sharing|bantering|chill|planning|reviewing",
  "task_category": "food|study|social|campus|music|outfit|none",
  "task_urgency": 0.0-1.0,
  "action_receptivity": 0.0-1.0,
  "topic_shift_type": "emotional_escape|functional_detour|new_thread|return_to_thread|none",
  "pressure_signal": 0.0-1.0,
  "thread_candidates": ["可能的主线话题"],
  "clarification_confidence": 0.0-1.0
}}"""

        messages = [
            {"role": "system", "content": "你是一个对话意图分析专家，只输出 JSON。"},
            {"role": "user", "content": prompt},
        ]
        
        text = await self._runtime.call("intent", messages)
        
        json_start = text.find("{")
        json_end = text.rfind("}")
        if json_start >= 0 and json_end > json_start:
            try:
                data = json.loads(text[json_start:json_end + 1])
            except json.JSONDecodeError:
                data = {}
        else:
            data = {}
        
        return IntentAnalysis(
            primary_intent=data.get("primary_intent", "companion"),
            intent_confidence=float(data.get("intent_confidence", 0.5)),
            emotional_state=data.get("emotional_state", "neutral"),
            emotional_intensity=float(data.get("emotional_intensity", 0.3)),
            emotional_context=data.get("emotional_context", ""),
            implicit_needs=data.get("implicit_needs", []),
            conversation_rhythm=data.get("conversation_rhythm", "chill"),
            task_category=data.get("task_category", "none"),
            task_urgency=float(data.get("task_urgency", 0.0)),
            action_receptivity=float(data.get("action_receptivity", 0.5)),
            topic_shift_type=data.get("topic_shift_type", "none"),
            pressure_signal=float(data.get("pressure_signal", 0.0)),
            thread_candidates=data.get("thread_candidates", []),
            clarification_confidence=float(data.get("clarification_confidence", 0.0)),
            raw_analysis=text,
        )
