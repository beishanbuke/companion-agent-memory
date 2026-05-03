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
    last_active_turn: int = 0
    created_turn: int = 0
    
    # 元数据
    metadata: dict[str, Any] = field(default_factory=dict)


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
        self.active_thread: Thread | None = None
        self.background_threads: list[Thread] = []
        self.dormant_threads: list[Thread] = []
        self._turn_counter = 0
        self._max_background = 3  # 最多保留3个后台主线
    
    def _next_turn(self) -> int:
        """递增轮次计数器。"""
        self._turn_counter += 1
        return self._turn_counter
    
    def create_thread(
        self,
        name: str,
        thread_type: str,
        urgency_score: float = 0.5,
        emotion_score: float = 0.5,
        resume_tokens: str = "",
    ) -> Thread:
        """创建新主线。"""
        thread = Thread(
            id=f"thread_{self._turn_counter}_{int(time.time())}",
            name=name,
            thread_type=thread_type,
            status="foreground",
            urgency_score=urgency_score,
            emotion_score=emotion_score,
            recency_score=1.0,
            resumability_score=0.8,
            user_focus_score=1.0,
            resume_tokens=resume_tokens,
            last_active_turn=self._turn_counter,
            created_turn=self._turn_counter,
        )
        
        # 如果已有前台主线，将其降级到后台
        if self.active_thread and self.active_thread.status == "foreground":
            self.active_thread.status = "background"
            self.active_thread.recency_score *= 0.8  # 衰减
            self.background_threads.append(self.active_thread)
            self._trim_background()
        
        self.active_thread = thread
        return thread
    
    def update_thread(
        self,
        thread_id: str,
        urgency_score: float | None = None,
        emotion_score: float | None = None,
        user_focus_score: float | None = None,
        resume_tokens: str | None = None,
    ) -> Thread | None:
        """更新主线状态。"""
        thread = self._find_thread(thread_id)
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
        
        thread.last_active_turn = self._turn_counter
        thread.recency_score = 1.0  # 重置活跃度
        
        return thread
    
    def switch_to_thread(self, thread_id: str) -> Thread | None:
        """切换到指定主线。"""
        target = self._find_thread(thread_id)
        if not target:
            return None
        
        # 当前前台降级
        if self.active_thread:
            self.active_thread.status = "background"
            self.active_thread.recency_score *= 0.8
            if self.active_thread not in self.background_threads:
                self.background_threads.append(self.active_thread)
        
        # 目标升级
        target.status = "foreground"
        target.recency_score = 1.0
        target.last_active_turn = self._turn_counter
        
        # 从后台列表移除
        if target in self.background_threads:
            self.background_threads.remove(target)
        if target in self.dormant_threads:
            self.dormant_threads.remove(target)
        
        self.active_thread = target
        self._trim_background()
        return target
    
    def resolve_thread(self, thread_id: str) -> bool:
        """标记主线为已解决。"""
        thread = self._find_thread(thread_id)
        if not thread:
            return False
        
        thread.status = "resolved"
        
        if thread == self.active_thread:
            self.active_thread = None
            # 尝试恢复最高分的后台主线
            self._promote_best_background()
        elif thread in self.background_threads:
            self.background_threads.remove(thread)
        elif thread in self.dormant_threads:
            self.dormant_threads.remove(thread)
        
        return True
    
    def score_threads(self) -> list[tuple[Thread, float]]:
        """计算所有主线的综合分数并排序。"""
        all_threads = []
        if self.active_thread:
            all_threads.append(self.active_thread)
        all_threads.extend(self.background_threads)
        all_threads.extend(self.dormant_threads)
        
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
    
    def get_active_thread_summary(self) -> dict[str, Any]:
        """获取前台主线摘要。"""
        if not self.active_thread:
            return {}
        
        return {
            "id": self.active_thread.id,
            "name": self.active_thread.name,
            "type": self.active_thread.thread_type,
            "urgency": self.active_thread.urgency_score,
            "emotion": self.active_thread.emotion_score,
            "resume_tokens": self.active_thread.resume_tokens,
        }
    
    def get_background_summaries(self) -> list[dict[str, Any]]:
        """获取后台主线摘要列表。"""
        summaries = []
        for thread in self.background_threads:
            summaries.append({
                "id": thread.id,
                "name": thread.name,
                "type": thread.thread_type,
                "urgency": thread.urgency_score,
                "resume_tokens": thread.resume_tokens[:100],
            })
        return summaries
    
    def should_pull_main_thread(self) -> tuple[bool, str]:
        """判断是否应该拉回主线。
        
        条件：
        - 当前前台是轻闲聊
        - 后台存在高压未解决主线
        - 用户情绪已稳定
        
        Returns:
            (是否拉回, 目标主线ID)
        """
        if not self.active_thread or self.active_thread.thread_type != "light_chat":
            return False, ""
        
        # 找后台中分数最高的非 light_chat 主线
        best_thread = None
        best_score = 0.0
        
        for thread in self.background_threads:
            if thread.thread_type == "light_chat":
                continue
            score = (
                thread.urgency_score * 0.4 +
                thread.emotion_score * 0.3 +
                thread.resumability_score * 0.3
            )
            if score > best_score and score > 0.6:
                best_score = score
                best_thread = thread
        
        if best_thread:
            return True, best_thread.id
        
        return False, ""
    
    def _find_thread(self, thread_id: str) -> Thread | None:
        """查找主线。"""
        if self.active_thread and self.active_thread.id == thread_id:
            return self.active_thread
        
        for thread in self.background_threads:
            if thread.id == thread_id:
                return thread
        
        for thread in self.dormant_threads:
            if thread.id == thread_id:
                return thread
        
        return None
    
    def _trim_background(self) -> None:
        """修剪后台主线列表，超出的降级为 dormant。"""
        while len(self.background_threads) > self._max_background:
            # 找分数最低的降级
            oldest = min(self.background_threads, key=lambda t: t.last_active_turn)
            oldest.status = "dormant"
            self.background_threads.remove(oldest)
            self.dormant_threads.append(oldest)
    
    def _promote_best_background(self) -> None:
        """提升最佳后台主线为前台。"""
        if not self.background_threads:
            return
        
        best = max(self.background_threads, key=lambda t: (
            t.urgency_score * 0.4 +
            t.emotion_score * 0.3 +
            t.recency_score * 0.3
        ))
        
        best.status = "foreground"
        best.recency_score = 1.0
        self.background_threads.remove(best)
        self.active_thread = best
    
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
            return True, current_intent.task_category
        
        # 简单规则：任务类别变化且持续2轮
        if current_intent.task_category != previous_intent.task_category:
            if current_intent.task_category != "none":
                return True, current_intent.task_category
        
        return False, ""
    
    def get_status(self) -> dict[str, Any]:
        """获取主线管理器状态。"""
        return {
            "active_thread": self.get_active_thread_summary(),
            "background_count": len(self.background_threads),
            "dormant_count": len(self.dormant_threads),
            "turn_counter": self._turn_counter,
        }