"""Emotion longitudinal memory for the companion agent.

Three lightweight, file-backed pieces that make emotion understanding
accumulate over time instead of resetting every turn:

- EmotionBaseline: per-user messaging-pattern statistics (EMA). Provides
  behavioral features ("this user is unusually terse today") that both
  the rule path and the LLM judge consume as weak hints.
- EmotionEventStore: an append-only episodic log of notable emotional
  moments {date, label, intensity, trigger, trend}. Backs follow-up
  prompts ("昨天你因为…很焦虑，今天好些了吗") and repeat-pattern notes.
- detect_emotion_correction: pattern-based extraction of user pushback
  ("我不是难过，是焦虑") so misreads get corrected, remembered and
  learned from instead of silently ignored.

All stores use atomic JSON writes and are safe to share across threads.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from dataclasses import dataclass
from datetime import date as date_type
from datetime import datetime
from pathlib import Path
from typing import Any

from .emotion_detector import (
    EMOTION_ANGRY,
    EMOTION_ANXIOUS,
    EMOTION_CALM,
    EMOTION_EXPECTANT,
    EMOTION_HAPPY,
    EMOTION_LONELY,
    EMOTION_NONE,
    EMOTION_SAD,
    EMOTION_TIRED,
    NEGATIVE_LABELS,
)

_lock = threading.Lock()

# Phrases users use when pushing back on an emotion read. Both an explicit
# negation of a label and an affirmative replacement must be present;
# otherwise we risk learning from noise.
_NEGATION_MARKERS = ("不是", "别提了", "才不是")
_AFFIRMATION_MARKERS = ("是", "其实是", "应该说是", "我觉得是")

# Alias phrases -> canonical label (longest first for greedy matching).
_EMOTION_PHRASES: list[tuple[str, str]] = sorted(
    [
        ("不开心", EMOTION_SAD), ("不高兴", EMOTION_SAD), ("难过", EMOTION_SAD),
        ("伤心", EMOTION_SAD), ("低落", EMOTION_SAD),
        ("焦虑", EMOTION_ANXIOUS), ("紧张", EMOTION_ANXIOUS), ("担心", EMOTION_ANXIOUS),
        ("害怕", EMOTION_ANXIOUS), ("压力", EMOTION_ANXIOUS),
        ("生气", EMOTION_ANGRY), ("愤怒", EMOTION_ANGRY), ("火大", EMOTION_ANGRY),
        ("烦躁", EMOTION_ANGRY),
        ("累", EMOTION_TIRED), ("疲惫", EMOTION_TIRED), ("困", EMOTION_TIRED),
        ("疲倦", EMOTION_TIRED),
        ("孤独", EMOTION_LONELY), ("寂寞", EMOTION_LONELY), ("孤单", EMOTION_LONELY),
        ("平静", EMOTION_CALM), ("淡定", EMOTION_CALM),
        ("开心", EMOTION_HAPPY), ("高兴", EMOTION_HAPPY), ("快乐", EMOTION_HAPPY),
        ("期待", EMOTION_EXPECTANT), ("期盼", EMOTION_EXPECTANT),
    ],
    key=lambda item: -len(item[0]),
)


@dataclass(frozen=True)
class EmotionCorrection:
    wrong_label: str
    correct_label: str
    raw: str


def _phrase_to_label(text: str) -> str | None:
    for phrase, label in _EMOTION_PHRASES:
        if phrase in text:
            return label
    return None


def detect_emotion_correction(message: str) -> EmotionCorrection | None:
    """Extract "我不是X，是Y"-style corrections from the user turn.

    Requires both a negated emotion phrase and an affirmative replacement;
    returns None when either side is missing or both resolve to the same
    label. Conservative by design — a false correction is worse than none.
    """
    text = (message or "").strip()
    if not text:
        return None
    if not any(marker in text for marker in _NEGATION_MARKERS + ("错了",)):
        if not any(marker in text for marker in _AFFIRMATION_MARKERS):
            return None

    negated: str | None = None
    affirmed: str | None = None
    for phrase, label in _EMOTION_PHRASES:
        start = text.find(phrase)
        if start < 0:
            continue
        prefix = text[max(0, start - 6):start]
        if any(prefix.endswith(marker) for marker in _NEGATION_MARKERS):
            negated = negated or label
        elif any(prefix.endswith(marker) for marker in _AFFIRMATION_MARKERS):
            affirmed = affirmed or label
    # 宽松匹配（"前缀里含'是'"）会误伤"我不是很难过，就是有点累"这类
    # 自然陈述——它不是在纠正机器人的判断。宁可漏判，不可误判。

    if negated and affirmed and negated != affirmed:
        return EmotionCorrection(wrong_label=negated, correct_label=affirmed, raw=text[:120])
    return None


class EmotionBaseline:
    """Per-user messaging-pattern baseline with EMA updates.

    Features are *relative to the user's own history*, which is what makes
    "suddenly terse" a signal instead of "a short person".
    """

    DEFAULT_PATH = Path(__file__).resolve().parent.parent / "prototype_demo" / ".run" / "emotion_baseline.json"

    def __init__(self, path: Path | str | None = None):
        self._path = Path(path) if path else self.DEFAULT_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {"avg_len": 0.0, "avg_hour": -1.0, "samples": 0}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return {"avg_len": 0.0, "avg_hour": -1.0, "samples": 0}
        if not isinstance(data, dict):
            return {"avg_len": 0.0, "avg_hour": -1.0, "samples": 0}
        return data

    def _save(self, data: dict[str, Any]) -> None:
        fd, tmp = tempfile.mkstemp(dir=str(self._path.parent), suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
        os.replace(tmp, self._path)

    def features(
        self,
        message: str,
        history: list[dict[str, str]] | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Behavioral features for the current turn (weak hints, not verdicts)."""
        now = now or datetime.now()
        base = self._load()
        length = len((message or "").strip())
        avg_len = float(base.get("avg_len") or 0.0)
        length_ratio = round(length / avg_len, 2) if avg_len >= 4 else None
        user_turns = sum(
            1 for item in (history or []) if str(item.get("role")) == "user"
        )
        return {
            "length_ratio_vs_own_avg": length_ratio,
            "hour_of_day": now.hour,
            "user_turns_in_session": user_turns,
            "samples_in_baseline": int(base.get("samples") or 0),
        }

    def update(self, message: str, now: datetime | None = None) -> None:
        """Incorporate the current turn into the EMA baseline."""
        now = now or datetime.now()
        length = len((message or "").strip())
        if length == 0:
            return
        with _lock:
            base = self._load()
            n = int(base.get("samples") or 0)
            if n < 3:
                # 前几条直接平均，避免冷启动被单条拉偏
                total = float(base.get("avg_len") or 0.0) * n + length
                base["avg_len"] = round(total / (n + 1), 2)
                hour = float(base.get("avg_hour") or -1.0)
                base["avg_hour"] = round(((hour * n + now.hour) / (n + 1)), 2) if hour >= 0 else float(now.hour)
            else:
                base["avg_len"] = round(0.9 * float(base["avg_len"]) + 0.1 * length, 2)
                hour = float(base.get("avg_hour") or now.hour)
                base["avg_hour"] = round(0.9 * hour + 0.1 * now.hour, 2)
            base["samples"] = n + 1
            self._save(base)


