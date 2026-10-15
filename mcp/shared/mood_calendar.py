"""Mood-weather-fortune calendar store.

Records one entry per day: detected emotion, weather snapshot, horoscope
score/theme and tarot usage. Used by the demo server to render the
mood calendar and to back evidence-based encouraging analyses.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import date as date_type
from datetime import timedelta
from pathlib import Path
from typing import Any

_lock = threading.Lock()


class MoodCalendar:
    def __init__(self, path: Path | str):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    # ---------- storage ----------

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {"days": {}}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return {"days": {}}
        if not isinstance(data, dict) or not isinstance(data.get("days"), dict):
            return {"days": {}}
        return data

    def _save(self, data: dict[str, Any]) -> None:
        fd, tmp = tempfile.mkstemp(dir=str(self._path.parent), suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, self._path)

    # ---------- recording ----------

    def record(self, day: str | None = None, **fields: Any) -> dict[str, Any] | None:
        """Merge fields into the given day (default today). Empty fields ignored."""
        day = day or date_type.today().isoformat()
        cleaned = {k: v for k, v in fields.items() if v not in (None, "", [])}
        if not cleaned:
            return None
        with _lock:
            data = self._load()
            entry = data["days"].setdefault(day, {"date": day})
            entry.update(cleaned)
            self._save(data)
            return entry

    def get_day(self, day: str) -> dict[str, Any] | None:
        return self._load()["days"].get(day)

    def get_days(self) -> dict[str, Any]:
        return self._load()["days"]

    # ---------- trend chart ----------

    # Labels from companion_agent.emotion_detector PRIMARY_LABELS.
    POSITIVE_MOODS = ("开心", "期待")
    NEGATIVE_MOODS = ("难过", "焦虑", "愤怒", "疲惫", "孤独")
    NEUTRAL_MOODS = ("平静",)

    @classmethod
    def _mood_score_of(cls, entry: dict[str, Any]) -> float | None:
        """0-100 mood score; falls back to deriving from mood label + intensity."""
        score = entry.get("mood_score")
        if isinstance(score, (int, float)):
            return max(0.0, min(100.0, float(score)))
        mood = entry.get("mood")
        intensity = entry.get("mood_intensity")
        if not isinstance(intensity, (int, float)):
            return None
        i = max(0.0, min(1.0, float(intensity)))
        if mood in cls.POSITIVE_MOODS:
            # 开心满强度≈100，期待略收敛（还悬着心）
            base = 52.0 if mood == "期待" else 50.0
            span = 40.0 if mood == "期待" else 50.0
            return base + i * span
        if mood in cls.NEGATIVE_MOODS:
            # 难过按满幅度下探，其余负性情绪基线稍高（程度略轻）
            base = 50.0 if mood == "难过" else 45.0
            span = 50.0 if mood == "难过" else 40.0
            return max(5.0, base - i * span)
        if mood in cls.NEUTRAL_MOODS:
            return 58.0 + i * 10.0
        return None

    @staticmethod
    def _is_rainy(desc: Any) -> bool:
        lowered = str(desc or "").lower()
        return any(k in lowered for k in ("雨", "rain", "drizzle", "shower", "thunder"))

    def build_series(self, days: int = 14, end: date_type | None = None) -> list[dict[str, Any]]:
        """Per-day rows for the mood trend chart, oldest first.

        Days without a usable mood score get a linear interpolation between
        known neighbours (edge gaps use the nearest known value) so the curve
        stays smooth without inventing labels.
        """
        end = end or date_type.today()
        start = end - timedelta(days=days - 1)
        stored = self._load()["days"]
        rows: list[dict[str, Any]] = []
        for i in range(days):
            day = start + timedelta(days=i)
            iso = day.isoformat()
            entry = stored.get(iso) or {}
            weather_desc = entry.get("weather_desc")
            rows.append(
                {
                    "date": iso,
                    "weekday": day.weekday(),
                    "mood_score": self._mood_score_of(entry),
                    "mood": entry.get("mood"),
                    "weather_desc": weather_desc,
                    "weather_temp_c": entry.get("weather_temp_c"),
                    "rain": self._is_rainy(weather_desc),
                    "has_tarot": bool(entry.get("tarot_draw") or entry.get("tarot_cards")),
                    "horoscope_score": entry.get("horoscope_score"),
                }
            )

        known = [(i, r["mood_score"]) for i, r in enumerate(rows) if r["mood_score"] is not None]
        if not known:
            for r in rows:
                r["mood_score"] = 60.0
            return rows
        first_i, first_v = known[0]
        for i in range(first_i):
            rows[i]["mood_score"] = first_v
        last_i, last_v = known[-1]
        for i in range(last_i + 1, len(rows)):
            rows[i]["mood_score"] = last_v
        for a in range(len(known) - 1):
            i0, v0 = known[a]
            i1, v1 = known[a + 1]
            gap = i1 - i0
            if gap > 1:
                for i in range(i0 + 1, i1):
                    t = (i - i0) / gap
                    rows[i]["mood_score"] = round(v0 + (v1 - v0) * t, 1)
        return rows

    def tarot_history(self) -> list[dict[str, Any]]:
        """Days with a stored tarot draw, newest first, for the journal view."""
        rows: list[dict[str, Any]] = []
        for day, entry in self._load()["days"].items():
            draw = entry.get("tarot_draw")
            if not draw:
                continue
            rows.append(
                {
                    "date": day,
                    "spread": draw.get("spread"),
                    "spread_name": draw.get("spread_name") or entry.get("tarot_spread") or "塔罗占卜",
                    "question": entry.get("tarot_question") or draw.get("question") or "",
                    "event": entry.get("tarot_event") or "",
                    "cards": draw.get("cards") or [],
                }
            )
        rows.sort(key=lambda r: r["date"], reverse=True)
        return rows

    def predict_mood(
        self, forecast_rows: list[dict[str, Any]], days: int = 5, recent: int = 7
    ) -> list[dict[str, Any]]:
        """Deterministic 0-100 mood forecast for upcoming days.

        Starts from a recency-weighted average of the last `recent` known
        mood scores, then per day: weather adjustment (rain -4 / sunny +3 /
        overcast +1), a small weekend lift, and mild mean-reversion to 62,
        chained through the previous predicted day so the curve stays smooth.
        """
        series = self.build_series(days=max(recent, 2))
        known = [(r["mood_score"] or 0.0) for r in series[-recent:]]
        weights = [i + 1 for i in range(len(known))]
        base = sum(v * w for v, w in zip(known, weights)) / sum(weights) if known else 62.0

        out: list[dict[str, Any]] = []
        prev = base
        for row in forecast_rows[:days]:
            iso = str(row.get("date") or "")
            try:
                weekday = date_type.fromisoformat(iso).weekday()
            except ValueError:
                weekday = 0
            desc = str(row.get("description") or "")
            try:
                rain_chance = int(row.get("chance_of_rain") or 0)
            except (TypeError, ValueError):
                rain_chance = 0
            score = prev * 0.45 + base * 0.55
            rainy = self._is_rainy(desc) or rain_chance >= 50
            if rainy:
                score -= 4.0
            elif "sunny" in desc.lower() or "clear" in desc.lower():
                score += 3.0
            else:
                score += 1.0
            if weekday >= 5:
                score += 3.0
            score = score * 0.9 + 62.0 * 0.1
            score = max(10.0, min(95.0, score))
            out.append(
                {
                    "date": iso,
                    "weekday": weekday,
                    "predicted_mood_score": round(score, 1),
                    "weather_desc": desc,
                    "weather_temp_c": row.get("max_temp_c"),
                    "rain": rainy,
                }
            )
            prev = score
        return out

    # ---------- stats ----------

    def stats(self) -> dict[str, Any]:
        days = self._load()["days"]
        total = len(days)
        mood_counts: dict[str, int] = {}
        score_sum = 0.0
        score_n = 0
        score_by_mood: dict[str, list[float]] = {}
        rainy = 0
        rainy_mood: dict[str, int] = {}
        clear_mood: dict[str, int] = {}
        tarot_days = 0
        tarot_mood: dict[str, int] = {}
        horoscope_days = 0
        hot_days = 0

        for entry in days.values():
            mood = entry.get("mood") or "None"
            mood_counts[mood] = mood_counts.get(mood, 0) + 1
            score = entry.get("horoscope_score")
            if isinstance(score, (int, float)):
                score_sum += score
                score_n += 1
                score_by_mood.setdefault(mood, []).append(float(score))
            weather_desc = str(entry.get("weather_desc") or "")
            is_rain = any(k in weather_desc for k in ("雨", "Rain", "Drizzle", "Shower", "Thunder"))
            if entry.get("weather_temp_c") is not None or weather_desc:
                if is_rain:
                    rainy += 1
                    rainy_mood[mood] = rainy_mood.get(mood, 0) + 1
                else:
                    clear_mood[mood] = clear_mood.get(mood, 0) + 1
                try:
                    if float(entry.get("weather_temp_c")) >= 30:
                        hot_days += 1
                except (TypeError, ValueError):
                    pass
            if entry.get("tarot_cards"):
                tarot_days += 1
                tarot_mood[mood] = tarot_mood.get(mood, 0) + 1
            if score is not None:
                horoscope_days += 1

        def avg(xs: list[float]) -> float | None:
            return round(sum(xs) / len(xs), 1) if xs else None

        return {
            "total_days": total,
            "mood_counts": mood_counts,
            "avg_horoscope_score": round(score_sum / score_n, 1) if score_n else None,
            "avg_score_by_mood": {k: avg(v) for k, v in score_by_mood.items()},
            "rainy_days": rainy,
            "rainy_mood": rainy_mood,
            "clear_mood": clear_mood,
            "hot_days": hot_days,
            "tarot_days": tarot_days,
            "tarot_mood": tarot_mood,
            "horoscope_days": horoscope_days,
        }
