"""
Thread Manager

管理前台主线 / 后台主线 / 话题切换 / 主线恢复。

核心数据结构：
- active_thread: 当前前台主线
- background_threads: 后台主线列表
- thread_type: pressure/relationship/study/research/career/life_admin/light_chat
- thread_status: foreground/background/dormant/resolved

核心能力：
- 创建线程
- 合并线程
- 主线切换
- 主线恢复
- 自动降级
- 计算前后台排序
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Thread:
    """对话主线。"""
    id: str
    name: str  # 主线程名称
    thread_type: str  # pressure/relationship/study/research/career/life_admin/light_chat
    status: str = "foreground"  # foreground/background/dormant/resolved
    
    # 评分维度
    urgency_score: float = 0.5  # 0-1，紧急度
    emotion_score: float = 0.5  # 0-1，情绪权重
    recency_score: float = 0.5  # 0-1，最近活跃度
    resumability_score: float = 0.5  # 0-1，可恢复度
    user_focus_score: float = 0.5  # 0-1，用户关注度
    
    # 上下文
    resume_tokens: str = ""  # 快速恢复摘要
    resume_capsule: dict[str, Any] = field(default_factory=dict)
    last_active_turn: int = 0
    created_turn: int = 0

    # 元数据
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ThreadSessionState:
    active_thread: Thread | None = None
    background_threads: list[Thread] = field(default_factory=list)
    dormant_threads: list[Thread] = field(default_factory=list)
    resolved_threads: list[Thread] = field(default_factory=list)
    turn_counter: int = 0


class ThreadManager:
    """对话主线管理器。"""
    
    THREAD_TYPES = [
        "pressure",      # 高压事件（推免、分手、家庭矛盾）
        "relationship",  # 关系处理
        "study",         # 学习/考试
        "research",      # 科研/项目
        "career",        # 职业规划
        "life_admin",    # 生活事务（选课、搬宿舍）
        "light_chat",    # 轻松闲聊
    ]
    
    def __init__(self):
        self._sessions: dict[str, ThreadSessionState] = {}
        self._default_session = "default"
        self._max_background = 2
        self._max_dormant = 8
    
    def _get_or_create_session(self, session_id: str = "") -> ThreadSessionState:
        sid = session_id or self._default_session
        if sid not in self._sessions:
            self._sessions[sid] = ThreadSessionState()
        return self._sessions[sid]
    
    @property
    def active_thread(self) -> Thread | None:
        return self._get_or_create_session().active_thread
    
    @property
    def background_threads(self) -> list[Thread]:
        return self._get_or_create_session().background_threads
    
    @property
    def dormant_threads(self) -> list[Thread]:
        return self._get_or_create_session().dormant_threads

    def _next_turn(self, session_id: str = "") -> int:
        """递增轮次计数器。"""
        session = self._get_or_create_session(session_id)
        session.turn_counter += 1
        return session.turn_counter
    
    def create_thread(
        self,
        name: str,
        thread_type: str,
        urgency_score: float = 0.5,
        emotion_score: float = 0.5,
        resume_tokens: str = "",
        metadata: dict[str, Any] | None = None,
        session_id: str = "",
    ) -> Thread:
        """创建新主线。"""
        session = self._get_or_create_session(session_id)

        # 优先恢复已有线程，避免同一主线不断新建副本。
        existing = None
        candidates = []
        if session.active_thread:
            candidates.append(session.active_thread)
        candidates.extend(session.background_threads)
        candidates.extend(session.dormant_threads)
        for thread in candidates:
            if thread.status == "resolved":
                continue
            if thread.name == name or (thread.thread_type == thread_type and thread_type != "light_chat"):
                existing = thread
                break

        if existing:
            existing.urgency_score = max(existing.urgency_score, urgency_score)
            existing.emotion_score = max(existing.emotion_score, emotion_score)
            if resume_tokens:
                existing.resume_tokens = resume_tokens
            if metadata:
                existing.metadata.update(metadata)
            existing.resume_capsule = self._build_resume_capsule(
                name=existing.name,
                thread_type=existing.thread_type,
                urgency_score=existing.urgency_score,
                emotion_score=existing.emotion_score,
                resume_tokens=existing.resume_tokens,
                metadata=existing.metadata,
            )
            self.switch_to_thread(existing.id, session_id)
            return existing

        turn = self._next_turn(session_id)
        thread = Thread(
            id=f"thread_{turn}_{int(time.time())}",
            name=name,
            thread_type=thread_type,
            status="foreground",
            urgency_score=urgency_score,
            emotion_score=emotion_score,
            recency_score=1.0,
            resumability_score=0.8,
            user_focus_score=1.0,
            resume_tokens=resume_tokens,
            resume_capsule=self._build_resume_capsule(
                name=name,
                thread_type=thread_type,
                urgency_score=urgency_score,
                emotion_score=emotion_score,
                resume_tokens=resume_tokens,
            ),
            last_active_turn=turn,
            created_turn=turn,
            metadata=metadata or {},
        )
        
        # 如果已有前台主线，将其降级到后台
        if session.active_thread and session.active_thread.status == "foreground":
            session.active_thread.status = "background"
            session.active_thread.recency_score *= 0.8
            session.background_threads.append(session.active_thread)
            self._trim_background(session_id)
        
        session.active_thread = thread
        return thread
    
    def update_thread(
        self,
        thread_id: str,
        urgency_score: float | None = None,
        emotion_score: float | None = None,
        user_focus_score: float | None = None,
        resume_tokens: str | None = None,
        metadata: dict[str, Any] | None = None,
        session_id: str = "",
    ) -> Thread | None:
        """更新主线状态。"""
        session = self._get_or_create_session(session_id)
        thread = self._find_thread(thread_id, session_id)
        if not thread:
            return None
        
        if urgency_score is not None:
            thread.urgency_score = urgency_score
        if emotion_score is not None:
            thread.emotion_score = emotion_score
        if user_focus_score is not None:
            thread.user_focus_score = user_focus_score
        if resume_tokens is not None:
            thread.resume_tokens = resume_tokens
        if metadata:
            thread.metadata.update(metadata)
        thread.resume_capsule = self._build_resume_capsule(
            name=thread.name,
            thread_type=thread.thread_type,
            urgency_score=thread.urgency_score,
            emotion_score=thread.emotion_score,
            resume_tokens=thread.resume_tokens,
            metadata=thread.metadata,
        )
        
        thread.last_active_turn = session.turn_counter
        thread.recency_score = 1.0  # 重置活跃度
        
        return thread
    
    def switch_to_thread(self, thread_id: str, session_id: str = "") -> Thread | None:
        """切换到指定主线。"""
        session = self._get_or_create_session(session_id)
        target = self._find_thread(thread_id, session_id)
        if not target:
            return None
        
        # 当前前台降级
        if session.active_thread:
            session.active_thread.status = "background"
            session.active_thread.recency_score *= 0.8
            if session.active_thread not in session.background_threads:
                session.background_threads.append(session.active_thread)
        
        # 目标升级
        target.status = "foreground"
        target.recency_score = 1.0
        target.last_active_turn = session.turn_counter
        
        # 从后台列表移除
        if target in session.background_threads:
            session.background_threads.remove(target)
        if target in session.dormant_threads:
            session.dormant_threads.remove(target)
        
        session.active_thread = target
        self._trim_background(session_id)
        return target
    
    def resolve_thread(self, thread_id: str, session_id: str = "") -> bool:
        """标记主线为已解决。"""
        session = self._get_or_create_session(session_id)
        thread = self._find_thread(thread_id, session_id)
        if not thread:
            return False
        
        thread.status = "resolved"
        
        if thread == session.active_thread:
            session.active_thread = None
            # 尝试恢复最高分的后台主线
            self._promote_best_background(session_id)
        elif thread in session.background_threads:
            session.background_threads.remove(thread)
        elif thread in session.dormant_threads:
            session.dormant_threads.remove(thread)
        session.resolved_threads.append(thread)
        
        return True
    
    def score_threads(self, session_id: str = "") -> list[tuple[Thread, float]]:
        """计算所有主线的综合分数并排序。"""
        session = self._get_or_create_session(session_id)
        all_threads = []
        if session.active_thread:
            all_threads.append(session.active_thread)
        all_threads.extend(session.background_threads)
        all_threads.extend(session.dormant_threads)
        
        scored = []
        for thread in all_threads:
            # 综合分数 = 紧急度*0.3 + 情绪权重*0.25 + 最近活跃度*0.2 + 可恢复度*0.15 + 用户关注度*0.1
            score = (
                thread.urgency_score * 0.3 +
                thread.emotion_score * 0.25 +
                thread.recency_score * 0.2 +
                thread.resumability_score * 0.15 +
                thread.user_focus_score * 0.1
            )
            scored.append((thread, score))
        
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored
    
    def get_active_thread_summary(self, session_id: str = "") -> dict[str, Any]:
        """获取前台主线摘要。"""
        session = self._get_or_create_session(session_id)
        if not session.active_thread:
            return {}
        
        return {
            "id": session.active_thread.id,
            "name": session.active_thread.name,
            "type": session.active_thread.thread_type,
            "urgency": session.active_thread.urgency_score,
            "emotion": session.active_thread.emotion_score,
            "resume_tokens": session.active_thread.resume_tokens,
            "resume_capsule": session.active_thread.resume_capsule,
        }
    
    def get_background_summaries(self, session_id: str = "") -> list[dict[str, Any]]:
        """获取后台主线摘要列表。"""
        session = self._get_or_create_session(session_id)
        summaries = []
        for thread in session.background_threads[: self._max_background]:
            summaries.append({
                "id": thread.id,
                "name": thread.name,
                "type": thread.thread_type,
                "urgency": thread.urgency_score,
                "resume_tokens": thread.resume_tokens[:100],
                "resume_capsule": thread.resume_capsule,
            })
        return summaries
    
    def should_pull_main_thread(self, session_id: str = "") -> tuple[bool, str]:
        """判断是否应该拉回主线。
        
        条件：
        - 当前前台是轻闲聊
        - 后台存在高压未解决主线
        - 用户情绪已稳定
        
        Returns:
            (是否拉回, 目标主线ID)
        """
        session = self._get_or_create_session(session_id)
        if not session.active_thread or session.active_thread.thread_type != "light_chat":
            return False, ""
        
        # 找后台中分数最高的非 light_chat 主线
        best_thread = None
        best_score = 0.0
        
        for thread in session.background_threads:
            if thread.thread_type == "light_chat":
                continue
            
            # === action_resume_score: 基于复盘 next_actions 的恢复优先级 ===
            action_resume_score = 0.0
            capsule = thread.resume_capsule or {}
            review_actions = capsule.get("review_next_actions", [])
            last_review_at = capsule.get("last_review_at", 0)
            if review_actions:
                # 有明确的 next_actions，提高恢复优先级
                action_resume_score = 0.3
                # 如果复盘比较新（24小时内），额外加分
                if last_review_at and (time.time() - last_review_at) < 86400:
                    action_resume_score += 0.15
            
            score = (
                thread.urgency_score * 0.35 +
                thread.emotion_score * 0.25 +
                thread.resumability_score * 0.25 +
                action_resume_score
            )
            if score > best_score and score > 0.6:
                best_score = score
                best_thread = thread
        
        if best_thread:
            return True, best_thread.id
        
        return False, ""
    
    def _find_thread(self, thread_id: str, session_id: str = "") -> Thread | None:
        """查找主线。"""
        session = self._get_or_create_session(session_id)
        if session.active_thread and session.active_thread.id == thread_id:
            return session.active_thread
        
        for thread in session.background_threads:
            if thread.id == thread_id:
                return thread
        
        for thread in session.dormant_threads:
            if thread.id == thread_id:
                return thread
        
        return None
    
    def _trim_background(self, session_id: str = "") -> None:
        """修剪后台主线列表，超出的降级为 dormant。"""
        session = self._get_or_create_session(session_id)
        while len(session.background_threads) > self._max_background:
            lowest = min(
                session.background_threads,
                key=lambda t: (
                    t.urgency_score * 0.35 +
                    t.emotion_score * 0.25 +
                    t.recency_score * 0.2 +
                    t.user_focus_score * 0.2
                ),
            )
            lowest.status = "dormant"
            session.background_threads.remove(lowest)
            session.dormant_threads.append(lowest)
        while len(session.dormant_threads) > self._max_dormant:
            session.dormant_threads.sort(key=lambda t: t.last_active_turn)
            session.dormant_threads.pop(0)
    
    def _promote_best_background(self, session_id: str = "") -> None:
        """提升最佳后台主线为前台。"""
        session = self._get_or_create_session(session_id)
        if not session.background_threads:
            return
        
        best = max(session.background_threads, key=lambda t: (
            t.urgency_score * 0.4 +
            t.emotion_score * 0.3 +
            t.recency_score * 0.3
        ))
        
        best.status = "foreground"
        best.recency_score = 1.0
        session.background_threads.remove(best)
        session.active_thread = best
    
    def detect_topic_shift(
        self,
        current_intent: Any,
        previous_intent: Any | None,
    ) -> tuple[bool, str]:
        """检测话题切换。
        
        Returns:
            (是否切换, 新话题类型)
        """
        if not previous_intent:
            seed = (getattr(current_intent, "thread_candidates", []) or [])
            return True, seed[0] if seed else current_intent.task_category

        shift_type = getattr(current_intent, "topic_shift_type", "none")
        if shift_type == "return_to_thread":
            seed = (getattr(current_intent, "thread_candidates", []) or [])
            if seed:
                return True, seed[0]
        if shift_type == "new_thread":
            seed = (getattr(current_intent, "thread_candidates", []) or [])
            if seed:
                return True, seed[0]
        
        # 简单规则：任务类别变化且持续2轮
        if current_intent.task_category != previous_intent.task_category:
            if current_intent.task_category != "none":
                return True, current_intent.task_category

        current_candidates = getattr(current_intent, "thread_candidates", []) or []
        previous_candidates = getattr(previous_intent, "thread_candidates", []) or []
        if current_candidates and current_candidates[:1] != previous_candidates[:1]:
            return True, current_candidates[0]
        
        return False, ""
    
    def get_status(self, session_id: str = "") -> dict[str, Any]:
        """获取主线管理器状态。"""
        session = self._get_or_create_session(session_id)
        return {
            "active_thread": self.get_active_thread_summary(session_id),
            "background_count": len(session.background_threads),
            "dormant_count": len(session.dormant_threads),
            "turn_counter": session.turn_counter,
        }
    
    def _build_resume_capsule(
        self,
        name: str,
        thread_type: str,
        urgency_score: float,
        emotion_score: float,
        resume_tokens: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        urgency_label = "高" if urgency_score > 0.7 else ("中" if urgency_score > 0.4 else "低")
        emotion_label = "高压" if emotion_score > 0.7 else ("牵挂中" if emotion_score > 0.4 else "平稳")
        next_action = ""
        if metadata:
            next_action = str(metadata.get("next_action", ""))
        return {
            "thread_name": name,
            "thread_type": thread_type,
            "current_stage": metadata.get("current_stage", "") if metadata else "",
            "why_it_matters": metadata.get("why_it_matters", "") if metadata else "",
            "current_blocker": metadata.get("current_blocker", "") if metadata else "",
            "last_progress": resume_tokens[:120],
            "next_recommended_action": next_action,
            "emotion_tone": emotion_label,
            "urgency": urgency_label,
            "resume_hint_for_reply": f"{name}这条线还挂着，最近卡点是：{resume_tokens[:80]}",
        }