class EmotionEventStore:
    """Append-only episodic log of notable emotional moments."""

    DEFAULT_PATH = Path(__file__).resolve().parent.parent / "prototype_demo" / ".run" / "emotion_events.json"
    MAX_EVENTS = 300

    def __init__(self, path: Path | str | None = None):
        self._path = Path(path) if path else self.DEFAULT_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {"events": []}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return {"events": []}
        if not isinstance(data, dict) or not isinstance(data.get("events"), list):
            return {"events": []}
        return data

    def _save(self, data: dict[str, Any]) -> None:
        fd, tmp = tempfile.mkstemp(dir=str(self._path.parent), suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, self._path)

    def record(
        self,
        label: str,
        intensity: float,
        trigger: str,
        trend: str = "新出现",
        corrected: bool = False,
        today: date_type | None = None,
    ) -> dict[str, Any] | None:
        """Append one emotional moment. Empty/None labels ignored."""
        label = (label or "").strip()
        if not label or label == EMOTION_NONE:
            return None
        today = today or date_type.today()
        event = {
            "date": today.isoformat(),
            "ts": datetime.now().isoformat(timespec="seconds"),
            "label": label,
            "intensity": round(max(0.0, min(1.0, float(intensity))), 2),
            "trigger": (trigger or "").strip()[:120],
            "trend": trend,
            "corrected": bool(corrected),
        }
        with _lock:
            data = self._load()
            data["events"].append(event)
            if len(data["events"]) > self.MAX_EVENTS:
                data["events"] = data["events"][-self.MAX_EVENTS:]
            self._save(data)
        return event

    def events(self) -> list[dict[str, Any]]:
        return list(self._load()["events"])

    def recent(
        self,
        days: int = 2,
        limit: int = 3,
        min_intensity: float = 0.0,
        labels: set[str] | None = None,
        exclude_today: bool = True,
        today: date_type | None = None,
    ) -> list[dict[str, Any]]:
        """Events within the last `days` days, newest first."""
        today = today or date_type.today()
        cutoff = today.fromordinal(today.toordinal() - days)
        out = []
        for event in reversed(self.events()):
            try:
                event_date = date_type.fromisoformat(str(event.get("date") or ""))
            except ValueError:
                continue
            if event_date < cutoff:
                break
            if exclude_today and event_date == today:
                continue
            if float(event.get("intensity") or 0.0) < min_intensity:
                continue
            if labels is not None and event.get("label") not in labels:
                continue
            out.append(event)
            if len(out) >= limit:
                break
        return out

    def label_counts(self, days: int = 14, today: date_type | None = None) -> dict[str, int]:
        today = today or date_type.today()
        cutoff = today.fromordinal(today.toordinal() - days)
        counts: dict[str, int] = {}
        for event in self.events():
            try:
                event_date = date_type.fromisoformat(str(event.get("date") or ""))
            except ValueError:
                continue
            if event_date < cutoff:
                continue
            label = str(event.get("label") or "")
            counts[label] = counts.get(label, 0) + 1
        return counts


