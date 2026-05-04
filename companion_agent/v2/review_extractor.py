"""
Review Extractor

独立复盘摘要抽取器。

输入：
- 最近几轮对话（user + assistant）
- 当前 active / background threads
- memory_context
- 当前状态

输出：
- ReviewSummary（结构化摘要）

这个模块让复盘摘要不只是"用户说了什么"，
而是"这一段对话里真正发生了什么"。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReviewSummary:
    """复盘结构化摘要（用户可见 + 系统内部）。"""
    scope: str = ""  # day / week / phase
    user_visible: str = ""  # 用户可见的口语化复盘
    structured: dict[str, Any] = field(default_factory=dict)  # 系统内部结构化数据

    def to_system_summary(self) -> dict[str, Any]:
        """转换为系统内部存储格式。"""
        return {
            "type": "review",
            "scope": self.scope,
            "timestamp": time.time() if 'time' in globals() else 0,
            **self.structured,
        }


@dataclass
class ConversationTurn:
    """对话轮次。"""
    role: str  # user | assistant
    content: str
    intent: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class ThreadSnapshot:
    """线程快照。"""
    id: str
    name: str
    thread_type: str
    resume_tokens: str
    resume_capsule: dict[str, Any]
    urgency_score: float
    emotion_score: float


class ReviewExtractor:
    """复盘摘要抽取器。"""
    
    def __init__(self):
        self._blocker_keywords = [
            "写不完", "被拒", "打回", "效率低", "松懈", "没状态", "焦虑", "累",
            "困难", "压力", "崩溃", "失败", "不顺", "拖延", "逃避", "不想",
            "后悔", "乱", "迷茫", "卡住", "瓶颈", "冲突", "纠结",
        ]
        self._win_keywords = [
            "完成了", "搞定了", "进步了", "改完", "通过", "成功", "顺利",
            "很好", "不错", "满意", "开心", "值得", "收获",
        ]
        self._action_keywords = [
            "明天", "下次", "试试", "建议", "要不", "定个", "先",
            "第一步", "先从", "接下来", "然后", "之后",
        ]
    
    def extract(
        self,
        turns: list[ConversationTurn],
        active_thread: ThreadSnapshot | None,
        background_threads: list[ThreadSnapshot],
        current_state: dict[str, Any],
        scope: str = "day",
        recent_reviews: list[dict[str, Any]] | None = None,
    ) -> ReviewSummary:
        """从多轮对话中抽取复盘摘要。
        
        Args:
            turns: 最近几轮对话（至少包含用户请求复盘的那一轮及后续）
            active_thread: 当前前台主线
            background_threads: 后台主线列表
            current_state: 当前对话状态摘要
            scope: 复盘范围 day/week/phase
            recent_reviews: 最近复盘记录的 system_summary 列表
            
        Returns:
            ReviewSummary
        """
        
        # === 1. 提取关键事件（从所有对话轮次中）===
        key_events = self._extract_key_events(turns)
        
        # === 2. 提取卡点 ===
        blockers = self._extract_blockers(turns)
        
        # === 3. 提取小成就 ===
        wins = self._extract_wins(turns)
        
        # === 4. 提取下一步行动 ===
        next_actions = self._extract_next_actions(turns)
        
        # === 5. 推断能量模式 ===
        energy_pattern = self._infer_energy_pattern(turns)
        
        # === 6. 推断主导情绪 ===
        dominant_emotion = self._infer_dominant_emotion(turns, current_state)
        
        # === 7. 推断情绪趋势 ===
        emotion_trend = self._infer_emotion_trend(turns)
        
        # === 8. 计算平均情绪强度 ===
        avg_intensity = self._calc_avg_intensity(turns)
        
        # === 9. 提取话题 ===
        topics = self._extract_topics(turns, active_thread, background_threads)

        # === 10. 推断用户场景 ===
        user_scene = current_state.get("user_scene", "unknown")

        # === 11. 用线程胶囊补强 ===
        key_events, blockers, wins, next_actions, topics = self._merge_thread_context(
            key_events=key_events,
            blockers=blockers,
            wins=wins,
            next_actions=next_actions,
            topics=topics,
            active_thread=active_thread,
            background_threads=background_threads,
        )

        # === 12. 用最近复盘记录补强 ===
        dominant_emotion, energy_pattern, key_events, blockers, wins, next_actions, topics = self._merge_recent_reviews(
            dominant_emotion=dominant_emotion,
            energy_pattern=energy_pattern,
            key_events=key_events,
            blockers=blockers,
            wins=wins,
            next_actions=next_actions,
            topics=topics,
            recent_reviews=recent_reviews or [],
            scope=scope,
        )
        
        # 组装结构化摘要
        structured = {
            "time_range": scope,
            "dominant_emotion": dominant_emotion,
            "emotion_trend": emotion_trend,
            "avg_intensity": round(avg_intensity, 2),
            "energy_pattern": energy_pattern,
            "key_events": key_events[:5],
            "blockers": list(set(blockers)),
            "wins": wins,
            "next_actions": next_actions[:3],
            "user_scene": user_scene,
            "topics": topics[-3:],
            "thread_context": {
                "active_thread": active_thread.name if active_thread else "",
                "background_count": len(background_threads),
            } if active_thread else {},
        }
        
        # 生成用户可见文本（从最近 assistant 回复中提取或生成）
        user_visible = self._generate_user_visible(turns, scope)
        
        return ReviewSummary(
            scope=scope,
            user_visible=user_visible,
            structured=structured,
        )

    def _merge_thread_context(
        self,
        key_events: list[str],
        blockers: list[str],
        wins: list[str],
        next_actions: list[str],
        topics: list[str],
        active_thread: ThreadSnapshot | None,
        background_threads: list[ThreadSnapshot],
    ) -> tuple[list[str], list[str], list[str], list[str], list[str]]:
        """用线程胶囊补强复盘抽取。"""
        threads = ([active_thread] if active_thread else []) + list(background_threads)
        for thread in threads:
            if not thread:
                continue
            capsule = thread.resume_capsule or {}
            hint = capsule.get("resume_hint_for_reply", "")
            if hint:
                key_events.append(hint[:80])
            blocker = capsule.get("current_blocker", "")
            if blocker:
                blockers.extend([part.strip() for part in blocker.split(",") if part.strip()])
            next_action = capsule.get("next_recommended_action", "")
            if next_action:
                next_actions.append(next_action)
            why = capsule.get("why_it_matters", "")
            if why:
                wins.append(f"持续在推进{thread.name}")
            if thread.thread_type and thread.thread_type not in topics:
                topics.append(thread.thread_type)
            if thread.name and thread.name != "闲聊" and thread.name not in topics:
                topics.append(thread.name)
        return (
            self._dedupe_keep_order(key_events),
            self._dedupe_keep_order(blockers),
            self._dedupe_keep_order(wins),
            self._dedupe_keep_order(next_actions),
            self._dedupe_keep_order(topics),
        )

    def _merge_recent_reviews(
        self,
        dominant_emotion: str,
        energy_pattern: str,
        key_events: list[str],
        blockers: list[str],
        wins: list[str],
        next_actions: list[str],
        topics: list[str],
        recent_reviews: list[dict[str, Any]],
        scope: str,
    ) -> tuple[str, str, list[str], list[str], list[str], list[str], list[str]]:
        """把最近复盘记录并入当前复盘摘要。"""
        if not recent_reviews:
            return dominant_emotion, energy_pattern, key_events, blockers, wins, next_actions, topics

        emotion_counts: dict[str, int] = {}
        energy_counts: dict[str, int] = {}
        for review in recent_reviews:
            emotion = review.get("dominant_emotion", "")
            if emotion:
                emotion_counts[emotion] = emotion_counts.get(emotion, 0) + 1
            energy = review.get("energy_pattern", "")
            if energy:
                energy_counts[energy] = energy_counts.get(energy, 0) + 1
            key_events.extend(review.get("key_events", [])[:2])
            blockers.extend(review.get("blockers", [])[:2])
            wins.extend(review.get("wins", [])[:2])
            next_actions.extend(review.get("next_actions", [])[:2])
            topics.extend(review.get("topics", [])[:2])

        if scope in ("week", "phase"):
            if emotion_counts:
                dominant_emotion = max(emotion_counts, key=emotion_counts.get)
            if energy_counts:
                energy_pattern = max(energy_counts, key=energy_counts.get)

        return (
            dominant_emotion,
            energy_pattern,
            self._dedupe_keep_order(key_events),
            self._dedupe_keep_order(blockers),
            self._dedupe_keep_order(wins),
            self._dedupe_keep_order(next_actions),
            self._dedupe_keep_order(topics),
        )

    @staticmethod
    def _dedupe_keep_order(items: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in items:
            clean = (item or "").strip()
            if not clean or clean in seen:
                continue
            seen.add(clean)
            result.append(clean)
        return result
    
    def _extract_key_events(self, turns: list[ConversationTurn]) -> list[str]:
        """提取关键事件。"""
        events = []
        for turn in turns:
            if turn.role == "user":
                content = turn.content.strip()
                # 过滤掉复盘请求本身
                if len(content) > 15 and not any(ph in content for ph in ["复盘", "帮我梳理", "总结一下"]):
                    # 提取第一句或前50字作为事件摘要
                    first_sent = content.split("。")[0].split("！")[0].split("？")[0]
                    if len(first_sent) > 5:
                        events.append(first_sent[:80])
        return events
    
    def _extract_blockers(self, turns: list[ConversationTurn]) -> list[str]:
        """提取卡点/困难。"""
        blockers = []
        for turn in turns:
            if turn.role == "user":
                for kw in self._blocker_keywords:
                    if kw in turn.content and kw not in blockers:
                        blockers.append(kw)
        return blockers
    
    def _extract_wins(self, turns: list[ConversationTurn]) -> list[str]:
        """提取小成就。"""
        wins = []
        for turn in turns:
            content = turn.content
            # 从 assistant 回复中识别积极信号
            if turn.role == "assistant":
                if any(kw in content for kw in self._win_keywords):
                    wins.append("有积极进展")
            # 从用户消息中识别
            if turn.role == "user":
                if any(kw in content for kw in ["完成了", "搞定了", "改了", "做了"]):
                    wins.append("主动推进")
        # 去重
        return list(set(wins)) if wins else []
    
    def _extract_next_actions(self, turns: list[ConversationTurn]) -> list[str]:
        """提取下一步行动。"""
        actions = []
        for turn in turns:
            if turn.role == "assistant":
                content = turn.content
                # 找包含行动建议的句子
                for sent in content.split("。"):
                    sent = sent.strip()
                    if any(kw in sent for kw in self._action_keywords):
                        if len(sent) > 10 and len(sent) < 100:
                            actions.append(sent)
        return actions
    
    def _infer_energy_pattern(self, turns: list[ConversationTurn]) -> str:
        """推断能量模式。"""
        user_turns = [t for t in turns if t.role == "user"]
        if len(user_turns) < 2:
            return "stable"
        
        # 简单推断：基于消息长度和关键词
        early = user_turns[0].content
        late = user_turns[-1].content
        
        early_energy = len(early) + sum(1 for kw in ["累", "崩溃", "焦虑"] if kw in early) * 20
        late_energy = len(late) + sum(1 for kw in ["累", "崩溃", "焦虑"] if kw in late) * 20
        
        if early_energy > late_energy * 1.5:
            return "前高后低"
        elif late_energy > early_energy * 1.5:
            return "前低后高"
        else:
            return "稳定"
    
    def _infer_dominant_emotion(
        self,
        turns: list[ConversationTurn],
        current_state: dict[str, Any],
    ) -> str:
        """推断主导情绪。"""
        # 优先使用 current_state 中的情绪
        state_emotion = current_state.get("dominant_emotion", "")
        if state_emotion:
            return state_emotion
        
        # 从对话中推断
        emotion_keywords = {
            "焦虑": "anxious", "紧张": "anxious", "担心": "anxious",
            "难过": "sad", "沮丧": "sad", "失落": "sad",
            "开心": "happy", "高兴": "happy", "兴奋": "happy",
            "生气": "angry", "愤怒": "angry", "烦": "angry",
            "累": "tired", "疲惫": "tired", "困": "tired",
            "平静": "neutral", "还好": "neutral", "一般": "neutral",
        }
        counts: dict[str, int] = {}
        for turn in turns:
            if turn.role == "user":
                for kw, emotion in emotion_keywords.items():
                    if kw in turn.content:
                        counts[emotion] = counts.get(emotion, 0) + 1
        
        if counts:
            return max(counts, key=counts.get)
        return "neutral"
    
    def _infer_emotion_trend(self, turns: list[ConversationTurn]) -> str:
        """推断情绪趋势。"""
        intensities = []
        for turn in turns:
            if turn.role == "user" and turn.intent:
                intensities.append(turn.intent.get("emotional_intensity", 0.3))
        
        if len(intensities) < 2:
            return "stable"
        
        if intensities[-1] - intensities[0] > 0.2:
            return "rising"
        elif intensities[0] - intensities[-1] > 0.2:
            return "falling"
        return "stable"
    
    def _calc_avg_intensity(self, turns: list[ConversationTurn]) -> float:
        """计算平均情绪强度。"""
        intensities = []
        for turn in turns:
            if turn.role == "user" and turn.intent:
                intensities.append(turn.intent.get("emotional_intensity", 0.3))
        
        if not intensities:
            return 0.0
        return sum(intensities) / len(intensities)
    
    def _extract_topics(
        self,
        turns: list[ConversationTurn],
        active_thread: ThreadSnapshot | None,
        background_threads: list[ThreadSnapshot],
    ) -> list[str]:
        """提取话题。"""
        topics = []
        
        # 从线程中提取
        if active_thread:
            topics.append(active_thread.thread_type)
            if active_thread.name and active_thread.name != "闲聊":
                topics.append(active_thread.name)
        
        for bt in background_threads:
            if bt.thread_type != "light_chat":
                topics.append(bt.thread_type)
        
        # 从用户消息中提取任务类别
        for turn in turns:
            if turn.role == "user" and turn.intent:
                task = turn.intent.get("task_category", "")
                if task and task != "none":
                    topics.append(task)
        
        # 去重并限制
        seen = set()
        result = []
        for t in topics:
            if t not in seen:
                seen.add(t)
                result.append(t)
        return result
    
    def _generate_user_visible(
        self,
        turns: list[ConversationTurn],
        scope: str,
    ) -> str:
        """生成用户可见的复盘文本。
        
        从最近的 assistant 回复中提取，如果没有则生成一个默认的。
        """
        # 找最近的 assistant 回复
        assistant_replies = [t.content for t in turns if t.role == "assistant"]
        if assistant_replies:
            # 返回最后一条，通常是完整的复盘回复
            return assistant_replies[-1][:500]
        
        scope_names = {"day": "今天", "week": "这周", "phase": "这阶段"}
        return f"{scope_names.get(scope, '这段时间')}的复盘已记录。"
