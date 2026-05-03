"""
Review Store

轻量复盘存储层：按 session / date / scope 存储复盘摘要。
支持：
- 日/周/阶段复盘的持久化
- 跨会话聚合（为连续日记、周报做准备）
- 按时间范围查询

数据结构：
{
  "session_id": {
    "YYYY-MM-DD": {
      "day": ReviewRecord,
      "week": ReviewRecord | null,
      "phase": ReviewRecord | null
    }
  }
}
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class ReviewRecord:
    """单条复盘记录。"""
    session_id: str
    date: str  # YYYY-MM-DD
    scope: str  # day | week | phase
    user_visible_text: str = ""  # 用户可见的口语化复盘
    system_summary: dict[str, Any] = field(default_factory=dict)  # 结构化摘要
    created_at: float = field(default_factory=time.time)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "date": self.date,
            "scope": self.scope,
            "user_visible_text": self.user_visible_text,
            "system_summary": self.system_summary,
            "created_at": self.created_at,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewRecord":
        return cls(
            session_id=data.get("session_id", ""),
            date=data.get("date", ""),
            scope=data.get("scope", "day"),
            user_visible_text=data.get("user_visible_text", ""),
            system_summary=data.get("system_summary", {}),
            created_at=data.get("created_at", 0.0),
        )


class ReviewStore:
    """复盘存储层。"""
    
    def __init__(self, storage_dir: str | None = None):
        """
        Args:
            storage_dir: 存储目录，默认使用项目根目录下的 review_store/
        """
        if storage_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            storage_dir = os.path.join(base_dir, "review_store")
        self._storage_dir = storage_dir
        os.makedirs(self._storage_dir, exist_ok=True)
        
        # 内存缓存: {session_id: {date: {scope: ReviewRecord}}}
        self._cache: dict[str, dict[str, dict[str, ReviewRecord]]] = {}
    
    def _get_file_path(self, session_id: str) -> str:
        """获取某个 session 的存储文件路径。"""
        safe_id = "".join(c for c in session_id if c.isalnum() or c in "_-").rstrip("_")
        return os.path.join(self._storage_dir, f"{safe_id}.json")
    
    def _load_session(self, session_id: str) -> dict[str, dict[str, ReviewRecord]]:
        """从磁盘加载某个 session 的复盘记录。"""
        if session_id in self._cache:
            return self._cache[session_id]
        
        path = self._get_file_path(session_id)
        if not os.path.exists(path):
            self._cache[session_id] = {}
            return {}
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            result: dict[str, dict[str, ReviewRecord]] = {}
            for date_str, scopes in data.items():
                result[date_str] = {}
                for scope, record_data in scopes.items():
                    result[date_str][scope] = ReviewRecord.from_dict(record_data)
            
            self._cache[session_id] = result
            return result
        except Exception:
            self._cache[session_id] = {}
            return {}
    
    def _save_session(self, session_id: str) -> None:
        """保存某个 session 的复盘记录到磁盘。"""
        path = self._get_file_path(session_id)
        data: dict[str, dict[str, dict[str, Any]]] = {}
        
        session_data = self._cache.get(session_id, {})
        for date_str, scopes in session_data.items():
            data[date_str] = {}
            for scope, record in scopes.items():
                data[date_str][scope] = record.to_dict()
        
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    
    def save_review(
        self,
        session_id: str,
        scope: str,
        user_visible_text: str,
        system_summary: dict[str, Any],
    ) -> ReviewRecord:
        """保存一条复盘记录。
        
        Args:
            session_id: 会话ID
            scope: day | week | phase
            user_visible_text: 用户可见文本
            system_summary: 结构化摘要
            
        Returns:
            保存的记录
        """
        from datetime import datetime
        date_str = datetime.now().strftime("%Y-%m-%d")
        
        record = ReviewRecord(
            session_id=session_id,
            date=date_str,
            scope=scope,
            user_visible_text=user_visible_text,
            system_summary=system_summary,
        )
        
        session_data = self._load_session(session_id)
        if date_str not in session_data:
            session_data[date_str] = {}
        session_data[date_str][scope] = record
        self._cache[session_id] = session_data
        
        self._save_session(session_id)
        return record
    
    def get_reviews(
        self,
        session_id: str,
        scope: str | None = None,
        limit: int = 10,
    ) -> list[ReviewRecord]:
        """查询复盘记录。
        
        Args:
            session_id: 会话ID
            scope: 过滤范围（day/week/phase），None 表示全部
            limit: 返回最大条数
            
        Returns:
            复盘记录列表，按时间倒序
        """
        session_data = self._load_session(session_id)
        results: list[ReviewRecord] = []
        
        # 按日期倒序
        for date_str in sorted(session_data.keys(), reverse=True):
            scopes = session_data[date_str]
            if scope:
                if scope in scopes:
                    results.append(scopes[scope])
            else:
                results.extend(scopes.values())
            
            if len(results) >= limit:
                break
        
        return results[:limit]
    
    def get_latest_review(
        self,
        session_id: str,
        scope: str | None = None,
    ) -> ReviewRecord | None:
        """获取最近的复盘记录。"""
        reviews = self.get_reviews(session_id, scope=scope, limit=1)
        return reviews[0] if reviews else None
    
    def get_reviews_by_date_range(
        self,
        session_id: str,
        start_date: str,
        end_date: str,
        scope: str | None = None,
    ) -> list[ReviewRecord]:
        """按日期范围查询复盘记录。"""
        session_data = self._load_session(session_id)
        results: list[ReviewRecord] = []
        
        for date_str in session_data:
            if start_date <= date_str <= end_date:
                scopes = session_data[date_str]
                if scope:
                    if scope in scopes:
                        results.append(scopes[scope])
                else:
                    results.extend(scopes.values())
        
        # 按日期正序
        results.sort(key=lambda r: r.date)
        return results
    
    def get_weekly_summary(self, session_id: str, week_start_date: str) -> dict[str, Any]:
        """生成某一周的聚合摘要。
        
        Args:
            session_id: 会话ID
            week_start_date: 周开始日期（周一）YYYY-MM-DD
            
        Returns:
            聚合摘要
        """
        from datetime import datetime, timedelta
        start = datetime.strptime(week_start_date, "%Y-%m-%d")
        end = start + timedelta(days=6)
        
        reviews = self.get_reviews_by_date_range(
            session_id,
            week_start_date,
            end.strftime("%Y-%m-%d"),
            scope="day",
        )
        
        if not reviews:
            return {"has_data": False}
        
        # 聚合统计
        all_blockers: list[str] = []
        all_wins: list[str] = []
        all_next_actions: list[str] = []
        all_emotions: list[str] = []
        
        for r in reviews:
            ss = r.system_summary
            all_blockers.extend(ss.get("blockers", []))
            all_wins.extend(ss.get("wins", []))
            all_next_actions.extend(ss.get("next_actions", []))
            all_emotions.append(ss.get("dominant_emotion", ""))
        
        from collections import Counter
        emotion_counts = Counter(all_emotions)
        dominant_emotion = emotion_counts.most_common(1)[0][0] if emotion_counts else ""
        
        return {
            "has_data": True,
            "week_start": week_start_date,
            "week_end": end.strftime("%Y-%m-%d"),
            "review_count": len(reviews),
            "dominant_emotion": dominant_emotion,
            "top_blockers": list(set(all_blockers))[:5],
            "top_wins": list(set(all_wins))[:5],
            "pending_actions": list(set(all_next_actions))[:5],
            "emotion_distribution": dict(emotion_counts),
        }