def build_followup_notes(
    store: EmotionEventStore,
    current_trigger: str = "",
    today: date_type | None = None,
) -> list[str]:
    """Prompt-ready follow-up notes from the episodic emotion log.

    Two note types:
    - 昨日高强度负性事件 -> 自然的情绪跟进询问
    - 近两周同一标签反复出现 -> 持续性压力提示
    """
    notes: list[str] = []
    yesterday = store.recent(
        days=2, limit=2, min_intensity=0.6, labels=set(NEGATIVE_LABELS),
        exclude_today=True, today=today,
    )
    for event in yesterday:
        trigger = str(event.get("trigger") or "").strip()
        if trigger and trigger == (current_trigger or "").strip()[:120]:
            continue
        if trigger:
            notes.append(
                f"昨天用户曾因「{trigger}」感到{event.get('label')}"
                f"（强度 {event.get('intensity')}），如果自然，可以询问一下近况。"
            )
        else:
            notes.append(
                f"昨天用户曾出现较强的{event.get('label')}情绪，如果自然，可以关心一下。"
            )

    counts = store.label_counts(days=14, today=today)
    for label, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        if count >= 3 and label in NEGATIVE_LABELS:
            notes.append(
                f"用户近两周多次出现「{label}」（{count} 次），回应时可留意背后是否有持续性的压力。"
            )
            break  # 只提示最强的一个模式，避免 prompt 过载
    return notes
