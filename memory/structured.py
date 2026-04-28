"""Structured long-term memory with slot updates and semantic retrieval."""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

try:
    from loguru import logger
except ImportError:  # pragma: no cover - local fallback for lightweight tests
    import logging

    logger = logging.getLogger(__name__)

from .base import BaseMemory
from .llm_extractor import RemoteLLMMemoryExtractor
from .semantic import BaseEmbedder, HashingEmbedder, cosine_similarity, tokenize_text
from .update_resolver import MemoryWriteDecision, RemoteLLMMemoryWriteResolver


_CITY_PATTERNS = (
    (
        "home_city",
        re.compile(r"(?:我(?:现在)?住在|住在|我家在|我目前在)(?P<value>[^，。,.!?；;\s]{1,12})"),
    ),
    ("home_city", re.compile(r"(?:我(?:最近)?搬到|搬到)(?P<value>[^，。,.!?；;\s]{1,12})")),
    ("work_city", re.compile(r"(?:我在)(?P<value>[^，。,.!?；;\s]{1,12})(?:工作|上班|读书)")),
)
_PERSONA_PATTERNS = (
    ("name", re.compile(r"(?:我叫|我的名字是)(?P<value>[\u4e00-\u9fffA-Za-z0-9·]{1,16})")),
    (
        "occupation",
        re.compile(
            r"(?:我是一名|我是一位|我是一个|我是|是一名|是一位|是一个|是)(?P<value>[^，。,.!?；;]{1,20}"
            r"(?:师|员|生|经理|者|顾问|老师|医生|律师|博主|主播))"
        ),
    ),
    ("age", re.compile(r"我今年(?P<value>\d{1,2})岁")),
)
_ENGLISH_PERSONA_PATTERNS = (
    ("name", re.compile(r"\b(?:my name is|i am|i'm)\s+(?P<value>[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b")),
    (
        "occupation",
        re.compile(
            r"\b(?:i am|i'm)\s+(?:an?\s+)?(?P<value>[a-z][a-z\s-]{1,30}"
            r"(?:nurse|doctor|teacher|engineer|designer|manager|artist|lawyer|student|writer|retiree|developer|mother|father))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "work_context",
        re.compile(r"\b(?:i work (?:in|at) the?|i work at)\s+(?P<value>[a-z0-9\s-]{2,40})\b", re.IGNORECASE),
    ),
    (
        "relationship_status",
        re.compile(
            r"\b(?:i am|i'm)\s+(?P<value>divorced|single|married|engaged|widowed|remarried)\b",
            re.IGNORECASE,
        ),
    ),
)
_ENGLISH_SLOT_FACT_PATTERNS = (
    (
        "preference",
        "living_preference",
        re.compile(r"\b(?:i want to live|i'd like to live|i would like to live)\s+(?:in|at)\s+(?P<value>.+)", re.IGNORECASE),
    ),
)
_NEGATIVE_PREF_MARKERS = ("不再喜欢", "不太喜欢", "不喜欢", "讨厌", "不能吃", "不吃", "喝不了")
_POSITIVE_PREF_MARKERS = ("最喜欢", "特别喜欢", "很喜欢", "偏爱", "喜欢", "爱", "更喜欢", "依然喜欢")
_ABILITY_PREF_MARKERS = ("能吃一点", "开始能吃", "现在能吃", "喝得了")
_ENGLISH_NEGATIVE_PREF_PATTERNS = (
    re.compile(r"\b(?:i don't like|i do not like|i dislike|i hate)\s+(?P<value>.+)", re.IGNORECASE),
)
_ENGLISH_POSITIVE_PREF_PATTERNS = (
    re.compile(
        r"\bmy favorite (?P<kind>drink|food|band|animal)(?:\s+now)? is\s+(?P<value>.+)",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:i love|i enjoy|i really like|i like)\s+(?P<value>.+)", re.IGNORECASE),
)
_TEMPORAL_CUES = ("今天", "昨天", "前天", "上周", "上个月", "最近", "刚刚", "刚才", "去年", "今年")
_EVENT_CUES = (
    "分手",
    "搬家",
    "搬到",
    "离职",
    "升职",
    "失眠",
    "睡不好",
    "睡不着",
    "焦虑",
    "压力",
    "难过",
    "孤独",
    "旅行",
    "见了",
    "去了",
    "开始",
    "结束",
    "完成",
    "生病",
)
_ENGLISH_TEMPORAL_CUES = (
    "today",
    "yesterday",
    "last week",
    "last month",
    "recently",
    "this weekend",
    "this week",
    "again",
    "remember how",
    "since then",
)
_ENGLISH_EVENT_CUES = (
    "divorce",
    "promotion",
    "shift",
    "miss the dinner",
    "overwhelmed",
    "anxious",
    "guilty",
    "frustrated",
    "community event",
    "book club",
    "hiking group",
    "coworker",
    "family dinner",
)
_TAG_RULES = {
    "relationship": ("分手", "男朋友", "女朋友", "伴侣", "恋爱", "感情"),
    "sleep": ("睡不好", "失眠", "睡不着", "熬夜"),
    "stress": ("焦虑", "压力", "崩溃", "紧张"),
    "career": ("工作", "加班", "面试", "离职", "升职"),
    "move": ("搬家", "搬到", "新城市", "租房"),
    "food": ("辣", "清淡", "咖啡", "拿铁", "奶茶", "吃"),
}
_ENGLISH_TAG_RULES = {
    "relationship": ("divorce", "partner", "boyfriend", "girlfriend", "family"),
    "sleep": ("sleep", "insomnia", "tired"),
    "stress": ("anxious", "stress", "overwhelmed", "frustrated", "guilty"),
    "career": ("work", "job", "shift", "hospital", "coworker", "promotion"),
    "move": ("move", "relocate", "new place"),
    "food": ("food", "drink", "recipe", "enchiladas", "honey", "pepper"),
    "community": ("community", "group", "book club", "potluck", "friends"),
}
_PREFERENCE_CATEGORIES = {
    "favorite_beverage": ("咖啡", "拿铁", "美式", "奶茶", "茶", "果汁"),
    "food_spice": ("辣", "川菜", "火锅"),
    "food_flavor": ("清淡", "甜", "酸", "咸"),
    "music_style": ("音乐", "摇滚", "古典", "爵士", "民谣"),
    "activity_style": ("跑步", "健身", "游泳", "瑜伽", "徒步", "旅行", "阅读"),
}
_ENGLISH_PREFERENCE_CATEGORIES = {
    "favorite_beverage": ("drink", "coffee", "tea", "pepper", "cola", "juice"),
    "favorite_food": ("food", "enchiladas", "honey", "recipe", "mexican food"),
    "music_style": ("band", "music", "jazz", "rock", "rolling stones"),
    "activity_style": ("yoga", "hiking", "reading", "cook", "cooking", "gardening", "travel", "walk", "walking"),
    "social_style": ("talking to strangers", "parties", "socializing", "gatherings"),
    "living_preference": ("beach", "rural", "suburban", "urban"),
}
_SLOT_LABELS = {
    "name": "姓名",
    "occupation": "职业",
    "age": "年龄",
    "home_city": "当前城市",
    "work_city": "工作/学习城市",
    "favorite_beverage": "饮品偏好",
    "food_spice": "辣度偏好",
    "food_flavor": "口味偏好",
    "music_style": "音乐偏好",
    "activity_style": "活动偏好",
    "favorite_food": "食物偏好",
    "social_style": "社交偏好",
    "living_preference": "居住偏好",
    "relationship_status": "关系状态",
    "work_context": "工作场景",
}
_QUESTION_WORDS = (
    "什么",
    "谁",
    "哪里",
    "哪儿",
    "哪个",
    "哪座",
    "几岁",
    "多大",
    "吗",
    "么",
    "what",
    "who",
    "where",
    "which",
    "how old",
)
_MEMORY_PROBE_PATTERNS = (
    r"^你还记得",
    r"^你记得",
    r"^还记得我",
    r"^我叫什么",
    r"^我住哪",
    r"^我住哪里",
    r"^我喜欢什么",
    r"^do you remember",
    r"^what do you remember",
    r"^can you remember",
    r"^what is my name",
    r"^where do i live",
)
_UNCERTAINTY_MARKERS = (
    "可能",
    "也许",
    "大概",
    "好像",
    "不确定",
    "maybe",
    "perhaps",
    "not sure",
    "i guess",
)
_UPDATE_CUES = (
    "其实",
    "现在",
    "后来",
    "已经",
    "不再",
    "改成",
    "改为",
    "搬到",
    "换成",
    "更喜欢",
    "anymore",
    "now",
    "actually",
    "moved to",
    "changed to",
)
_INVALID_GENERIC_VALUES = {
    "什么",
    "谁",
    "哪里",
    "哪儿",
    "哪个",
    "哪座",
    "啥",
    "几岁",
    "多大",
    "what",
    "who",
    "where",
    "which",
    "how",
}
_INVALID_SLOT_VALUE_PATTERNS = {
    "name": re.compile(r"^(什么|谁|what|who)$", re.IGNORECASE),
    "home_city": re.compile(r"^(哪里|哪儿|哪个地方|where)$", re.IGNORECASE),
    "work_city": re.compile(r"^(哪里|哪儿|哪个地方|where)$", re.IGNORECASE),
}


@dataclass
class SlotValue:
    key: str
    value: str
    updated_at: str
    source_memory_id: str
    confidence: float = 1.0
    first_seen_at: str = ""


@dataclass
class PreferenceProfileItem:
    key: str
    value: str
    normalized_value: str
    polarity: str
    scope: str
    status: str
    updated_at: str
    first_seen_at: str
    source_memory_id: str
    confidence: float = 1.0
    evidence_count: int = 1
    valid_from: str = ""
    valid_to: str = ""


@dataclass
class ConflictRecord:
    slot_key: str
    previous_value: str
    new_value: str
    resolved_to: str
    resolved_at: str
    reason: str


@dataclass
class MemoryItem:
    id: str
    memory_type: str
    summary: str
    content: str
    role: str
    created_at: str
    updated_at: str
    slot_key: Optional[str] = None
    value: Optional[str] = None
    status: str = "active"
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    vector: list[float] = field(default_factory=list)


@dataclass
class MemoryCandidate:
    memory_type: str
    summary: str
    value: str
    content: str
    slot_key: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class StructuredLongTermMemory(BaseMemory):
    """Structured slot memory with semantic recall and metadata filtering."""

    def __init__(
        self,
        file_path: Optional[str] = None,
        max_memories: int = 200,
        default_limit: int = 6,
        embedder: BaseEmbedder | None = None,
        candidate_extractor: Callable[[str], Awaitable[list[MemoryCandidate]]] | None = None,
        write_resolver: Callable[
            [str, MemoryCandidate, Any | None],
            Awaitable[MemoryWriteDecision],
        ]
        | None = None,
    ):
        self._file = Path(file_path or "long_term_memory_store.json")
        self._max_memories = max_memories
        self._default_limit = default_limit
        self._embedder = embedder or HashingEmbedder()
        self._candidate_extractor = candidate_extractor
        self._llm_extractor = RemoteLLMMemoryExtractor() if candidate_extractor is None else None
        self._write_resolver = write_resolver
        self._llm_write_resolver = (
            RemoteLLMMemoryWriteResolver() if write_resolver is None else None
        )
        self._persona_slots: dict[str, SlotValue] = {}
        self._preference_slots: dict[str, SlotValue] = {}
        self._preference_profiles: dict[str, list[PreferenceProfileItem]] = {}
        self._conflicts: list[ConflictRecord] = []
        self._memories: list[MemoryItem] = []
        self._load()

    async def store(self, role: str, content: str) -> None:
        content = content.strip()
        if role != "user" or not content:
            return

        timestamp = _utcnow()
        candidates = await self._extract_candidates_for_write(content)
        if not candidates and self._should_store_fallback_event(content):
            candidates = [
                MemoryCandidate(
                    memory_type="event",
                    summary=f"对话备注：{content}",
                    value=content,
                    content=content,
                    tags=self._extract_tags(content),
                )
            ]
        if not candidates:
            return

        changed = False
        for candidate in candidates:
            changed = await self._apply_candidate(candidate, role, timestamp) or changed

        if changed:
            self._trim_memories()
            self._save()

    async def retrieve(
        self,
        query: str = "",
        filters: dict[str, Any] | None = None,
        limit: int = 6,
    ) -> str:
        normalized_filters = self._normalize_filters(query, filters)
        effective_limit = limit or self._default_limit

        persona_lines = self._format_slots(
            self._persona_slots,
            query=query,
            slot_keys=normalized_filters.get("slot_keys"),
            limit=2,
        )
        preference_lines = self._format_slots(
            self._preference_slots,
            query=query,
            slot_keys=normalized_filters.get("slot_keys"),
            limit=3,
        )
        detailed_preference_lines = self._format_preference_profiles(
            query=query,
            slot_keys=normalized_filters.get("slot_keys"),
            limit=4,
        )
        memory_lines = self._format_memories(
            query=query,
            filters=normalized_filters,
            limit=effective_limit,
        )

        sections = []
        if persona_lines:
            sections.append("Persona slots:\n" + "\n".join(persona_lines))
        rendered_preferences = detailed_preference_lines or preference_lines
        if rendered_preferences:
            sections.append("Preference slots:\n" + "\n".join(rendered_preferences))
        if memory_lines:
            sections.append("Relevant long-term memories:\n" + "\n".join(memory_lines))

        if not sections:
            return ""

        return "[Long-term memory]\n" + "\n\n".join(sections)

    async def clear(self) -> None:
        self._persona_slots.clear()
        self._preference_slots.clear()
        self._preference_profiles.clear()
        self._conflicts.clear()
        self._memories.clear()
        if self._file.exists():
            self._file.unlink()
        logger.info("StructuredLongTermMemory: cleared persisted state")

    async def delete_memory(self, memory_id: str) -> MemoryItem | None:
        normalized_id = str(memory_id or "").strip()
        if not normalized_id:
            return None

        target = next((memory for memory in self._memories if memory.id == normalized_id), None)
        if target is None:
            return None

        if target.status == "deleted":
            return target

        target.status = "deleted"

        if target.memory_type == "persona" and target.slot_key:
            slot = self._persona_slots.get(target.slot_key)
            if slot and slot.source_memory_id == normalized_id:
                self._persona_slots.pop(target.slot_key, None)
        elif target.memory_type == "preference" and target.slot_key:
            deleted_at = _utcnow()
            for item in self._preference_profiles.get(target.slot_key, []):
                if item.source_memory_id != normalized_id:
                    continue
                item.status = "deleted"
                item.valid_to = deleted_at
            self._rebuild_preference_slots()

        self._save()
        logger.info("StructuredLongTermMemory: deleted memory {}", normalized_id)
        return target

    def snapshot(self) -> dict[str, Any]:
        """Debug view used by local tests and demos."""

        return {
            "persona_slots": {key: asdict(value) for key, value in self._persona_slots.items()},
            "preference_slots": {
                key: asdict(value) for key, value in self._preference_slots.items()
            },
            "preference_profiles": {
                key: [asdict(item) for item in items]
                for key, items in self._preference_profiles.items()
            },
            "conflicts": [asdict(conflict) for conflict in self._conflicts],
            "memories": [asdict(memory) for memory in self._memories],
        }

    async def _extract_candidates_for_write(self, content: str) -> list[MemoryCandidate]:
        if self._candidate_extractor is not None:
            extracted = await self._candidate_extractor(content)
            return self._dedupe_candidates(self._expand_preference_candidates(extracted))

        llm_candidates = await self._extract_candidates_with_llm(content)
        rule_candidates = self._extract_candidates_with_rules(content)
        if not llm_candidates:
            return self._dedupe_candidates(self._expand_preference_candidates(rule_candidates))

        merged_candidates = list(llm_candidates)
        seen_slot_keys = {
            (candidate.memory_type, candidate.slot_key)
            for candidate in llm_candidates
            if candidate.slot_key
        }
        has_event = any(candidate.memory_type == "event" for candidate in llm_candidates)

        for candidate in rule_candidates:
            if candidate.memory_type == "event":
                if not has_event:
                    merged_candidates.append(candidate)
                continue

            slot_identity = (candidate.memory_type, candidate.slot_key)
            if slot_identity not in seen_slot_keys:
                merged_candidates.append(candidate)

        return self._dedupe_candidates(self._expand_preference_candidates(merged_candidates))

    async def _extract_candidates_with_llm(self, content: str) -> list[MemoryCandidate]:
        if self._llm_extractor is None:
            return []

        raw_candidates = await self._llm_extractor.extract(content)
        candidates: list[MemoryCandidate] = []
        for item in raw_candidates:
            memory_type = str(item.get("memory_type", "")).strip().lower()
            if memory_type not in {"persona", "preference", "event"}:
                continue

            slot_key = item.get("slot_key")
            normalized_slot_key = self._clean_slot_key(slot_key)
            value = self._clean_value(str(item.get("value", "")).strip())
            summary = self._clean_value(str(item.get("summary", "")).strip())
            if memory_type in {"persona", "preference"} and (not normalized_slot_key or not value):
                continue
            if memory_type == "event" and not summary:
                summary = f"历史事件：{content}"
            if not value:
                value = content if memory_type == "event" else summary
            if not summary:
                summary = self._default_summary(memory_type, normalized_slot_key, value)

            tags = [
                str(tag).strip().lower()
                for tag in item.get("tags", [])
                if isinstance(tag, str) and str(tag).strip()
            ]
            merged_tags = []
            for tag in [*tags, *self._extract_tags(content)]:
                if tag not in merged_tags:
                    merged_tags.append(tag)

            metadata = item.get("metadata", {})
            if not isinstance(metadata, dict):
                metadata = {}
            metadata = {**metadata, "extraction_source": "llm"}

            candidates.append(
                MemoryCandidate(
                    memory_type=memory_type,
                    slot_key=normalized_slot_key,
                    value=value,
                    summary=summary,
                    content=content,
                    tags=merged_tags,
                    metadata=metadata,
                )
            )

        return candidates

    def _extract_candidates_with_rules(self, content: str) -> list[MemoryCandidate]:
        candidates: list[MemoryCandidate] = []

        for slot_key, pattern in _PERSONA_PATTERNS + _CITY_PATTERNS:
            match = pattern.search(content)
            if not match:
                continue
            value = self._clean_value(match.group("value"))
            candidates.append(
                MemoryCandidate(
                    memory_type="persona",
                    slot_key=slot_key,
                    value=value,
                    summary=f"用户{_SLOT_LABELS.get(slot_key, slot_key)}是{value}",
                    content=content,
                    tags=self._extract_tags(content),
                )
            )

        for slot_key, pattern in _ENGLISH_PERSONA_PATTERNS:
            match = pattern.search(content)
            if not match:
                continue
            value = self._clean_value(match.group("value"))
            if not value:
                continue
            candidates.append(
                MemoryCandidate(
                    memory_type="persona",
                    slot_key=slot_key,
                    value=value,
                    summary=f"User {_slot_label_en(slot_key)}: {value}",
                    content=content,
                    tags=self._extract_tags(content),
                )
            )

        for memory_type, slot_key, pattern in _ENGLISH_SLOT_FACT_PATTERNS:
            match = pattern.search(content)
            if not match:
                continue
            value = self._clean_value(match.group("value"))
            if not value:
                continue
            rendered_value = self._render_preference_value(slot_key, "positive", value)
            candidates.append(
                MemoryCandidate(
                    memory_type=memory_type,
                    slot_key=slot_key,
                    value=rendered_value,
                    summary=f"User {_slot_label_en(slot_key)}: {rendered_value}",
                    content=content,
                    tags=self._extract_tags(content),
                )
            )

        for clause in self._split_clauses(content):
            candidates.extend(self._extract_preference_candidates(clause, content))

        if self._looks_like_event(content):
            tags = self._extract_tags(content)
            candidates.append(
                MemoryCandidate(
                    memory_type="event",
                    summary=f"历史事件：{content}",
                    value=content,
                    content=content,
                    tags=tags,
                    metadata={"memory_scope": "cross_session"},
                )
            )

        return self._dedupe_candidates(candidates)

    def _extract_preference_candidates(
        self,
        clause: str,
        full_content: str,
    ) -> list[MemoryCandidate]:
        candidates: list[MemoryCandidate] = []
        cleaned_clause = clause.strip()
        if not cleaned_clause:
            return candidates

        polarity, marker = self._detect_preference_marker(cleaned_clause)
        if marker:
            phrase = self._clean_value(cleaned_clause.split(marker, 1)[1])
            if phrase:
                slot_key = self._infer_preference_slot(cleaned_clause + phrase)
                if not slot_key:
                    slot_key = f"general_{self._slugify(phrase)}"

                value = self._render_preference_value(slot_key, polarity, phrase)
                candidates.append(
                    MemoryCandidate(
                        memory_type="preference",
                        slot_key=slot_key,
                        value=value,
                        summary=f"用户{_SLOT_LABELS.get(slot_key, slot_key)}：{value}",
                        content=full_content,
                        tags=self._extract_tags(full_content),
                    )
                )

        candidates.extend(self._extract_english_preference_candidates(cleaned_clause, full_content))
        return candidates

    def _detect_preference_marker(self, clause: str) -> tuple[str, str]:
        for marker in _NEGATIVE_PREF_MARKERS:
            if marker in clause:
                return "negative", marker
        for marker in _ABILITY_PREF_MARKERS:
            if marker in clause:
                return "ability", marker
        for marker in _POSITIVE_PREF_MARKERS:
            if marker in clause:
                return "positive", marker
        return "", ""

    def _extract_english_preference_candidates(
        self,
        clause: str,
        full_content: str,
    ) -> list[MemoryCandidate]:
        candidates: list[MemoryCandidate] = []

        for pattern in _ENGLISH_NEGATIVE_PREF_PATTERNS:
            match = pattern.search(clause)
            if not match:
                continue
            phrase = self._clean_value(match.group("value"))
            slot_key = self._infer_preference_slot(clause + " " + phrase)
            if not slot_key:
                slot_key = f"general_{self._slugify(phrase)}"
            value = self._render_preference_value(slot_key, "negative", phrase)
            candidates.append(
                MemoryCandidate(
                    memory_type="preference",
                    slot_key=slot_key,
                    value=value,
                    summary=f"User {_slot_label_en(slot_key)}: {value}",
                    content=full_content,
                    tags=self._extract_tags(full_content),
                )
            )

        for pattern in _ENGLISH_POSITIVE_PREF_PATTERNS:
            match = pattern.search(clause)
            if not match:
                continue
            phrase = self._clean_value(match.group("value"))
            kind = self._clean_value(match.groupdict().get("kind", ""))
            seed_text = f"{clause} {phrase} {kind}"
            slot_key = self._infer_preference_slot(seed_text)
            if not slot_key and kind:
                slot_key = self._infer_preference_slot(kind)
            if not slot_key:
                slot_key = f"general_{self._slugify(phrase)}"
            value = self._render_preference_value(slot_key, "positive", phrase)
            candidates.append(
                MemoryCandidate(
                    memory_type="preference",
                    slot_key=slot_key,
                    value=value,
                    summary=f"User {_slot_label_en(slot_key)}: {value}",
                    content=full_content,
                    tags=self._extract_tags(full_content),
                )
            )

        return candidates

    def _expand_preference_candidates(
        self,
        candidates: list[MemoryCandidate],
    ) -> list[MemoryCandidate]:
        expanded: list[MemoryCandidate] = []
        for candidate in candidates:
            if candidate.memory_type != "preference" or not candidate.slot_key or not candidate.value:
                expanded.append(candidate)
                continue

            parsed = self._parse_preference_value(candidate.slot_key, candidate.value)
            normalized_items = parsed["normalized_items"]
            if not normalized_items:
                expanded.append(candidate)
                continue

            for normalized_item in normalized_items:
                canonical_value = self._compose_preference_value(
                    candidate.slot_key,
                    parsed["polarity"],
                    normalized_item,
                )
                if not canonical_value:
                    continue
                expanded.append(
                    MemoryCandidate(
                        memory_type=candidate.memory_type,
                        slot_key=candidate.slot_key,
                        value=canonical_value,
                        summary=self._default_summary(
                            candidate.memory_type,
                            candidate.slot_key,
                            canonical_value,
                        ),
                        content=candidate.content,
                        tags=candidate.tags,
                        metadata=candidate.metadata,
                    )
                )

        return expanded

    def _infer_preference_slot(self, text: str) -> str:
        for slot_key, keywords in _PREFERENCE_CATEGORIES.items():
            if any(keyword in text for keyword in keywords):
                return slot_key
        lowered = text.lower()
        for slot_key, keywords in _ENGLISH_PREFERENCE_CATEGORIES.items():
            if any(keyword in lowered for keyword in keywords):
                return slot_key
        return ""

    def _render_preference_value(self, slot_key: str, polarity: str, phrase: str) -> str:
        phrase_lower = phrase.lower()
        if slot_key == "food_spice":
            if "清淡" in phrase:
                return "更喜欢清淡"
            if polarity == "negative":
                return self._compose_preference_value(slot_key, "avoid", "辣")
            if polarity == "ability":
                return self._compose_preference_value(slot_key, "accept", "辣")
            if "spicy" in phrase_lower:
                return self._compose_preference_value(slot_key, "like", "spicy food")
            return self._compose_preference_value(slot_key, "like", "偏辣口味")
        if slot_key == "food_flavor":
            if "清淡" in phrase:
                return "更喜欢清淡"
        mapped_polarity = {
            "positive": "like",
            "negative": "dislike",
            "ability": "accept",
        }.get(polarity, "like")
        return self._compose_preference_value(slot_key, mapped_polarity, phrase)

    async def _apply_candidate(
        self,
        candidate: MemoryCandidate,
        role: str,
        timestamp: str,
    ) -> bool:
        if candidate.memory_type == "persona" and candidate.slot_key:
            return await self._upsert_slot_candidate(candidate, role, timestamp)
        if candidate.memory_type == "preference" and candidate.slot_key:
            return await self._upsert_preference_candidate(candidate, role, timestamp)
        return self._append_memory(candidate, role, timestamp)

    async def _upsert_slot_candidate(
        self,
        candidate: MemoryCandidate,
        role: str,
        timestamp: str,
    ) -> bool:
        slot_map = (
            self._persona_slots if candidate.memory_type == "persona" else self._preference_slots
        )
        existing = slot_map.get(candidate.slot_key)
        decision = await self._resolve_write_decision(candidate, existing)
        if decision.decision == "noop":
            return False

        if decision.decision == "delete":
            if not existing:
                return False
            self._mark_memory_status(existing.source_memory_id, "deleted")
            slot_map.pop(candidate.slot_key, None)
            self._conflicts.append(
                ConflictRecord(
                    slot_key=candidate.slot_key,
                    previous_value=existing.value,
                    new_value="",
                    resolved_to="",
                    resolved_at=timestamp,
                    reason=decision.reason or "explicit_delete",
                )
            )
            return True

        resolved_value = self._clean_value(decision.resolved_value or candidate.value)
        if not resolved_value or self._is_invalid_slot_value(candidate.slot_key, resolved_value):
            return False

        if existing and self._values_equivalent(existing.value, resolved_value):
            existing.updated_at = timestamp
            return False

        memory_id = self._create_memory_id()
        if existing:
            self._mark_memory_status(existing.source_memory_id, "superseded")
            self._conflicts.append(
                ConflictRecord(
                    slot_key=candidate.slot_key,
                    previous_value=existing.value,
                    new_value=resolved_value,
                    resolved_to=resolved_value,
                    resolved_at=timestamp,
                    reason=decision.reason or "latest_user_statement",
                )
            )

        slot_map[candidate.slot_key] = SlotValue(
            key=candidate.slot_key,
            value=resolved_value,
            updated_at=timestamp,
            first_seen_at=existing.first_seen_at if existing else timestamp,
            source_memory_id=memory_id,
        )
        resolved_candidate = MemoryCandidate(
            memory_type=candidate.memory_type,
            summary=self._default_summary(candidate.memory_type, candidate.slot_key, resolved_value),
            value=resolved_value,
            content=candidate.content,
            slot_key=candidate.slot_key,
            tags=candidate.tags,
            metadata={
                **candidate.metadata,
                "write_decision": decision.decision,
                "write_reason": decision.reason,
            },
        )
        memory = self._candidate_to_memory(resolved_candidate, role, timestamp, memory_id)
        self._memories.append(memory)
        return True

    async def _upsert_preference_candidate(
        self,
        candidate: MemoryCandidate,
        role: str,
        timestamp: str,
    ) -> bool:
        active_items = self._active_preference_items(candidate.slot_key)
        matching_item = self._find_matching_preference_item(candidate.slot_key, candidate.value)
        covering_item = self._find_covering_preference_item(candidate.slot_key, candidate.value)
        related_items = self._find_related_preference_items(candidate.slot_key, candidate.value)
        representative_existing = matching_item or covering_item or (
            related_items[-1] if related_items else None
        )

        if covering_item and self._same_preference_polarity(covering_item.value, candidate.value):
            covering_item.evidence_count += 1
            covering_item.updated_at = timestamp
            self._rebuild_preference_slots()
            return False

        decision = await self._resolve_preference_write_decision(candidate, representative_existing)
        if decision.decision == "noop":
            existing_item = matching_item or covering_item
            if existing_item:
                existing_item.evidence_count += 1
                existing_item.updated_at = timestamp
                self._rebuild_preference_slots()
            return False

        if decision.decision == "delete":
            target_items = related_items or ([representative_existing] if representative_existing else [])
            if not target_items:
                return False
            for item in target_items:
                self._mark_memory_status(item.source_memory_id, "deleted")
                item.status = "deleted"
                item.valid_to = timestamp
            self._rebuild_preference_slots()
            return True

        resolved_value = self._clean_value(decision.resolved_value or candidate.value)
        if not resolved_value or self._is_invalid_slot_value(candidate.slot_key, resolved_value):
            return False

        if matching_item and self._preference_values_equivalent(matching_item.value, resolved_value):
            matching_item.evidence_count += 1
            matching_item.updated_at = timestamp
            self._rebuild_preference_slots()
            return False

        target_items = related_items or ([representative_existing] if representative_existing else [])
        if decision.decision == "update":
            if not target_items:
                decision = MemoryWriteDecision(
                    decision="add",
                    resolved_value=resolved_value,
                    reason=decision.reason or "coexisting_preference",
                )
            for item in target_items:
                self._retain_split_preference_residuals(
                    item,
                    resolved_value,
                    role,
                    timestamp,
                )
                self._mark_memory_status(item.source_memory_id, "superseded")
                item.status = "historical"
                item.valid_to = timestamp
                self._conflicts.append(
                    ConflictRecord(
                        slot_key=candidate.slot_key,
                        previous_value=item.value,
                        new_value=resolved_value,
                        resolved_to=resolved_value,
                        resolved_at=timestamp,
                        reason=decision.reason or "preference_superseded",
                    )
                )

        memory_id = self._create_memory_id()
        parsed = self._parse_preference_value(candidate.slot_key, resolved_value)
        item = PreferenceProfileItem(
            key=candidate.slot_key,
            value=resolved_value,
            normalized_value=parsed["normalized_value"],
            polarity=parsed["polarity"],
            scope=self._infer_preference_scope(candidate.content),
            status="active",
            updated_at=timestamp,
            first_seen_at=timestamp,
            source_memory_id=memory_id,
            confidence=1.0,
            evidence_count=1,
            valid_from=timestamp,
        )
        self._preference_profiles.setdefault(candidate.slot_key, []).append(item)

        resolved_candidate = MemoryCandidate(
            memory_type=candidate.memory_type,
            summary=self._default_summary(candidate.memory_type, candidate.slot_key, resolved_value),
            value=resolved_value,
            content=candidate.content,
            slot_key=candidate.slot_key,
            tags=candidate.tags,
            metadata={
                **candidate.metadata,
                "write_decision": decision.decision,
                "write_reason": decision.reason,
                "scope": item.scope,
                "polarity": item.polarity,
                "normalized_value": item.normalized_value,
            },
        )
        self._memories.append(self._candidate_to_memory(resolved_candidate, role, timestamp, memory_id))
        self._rebuild_preference_slots()
        return True

    def _append_memory(self, candidate: MemoryCandidate, role: str, timestamp: str) -> bool:
        if self._is_duplicate_event(candidate):
            return False
        memory = self._candidate_to_memory(candidate, role, timestamp, self._create_memory_id())
        self._memories.append(memory)
        return True

    def _candidate_to_memory(
        self,
        candidate: MemoryCandidate,
        role: str,
        timestamp: str,
        memory_id: str,
    ) -> MemoryItem:
        vector_text = " ".join([candidate.summary, candidate.value, *candidate.tags])
        return MemoryItem(
            id=memory_id,
            memory_type=candidate.memory_type,
            summary=candidate.summary,
            value=candidate.value,
            content=candidate.content,
            role=role,
            created_at=timestamp,
            updated_at=timestamp,
            slot_key=candidate.slot_key,
            tags=candidate.tags,
            metadata=candidate.metadata,
            vector=self._embedder.embed(vector_text),
        )

    def _format_slots(
        self,
        slot_map: dict[str, SlotValue],
        query: str,
        slot_keys: set[str],
        limit: int,
    ) -> list[str]:
        if not slot_map:
            return []

        query_tokens = set(tokenize_text(query))
        scored = []
        for slot in slot_map.values():
            score = 0.1
            if not query:
                score = 0.5
            if slot.key in slot_keys:
                score += 1.0
            slot_tokens = set(tokenize_text(f"{slot.key} {slot.value} {_SLOT_LABELS.get(slot.key, '')}"))
            overlap = len(query_tokens & slot_tokens)
            score += overlap * 0.2
            scored.append((score, slot))

        scored.sort(key=lambda item: (item[0], item[1].updated_at), reverse=True)
        lines = []
        for _, slot in scored[:limit]:
            label = _SLOT_LABELS.get(slot.key, slot.key)
            lines.append(f"- {label}: {slot.value}")
        return lines

    def _format_preference_profiles(
        self,
        query: str,
        slot_keys: set[str],
        limit: int,
    ) -> list[str]:
        query_tokens = set(tokenize_text(query))
        scored: list[tuple[float, PreferenceProfileItem]] = []
        for key, items in self._preference_profiles.items():
            for item in items:
                if item.status != "active":
                    continue
                if slot_keys and key not in slot_keys:
                    continue
                score = 0.25 if not query else 0.0
                if key in slot_keys:
                    score += 1.0
                text = f"{key} {item.value} {item.scope} {_SLOT_LABELS.get(key, '')}"
                overlap = len(query_tokens & set(tokenize_text(text)))
                score += overlap * 0.2
                score += item.evidence_count * 0.03
                scored.append((score, item))

        if not scored:
            return []

        scored.sort(key=lambda pair: (pair[0], pair[1].updated_at), reverse=True)
        lines = []
        for _, item in scored[:limit]:
            label = _SLOT_LABELS.get(item.key, item.key)
            qualifier = f" ({self._render_scope_label(item.scope)})" if item.scope != "global" else ""
            lines.append(f"- {label}{qualifier}: {item.value}")
        return lines

    def _format_memories(
        self,
        query: str,
        filters: dict[str, Any],
        limit: int,
    ) -> list[str]:
        results = self._search_memories(query, filters, limit)
        lines = []
        for memory in results:
            prefix = {
                "persona": "persona",
                "preference": "preference",
                "event": "event",
            }.get(memory.memory_type, "memory")
            lines.append(f"- [{prefix}|{memory.updated_at[:10]}] {memory.summary}")
        return lines

    def _search_memories(
        self,
        query: str,
        filters: dict[str, Any],
        limit: int,
    ) -> list[MemoryItem]:
        if not self._memories:
            return []

        query_vector = self._embedder.embed(query or "user history")
        query_tokens = set(tokenize_text(query))
        scene = str(filters.get("scene") or "")
        scored: list[tuple[float, MemoryItem]] = []

        for memory in self._memories:
            if not self._matches_filters(memory, filters):
                continue

            score = 0.0
            if query:
                score += cosine_similarity(query_vector, memory.vector) * 0.75
                memory_tokens = set(tokenize_text(f"{memory.summary} {' '.join(memory.tags)}"))
                score += len(query_tokens & memory_tokens) * 0.08
            if memory.slot_key and memory.slot_key in filters.get("slot_keys", set()):
                score += 0.35
            if memory.memory_type == "event":
                score += 0.1
            if memory.status == "active":
                score += 0.05
            score += self._scene_memory_boost(scene, memory)
            score += self._freshness_score(memory.updated_at)
            scored.append((score, memory))

        scored.sort(key=lambda item: (item[0], item[1].updated_at), reverse=True)
        return [memory for _, memory in scored[:limit]]

    def _matches_filters(self, memory: MemoryItem, filters: dict[str, Any]) -> bool:
        allowed_types: set[str] = filters.get("memory_types", set())
        if allowed_types and memory.memory_type not in allowed_types:
            return False

        slot_keys: set[str] = filters.get("slot_keys", set())
        if slot_keys and memory.slot_key and memory.slot_key not in slot_keys:
            return False

        if filters.get("active_only") and memory.status != "active":
            return False

        return True

    def _normalize_filters(
        self,
        query: str,
        filters: dict[str, Any] | None,
    ) -> dict[str, Any]:
        merged = {
            "memory_types": {"persona", "preference", "event"},
            "slot_keys": set(),
            "active_only": True,
            "scene": "",
        }
        if filters:
            merged["memory_types"] = set(filters.get("memory_types", merged["memory_types"]))
            merged["slot_keys"] = set(filters.get("slot_keys", merged["slot_keys"]))
            if "active_only" in filters:
                merged["active_only"] = bool(filters["active_only"])
            if "scene" in filters:
                merged["scene"] = str(filters.get("scene") or "")

        if any(keyword in query for keyword in ("喜欢", "偏好", "推荐", "想吃", "口味")):
            merged["memory_types"] = {"preference", "event"}
        if any(keyword in query for keyword in ("住", "工作", "名字", "叫", "职业", "我是谁")):
            merged["memory_types"] = {"persona", "event"}
        if any(keyword in query for keyword in ("上次", "之前", "最近", "那天", "心情", "发生")):
            merged["memory_types"].add("event")

        if any(keyword in query for keyword in ("住", "城市")):
            merged["slot_keys"].add("home_city")
        if any(keyword in query for keyword in ("工作", "职业")):
            merged["slot_keys"].add("occupation")
        if any(keyword in query for keyword in ("饮料", "咖啡", "喝")):
            merged["slot_keys"].add("favorite_beverage")
        if any(keyword in query for keyword in ("辣", "清淡", "吃", "口味")):
            merged["slot_keys"].update({"food_spice", "food_flavor"})

        return merged

    def _scene_memory_boost(self, scene: str, memory: MemoryItem) -> float:
        if not scene:
            return 0.0

        if scene == "emotional_support":
            if memory.memory_type == "event":
                return 0.25
            if memory.slot_key in {"relationship_status", "work_context", "social_style"}:
                return 0.2
            if any(tag in {"stress", "sleep", "relationship"} for tag in memory.tags):
                return 0.15

        if scene == "smalltalk":
            if memory.memory_type == "persona":
                return 0.2
            if memory.memory_type == "event":
                return 0.12

        if scene == "memory_probe":
            if memory.memory_type in {"persona", "preference"}:
                return 0.28
            if memory.memory_type == "event":
                return 0.1

        if scene == "task_execution" and memory.memory_type == "preference":
            return 0.18

        return 0.0

    def _split_clauses(self, text: str) -> list[str]:
        return [part.strip() for part in re.split(r"[，,。；;！!？?\n]", text) if part.strip()]

    def _looks_like_event(self, content: str) -> bool:
        lowered = content.lower()
        return any(cue in content for cue in _TEMPORAL_CUES + _EVENT_CUES) or any(
            cue in lowered for cue in _ENGLISH_TEMPORAL_CUES + _ENGLISH_EVENT_CUES
        )

    def _extract_tags(self, text: str) -> list[str]:
        lowered = text.lower()
        tags = []
        for tag, keywords in _TAG_RULES.items():
            if any(keyword in text for keyword in keywords):
                tags.append(tag)
        for tag, keywords in _ENGLISH_TAG_RULES.items():
            if any(keyword in lowered for keyword in keywords) and tag not in tags:
                tags.append(tag)
        return tags

    def _dedupe_candidates(self, candidates: list[MemoryCandidate]) -> list[MemoryCandidate]:
        seen = set()
        unique = []
        for candidate in candidates:
            key = (candidate.memory_type, candidate.slot_key, candidate.value)
            if key in seen:
                continue
            seen.add(key)
            unique.append(candidate)
        return unique

    def _is_duplicate_event(self, candidate: MemoryCandidate) -> bool:
        if candidate.memory_type != "event":
            return False
        for memory in reversed(self._memories[-10:]):
            if memory.memory_type != "event":
                continue
            if memory.content == candidate.content:
                return True
        return False

    def _mark_memory_status(self, memory_id: str, status: str) -> None:
        for memory in self._memories:
            if memory.id == memory_id:
                memory.status = status
                return

    def _trim_memories(self) -> None:
        if len(self._memories) <= self._max_memories:
            return

        protected_ids = {slot.source_memory_id for slot in self._persona_slots.values()}
        protected_ids.update(
            item.source_memory_id
            for items in self._preference_profiles.values()
            for item in items
            if item.status == "active"
        )
        removable = [memory for memory in self._memories if memory.id not in protected_ids]
        removable.sort(key=lambda memory: memory.updated_at)
        while len(self._memories) > self._max_memories and removable:
            victim = removable.pop(0)
            self._memories = [memory for memory in self._memories if memory.id != victim.id]

    def _clean_value(self, value: str) -> str:
        cleaned = value.strip().strip("，,。！？；; ")
        if len(cleaned) > 1 and cleaned.endswith(("了", "呢", "呀", "啊")):
            cleaned = cleaned[:-1]
        return cleaned.strip()

    async def _resolve_write_decision(
        self,
        candidate: MemoryCandidate,
        existing: SlotValue | None,
    ) -> MemoryWriteDecision:
        local_decision = self._resolve_write_decision_locally(candidate, existing)
        if local_decision.decision == "noop":
            return local_decision

        should_use_llm = existing is not None or self._message_needs_extra_validation(candidate.content)
        if self._write_resolver is not None:
            resolved = await self._write_resolver(candidate.content, candidate, existing)
            return self._normalize_write_decision(candidate, existing, resolved, fallback=local_decision)
        if should_use_llm and self._llm_write_resolver and self._llm_write_resolver.is_configured():
            resolved = await self._llm_write_resolver.resolve(
                content=candidate.content,
                memory_type=candidate.memory_type,
                slot_key=candidate.slot_key or "",
                candidate_value=candidate.value,
                existing_value=existing.value if existing else None,
            )
            return self._normalize_write_decision(candidate, existing, resolved, fallback=local_decision)
        return local_decision

    async def _resolve_preference_write_decision(
        self,
        candidate: MemoryCandidate,
        existing: PreferenceProfileItem | None,
    ) -> MemoryWriteDecision:
        local_decision = self._resolve_preference_write_decision_locally(candidate, existing)
        if local_decision.decision == "noop":
            return local_decision

        should_use_llm = (
            existing is not None
            and (self._contains_update_cue(candidate.content) or self._message_needs_extra_validation(candidate.content))
        )
        if self._write_resolver is not None:
            resolved = await self._write_resolver(candidate.content, candidate, None)
            return self._normalize_preference_write_decision(candidate, existing, resolved, fallback=local_decision)
        if should_use_llm and self._llm_write_resolver and self._llm_write_resolver.is_configured():
            resolved = await self._llm_write_resolver.resolve(
                content=candidate.content,
                memory_type=candidate.memory_type,
                slot_key=candidate.slot_key or "",
                candidate_value=candidate.value,
                existing_value=existing.value if existing else None,
            )
            return self._normalize_preference_write_decision(candidate, existing, resolved, fallback=local_decision)
        return local_decision

    def _resolve_write_decision_locally(
        self,
        candidate: MemoryCandidate,
        existing: SlotValue | None,
    ) -> MemoryWriteDecision:
        content = candidate.content
        if self._looks_like_memory_probe(content):
            return MemoryWriteDecision(decision="noop", reason="memory_probe")
        if self._is_invalid_slot_value(candidate.slot_key, candidate.value):
            return MemoryWriteDecision(decision="noop", reason="invalid_candidate_value")
        if self._is_uncertain_statement(content):
            return MemoryWriteDecision(decision="noop", reason="uncertain_statement")
        if self._looks_like_question(content) and not self._contains_explicit_fact(candidate):
            return MemoryWriteDecision(decision="noop", reason="question_without_fact")
        if existing and self._values_equivalent(existing.value, candidate.value):
            return MemoryWriteDecision(
                decision="noop",
                resolved_value=existing.value,
                reason="same_value",
            )
        if existing is None:
            return MemoryWriteDecision(
                decision="add",
                resolved_value=candidate.value,
                reason="new_slot",
            )
        if self._contains_delete_cue(content):
            return MemoryWriteDecision(decision="delete", reason="explicit_delete")
        if self._contains_update_cue(content) or self._contains_explicit_fact(candidate):
            return MemoryWriteDecision(
                decision="update",
                resolved_value=candidate.value,
                reason="explicit_user_statement",
            )
        return MemoryWriteDecision(decision="noop", reason="needs_more_evidence")

    def _resolve_preference_write_decision_locally(
        self,
        candidate: MemoryCandidate,
        existing: PreferenceProfileItem | None,
    ) -> MemoryWriteDecision:
        content = candidate.content
        if self._looks_like_memory_probe(content):
            return MemoryWriteDecision(decision="noop", reason="memory_probe")
        if self._is_invalid_slot_value(candidate.slot_key, candidate.value):
            return MemoryWriteDecision(decision="noop", reason="invalid_candidate_value")
        if self._is_uncertain_statement(content):
            return MemoryWriteDecision(decision="noop", reason="uncertain_statement")
        if self._looks_like_question(content) and not self._contains_explicit_fact(candidate):
            return MemoryWriteDecision(decision="noop", reason="question_without_fact")
        if existing and self._preference_values_equivalent(existing.value, candidate.value):
            return MemoryWriteDecision(decision="noop", resolved_value=existing.value, reason="same_preference")
        if self._contains_delete_cue(content) and not self._contains_explicit_fact(candidate):
            return MemoryWriteDecision(decision="delete", reason="explicit_delete")
        if existing and (
            self._contains_update_cue(content)
            or self._preference_subjects_overlap(existing.value, candidate.value)
        ):
            return MemoryWriteDecision(decision="update", resolved_value=candidate.value, reason="preference_shift")
        return MemoryWriteDecision(decision="add", resolved_value=candidate.value, reason="coexisting_preference")

    def _normalize_write_decision(
        self,
        candidate: MemoryCandidate,
        existing: SlotValue | None,
        decision: MemoryWriteDecision,
        *,
        fallback: MemoryWriteDecision,
    ) -> MemoryWriteDecision:
        action = str(decision.decision or "").strip().lower()
        if action not in {"add", "update", "delete", "noop"}:
            return fallback
        resolved_value = self._clean_value(decision.resolved_value or candidate.value)
        if action in {"add", "update"} and (
            not resolved_value or self._is_invalid_slot_value(candidate.slot_key, resolved_value)
        ):
            return MemoryWriteDecision(decision="noop", reason="invalid_resolved_value")
        if existing and action in {"add", "update"} and self._values_equivalent(existing.value, resolved_value):
            return MemoryWriteDecision(
                decision="noop",
                resolved_value=existing.value,
                reason="same_value",
            )
        if not existing and action == "update":
            action = "add"
        if existing and action == "add":
            action = "update"
        return MemoryWriteDecision(
            decision=action,
            resolved_value=resolved_value,
            reason=decision.reason or fallback.reason,
        )

    def _normalize_preference_write_decision(
        self,
        candidate: MemoryCandidate,
        existing: PreferenceProfileItem | None,
        decision: MemoryWriteDecision,
        *,
        fallback: MemoryWriteDecision,
    ) -> MemoryWriteDecision:
        action = str(decision.decision or "").strip().lower()
        if action not in {"add", "update", "delete", "noop"}:
            return fallback
        resolved_value = self._clean_value(decision.resolved_value or candidate.value)
        if action in {"add", "update"} and (
            not resolved_value or self._is_invalid_slot_value(candidate.slot_key, resolved_value)
        ):
            return MemoryWriteDecision(decision="noop", reason="invalid_resolved_value")
        if existing and action in {"add", "update"} and self._preference_values_equivalent(existing.value, resolved_value):
            return MemoryWriteDecision(decision="noop", resolved_value=existing.value, reason="same_preference")
        if not existing and action == "update":
            action = "add"
        return MemoryWriteDecision(
            decision=action,
            resolved_value=resolved_value,
            reason=decision.reason or fallback.reason,
        )

    def _should_store_fallback_event(self, content: str) -> bool:
        return self._looks_like_event(content) and not self._looks_like_memory_probe(content)

    def _message_needs_extra_validation(self, content: str) -> bool:
        return self._looks_like_question(content) or self._is_uncertain_statement(content)

    def _looks_like_question(self, content: str) -> bool:
        lowered = content.strip().lower()
        if "?" in content or "？" in content:
            return True
        if any(lowered.startswith(prefix.replace("^", "")) for prefix in ("what", "who", "where", "do you", "can you")):
            return True
        return any(word in lowered for word in _QUESTION_WORDS)

    def _looks_like_memory_probe(self, content: str) -> bool:
        text = content.strip().lower()
        return any(re.search(pattern, text) for pattern in _MEMORY_PROBE_PATTERNS)

    def _is_uncertain_statement(self, content: str) -> bool:
        lowered = content.lower()
        return any(marker in content or marker in lowered for marker in _UNCERTAINTY_MARKERS)

    def _contains_update_cue(self, content: str) -> bool:
        lowered = content.lower()
        return any(cue in content or cue in lowered for cue in _UPDATE_CUES)

    def _contains_delete_cue(self, content: str) -> bool:
        lowered = content.lower()
        delete_cues = ("不再", "不喜欢了", "已经不是", "已经不", "no longer", "not anymore")
        return any(cue in content or cue in lowered for cue in delete_cues)

    def _contains_explicit_fact(self, candidate: MemoryCandidate) -> bool:
        content = candidate.content
        value = candidate.value
        if self._is_invalid_slot_value(candidate.slot_key, value):
            return False
        if candidate.slot_key == "name":
            return bool(re.search(r"(?:我叫|我的名字是)", content))
        if candidate.slot_key in {"home_city", "work_city"}:
            return bool(re.search(r"(?:我(?:现在)?住在|我家在|我目前在|我(?:最近)?搬到|我在)", content))
        if candidate.memory_type == "preference":
            return bool(
                any(marker in content for marker in _POSITIVE_PREF_MARKERS + _NEGATIVE_PREF_MARKERS)
                or re.search(r"\b(?:i like|i love|i enjoy|my favorite)\b", content, re.IGNORECASE)
            )
        if candidate.memory_type == "persona":
            persona_fact_patterns = {
                "occupation": r"(?:我是一名|我是一位|我是一个|我是|my name is|i am|i'm)",
                "age": r"(?:我今年\d{1,2}岁|\bi am \d{1,2}\b)",
                "relationship_status": r"\b(?:i am|i'm)\s+(?:single|married|engaged|widowed|divorced|remarried)\b",
                "work_context": r"\b(?:i work (?:in|at)|i work at)\b",
            }
            pattern = persona_fact_patterns.get(candidate.slot_key or "")
            return bool(re.search(pattern, content, re.IGNORECASE)) if pattern else False
        return False

    def _is_invalid_slot_value(self, slot_key: str | None, value: str) -> bool:
        cleaned = self._clean_value(value).strip().lower()
        if not cleaned:
            return True
        if cleaned in _INVALID_GENERIC_VALUES:
            return True
        if slot_key and slot_key in _INVALID_SLOT_VALUE_PATTERNS:
            return bool(_INVALID_SLOT_VALUE_PATTERNS[slot_key].match(cleaned))
        if "?" in cleaned or "？" in cleaned:
            return True
        if re.fullmatch(r"(what|who|where|which|how|怎么|为什么|什么样)", cleaned, re.IGNORECASE):
            return True
        return False

    def _values_equivalent(self, left: str, right: str) -> bool:
        return self._clean_value(left).casefold() == self._clean_value(right).casefold()

    def _preference_values_equivalent(self, left: str, right: str) -> bool:
        left_parsed = self._parse_preference_value("", left)
        right_parsed = self._parse_preference_value("", right)
        return (
            left_parsed["polarity"] == right_parsed["polarity"]
            and set(left_parsed["normalized_items"]) == set(right_parsed["normalized_items"])
        )

    def _active_preference_items(self, slot_key: str | None) -> list[PreferenceProfileItem]:
        if not slot_key:
            return []
        items = self._preference_profiles.get(slot_key, [])
        return [item for item in items if item.status == "active"]

    def _find_matching_preference_item(
        self,
        slot_key: str | None,
        value: str,
    ) -> PreferenceProfileItem | None:
        for item in self._active_preference_items(slot_key):
            if self._preference_values_equivalent(item.value, value):
                return item
        return None

    def _find_covering_preference_item(
        self,
        slot_key: str | None,
        value: str,
    ) -> PreferenceProfileItem | None:
        candidate_parsed = self._parse_preference_value(slot_key or "", value)
        candidate_items = set(candidate_parsed["normalized_items"])
        if not candidate_items:
            return None

        for item in self._active_preference_items(slot_key):
            item_parsed = self._parse_preference_value(slot_key or "", item.value)
            item_items = set(item_parsed["normalized_items"])
            if (
                item_parsed["polarity"] == candidate_parsed["polarity"]
                and candidate_items.issubset(item_items)
            ):
                return item
        return None

    def _find_related_preference_items(
        self,
        slot_key: str | None,
        value: str,
    ) -> list[PreferenceProfileItem]:
        candidate_parsed = self._parse_preference_value(slot_key or "", value)
        candidate_items = set(candidate_parsed["normalized_items"])
        if not candidate_items:
            return []

        related: list[PreferenceProfileItem] = []
        for item in self._active_preference_items(slot_key):
            item_parsed = self._parse_preference_value(slot_key or "", item.value)
            item_items = set(item_parsed["normalized_items"])
            if candidate_items & item_items:
                related.append(item)
        return related

    def _infer_preference_scope(self, content: str) -> str:
        lowered = content.lower()
        scope_rules = (
            ("breakfast", ("早餐", "早上", "morning", "breakfast")),
            ("nighttime", ("晚上", "夜里", "睡前", "night", "evening", "before bed")),
            ("workday", ("工作日", "上班", "workday", "at work")),
            ("weekend", ("周末", "weekend")),
            ("with_friends", ("和朋友", "聚会", "with friends")),
            ("alone", ("自己一个人", "独处", "alone", "by myself")),
        )
        for scope, keywords in scope_rules:
            if any(keyword in content or keyword in lowered for keyword in keywords):
                return scope
        return "global"

    def _render_scope_label(self, scope: str) -> str:
        return {
            "global": "长期",
            "breakfast": "早餐",
            "nighttime": "晚上",
            "workday": "工作时",
            "weekend": "周末",
            "with_friends": "和朋友一起时",
            "alone": "独处时",
        }.get(scope, scope)

    def _parse_preference_value(self, slot_key: str, value: str) -> dict[str, Any]:
        cleaned = self._clean_value(value)
        lowered = cleaned.lower()
        polarity = "like"
        normalized = cleaned
        if lowered.startswith("doesn't like "):
            polarity = "dislike"
            normalized = cleaned[13:].strip()
        elif lowered.startswith("likes "):
            polarity = "like"
            normalized = cleaned[6:].strip()
        elif lowered.startswith("dislike "):
            polarity = "dislike"
            normalized = cleaned[8:].strip()
        elif lowered.startswith("dislikes "):
            polarity = "dislike"
            normalized = cleaned[9:].strip()
        elif lowered.startswith("hate "):
            polarity = "dislike"
            normalized = cleaned[5:].strip()
        elif lowered.startswith("hates "):
            polarity = "dislike"
            normalized = cleaned[6:].strip()
        elif lowered.startswith("love "):
            polarity = "like"
            normalized = cleaned[5:].strip()
        elif lowered.startswith("loves "):
            polarity = "like"
            normalized = cleaned[6:].strip()
        elif lowered.startswith("enjoy "):
            polarity = "like"
            normalized = cleaned[6:].strip()
        elif lowered.startswith("enjoys "):
            polarity = "like"
            normalized = cleaned[7:].strip()
        elif lowered.startswith("prefer "):
            polarity = "prefer"
            normalized = cleaned[7:].strip()
        elif lowered.startswith("prefers "):
            polarity = "prefer"
            normalized = cleaned[8:].strip()
        elif cleaned.startswith("讨厌"):
            polarity = "dislike"
            normalized = cleaned.removeprefix("讨厌").strip()
        elif cleaned.startswith("不喜欢"):
            polarity = "dislike"
            normalized = cleaned.removeprefix("不喜欢").strip()
        elif cleaned.startswith("更喜欢"):
            polarity = "prefer"
            normalized = cleaned.removeprefix("更喜欢").strip()
        elif cleaned.startswith("爱喝"):
            polarity = "like"
            normalized = cleaned.removeprefix("爱喝").strip()
        elif cleaned.startswith("爱"):
            polarity = "like"
            normalized = cleaned.removeprefix("爱").strip()
        elif cleaned.startswith("喜欢"):
            polarity = "like"
            normalized = cleaned.removeprefix("喜欢").strip()
        elif cleaned.startswith("不太能吃"):
            polarity = "avoid"
            normalized = cleaned.removeprefix("不太能吃").strip()
        elif cleaned.startswith("现在能接受"):
            polarity = "accept"
            normalized = cleaned.removeprefix("现在能接受").strip()
        elif cleaned.startswith("现在能吃一点"):
            polarity = "accept"
            normalized = cleaned.removeprefix("现在能吃一点").strip()
        normalized = re.sub(r"^(the|a|an)\s+", "", normalized, flags=re.IGNORECASE).strip()
        if slot_key == "favorite_beverage":
            normalized = normalized.removeprefix("喝").strip()
        normalized_items = self._split_preference_terms(normalized)
        if not normalized_items and normalized:
            normalized_items = [normalized]
        return {
            "polarity": polarity,
            "normalized_value": normalized.casefold(),
            "normalized_items": [item.casefold() for item in normalized_items],
        }

    def _rebuild_preference_slots(self) -> None:
        rebuilt: dict[str, SlotValue] = {}
        for key, items in self._preference_profiles.items():
            active_items = [item for item in items if item.status == "active"]
            if not active_items:
                continue
            active_items.sort(key=lambda item: (item.updated_at, item.evidence_count), reverse=True)
            latest = active_items[0]
            values = [self._render_preference_for_slot(item) for item in active_items]
            rebuilt[key] = SlotValue(
                key=key,
                value="；".join(values),
                updated_at=latest.updated_at,
                source_memory_id=latest.source_memory_id,
                confidence=latest.confidence,
                first_seen_at=min(item.first_seen_at for item in active_items),
            )
        self._preference_slots = rebuilt

    def _render_preference_for_slot(self, item: PreferenceProfileItem) -> str:
        if item.scope == "global":
            return item.value
        return f"{self._render_scope_label(item.scope)}: {item.value}"

    def _compose_preference_value(
        self,
        slot_key: str,
        polarity: str,
        normalized_value: str,
    ) -> str:
        phrase = normalized_value.strip()
        if not phrase:
            return ""

        if slot_key == "favorite_beverage":
            phrase = phrase.removeprefix("喝").strip()

        if slot_key == "food_spice":
            if "清淡" in phrase and polarity in {"like", "prefer"}:
                return "更喜欢清淡"
            if polarity == "avoid":
                return f"不太能吃{phrase}"
            if polarity == "accept":
                return f"现在能接受{phrase}"

        if re.search(r"[A-Za-z]", phrase):
            return {
                "dislike": f"doesn't like {phrase}",
                "prefer": f"prefers {phrase}",
                "avoid": f"avoids {phrase}",
                "accept": f"can enjoy {phrase} now",
            }.get(polarity, f"likes {phrase}")

        return {
            "dislike": f"不喜欢{phrase}",
            "prefer": f"更喜欢{phrase}",
            "avoid": f"不太能吃{phrase}",
            "accept": f"现在能接受{phrase}",
        }.get(polarity, f"喜欢{phrase}")

    def _split_preference_terms(self, text: str) -> list[str]:
        if not text:
            return []

        parts = re.split(
            r"\s*(?:和|跟|及|以及|与|、|,|，|/|&|and|or|或者|或)\s*",
            text,
            flags=re.IGNORECASE,
        )
        cleaned_parts: list[str] = []
        seen: set[str] = set()
        for part in parts:
            cleaned = self._clean_value(part)
            cleaned = re.sub(r"^(都|也|还|又)\s*", "", cleaned)
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            if not cleaned:
                continue
            key = cleaned.casefold()
            if key in seen:
                continue
            seen.add(key)
            cleaned_parts.append(cleaned)
        return cleaned_parts

    def _same_preference_polarity(self, left: str, right: str) -> bool:
        return (
            self._parse_preference_value("", left)["polarity"]
            == self._parse_preference_value("", right)["polarity"]
        )

    def _preference_subjects_overlap(self, left: str, right: str) -> bool:
        left_items = set(self._parse_preference_value("", left)["normalized_items"])
        right_items = set(self._parse_preference_value("", right)["normalized_items"])
        return bool(left_items and right_items and left_items & right_items)

    def _retain_split_preference_residuals(
        self,
        item: PreferenceProfileItem,
        replacement_value: str,
        role: str,
        timestamp: str,
    ) -> None:
        original = self._parse_preference_value(item.key, item.value)
        replacement = self._parse_preference_value(item.key, replacement_value)
        remaining_items = [
            normalized_item
            for normalized_item in original["normalized_items"]
            if normalized_item not in set(replacement["normalized_items"])
        ]

        for normalized_item in remaining_items:
            residual_value = self._compose_preference_value(
                item.key,
                original["polarity"],
                normalized_item,
            )
            if not residual_value:
                continue

            existing = self._find_matching_preference_item(item.key, residual_value)
            if existing:
                existing.evidence_count += max(item.evidence_count - 1, 1)
                continue

            memory_id = self._create_memory_id()
            residual_item = PreferenceProfileItem(
                key=item.key,
                value=residual_value,
                normalized_value=normalized_item,
                polarity=original["polarity"],
                scope=item.scope,
                status="active",
                updated_at=item.updated_at,
                first_seen_at=item.first_seen_at,
                source_memory_id=memory_id,
                confidence=item.confidence,
                evidence_count=item.evidence_count,
                valid_from=item.valid_from or item.first_seen_at,
            )
            self._preference_profiles.setdefault(item.key, []).append(residual_item)
            residual_candidate = MemoryCandidate(
                memory_type="preference",
                summary=self._default_summary("preference", item.key, residual_value),
                value=residual_value,
                content=item.value,
                slot_key=item.key,
                metadata={
                    "write_decision": "derived_split",
                    "write_reason": "residual_preference_after_partial_update",
                    "scope": item.scope,
                    "polarity": residual_item.polarity,
                    "normalized_value": residual_item.normalized_value,
                },
            )
            self._memories.append(
                self._candidate_to_memory(residual_candidate, role, timestamp, memory_id)
            )

    def _clean_slot_key(self, slot_key: Any) -> str | None:
        if slot_key is None:
            return None
        cleaned = str(slot_key).strip().lower().replace("-", "_").replace(" ", "_")
        cleaned = re.sub(r"[^a-z0-9_]", "", cleaned)
        return cleaned or None

    def _default_summary(self, memory_type: str, slot_key: str | None, value: str) -> str:
        if memory_type == "persona":
            label = _SLOT_LABELS.get(slot_key or "", _slot_label_en(slot_key or "persona"))
            return f"用户{label}是{value}" if re.search(r"[\u4e00-\u9fff]", value) else f"User {label}: {value}"
        if memory_type == "preference":
            label = _SLOT_LABELS.get(slot_key or "", _slot_label_en(slot_key or "preference"))
            return f"用户{label}：{value}" if re.search(r"[\u4e00-\u9fff]", value) else f"User {label}: {value}"
        return f"历史事件：{value}"

    def _slugify(self, value: str) -> str:
        tokens = tokenize_text(value)
        if not tokens:
            return "generic_preference"
        return "_".join(tokens[:3])

    def _create_memory_id(self) -> str:
        return uuid4().hex

    def _freshness_score(self, timestamp: str) -> float:
        try:
            delta = datetime.now(timezone.utc) - datetime.fromisoformat(timestamp)
        except ValueError:
            return 0.0
        days = max(delta.total_seconds() / 86400.0, 0.0)
        return max(0.0, 0.12 - min(days / 365.0, 0.12))

    def _load(self) -> None:
        if not self._file.exists():
            return

        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
            self._persona_slots = {
                key: SlotValue(**value) for key, value in data.get("persona_slots", {}).items()
            }
            raw_profiles = data.get("preference_profiles", {})
            if raw_profiles:
                self._preference_profiles = {
                    key: [PreferenceProfileItem(**item) for item in items]
                    for key, items in raw_profiles.items()
                }
            else:
                self._preference_profiles = self._migrate_preference_slots(
                    data.get("preference_slots", {})
                )
            self._rebuild_preference_slots()
            self._conflicts = [ConflictRecord(**item) for item in data.get("conflicts", [])]
            self._memories = [MemoryItem(**item) for item in data.get("memories", [])]
            logger.info(
                "StructuredLongTermMemory: loaded {} memories from {}",
                len(self._memories),
                self._file,
            )
        except Exception as e:
            logger.warning(f"StructuredLongTermMemory: could not load {self._file}: {e}")

    def _save(self) -> None:
        payload = {
            "version": 3,
            "persona_slots": {key: asdict(value) for key, value in self._persona_slots.items()},
            "preference_slots": {
                key: asdict(value) for key, value in self._preference_slots.items()
            },
            "preference_profiles": {
                key: [asdict(item) for item in items]
                for key, items in self._preference_profiles.items()
            },
            "conflicts": [asdict(conflict) for conflict in self._conflicts],
            "memories": [asdict(memory) for memory in self._memories],
        }
        try:
            self._file.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"StructuredLongTermMemory: could not save {self._file}: {e}")

    def _migrate_preference_slots(
        self,
        raw_slots: dict[str, dict[str, Any]],
    ) -> dict[str, list[PreferenceProfileItem]]:
        migrated: dict[str, list[PreferenceProfileItem]] = {}
        for key, value in raw_slots.items():
            slot = SlotValue(**value)
            parsed = self._parse_preference_value(key, slot.value)
            migrated[key] = [
                PreferenceProfileItem(
                    key=key,
                    value=slot.value,
                    normalized_value=parsed["normalized_value"],
                    polarity=parsed["polarity"],
                    scope="global",
                    status="active",
                    updated_at=slot.updated_at,
                    first_seen_at=slot.first_seen_at or slot.updated_at,
                    source_memory_id=slot.source_memory_id,
                    confidence=slot.confidence,
                    evidence_count=1,
                    valid_from=slot.first_seen_at or slot.updated_at,
                )
            ]
        return migrated


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slot_label_en(slot_key: str) -> str:
    return {
        "name": "name",
        "occupation": "occupation",
        "work_context": "work context",
        "relationship_status": "relationship status",
        "home_city": "current city",
        "favorite_beverage": "favorite beverage",
        "favorite_food": "favorite food",
        "activity_style": "activity preference",
        "social_style": "social preference",
        "living_preference": "living preference",
        "music_style": "music preference",
        "food_spice": "spice preference",
        "food_flavor": "flavor preference",
    }.get(slot_key, slot_key.replace("_", " "))
