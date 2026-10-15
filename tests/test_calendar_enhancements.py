"""Tests for the mood-calendar enhancements: seed script, trend series,
tarot journal history and the deterministic mood forecast."""

import json
import sys
from datetime import date, timedelta
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
PROTOTYPE_DIR = PROJECT_DIR / "prototype_demo"
MCP_SHARED_DIR = PROJECT_DIR / "mcp" / "shared"
for path in (str(PROJECT_DIR), str(MCP_SHARED_DIR), str(PROTOTYPE_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from mood_calendar import MoodCalendar  # noqa: E402
from seed_calendar_history import seed  # noqa: E402

TODAY = date(2026, 9, 21)


def _seeded_calendar(tmp_path: Path) -> MoodCalendar:
    calendar = MoodCalendar(tmp_path / "mood_calendar.json")
    seed(calendar, days=30, tarot_days=20, seed_value=7, today=TODAY)
    return calendar


def test_seed_backfills_30_days_with_weather_and_mood(tmp_path):
    calendar = _seeded_calendar(tmp_path)
    days = calendar.get_days()
    seeded = {k: v for k, v in days.items() if k != TODAY.isoformat()}

    assert len(seeded) == 30
    for iso, entry in seeded.items():
        assert entry["weather_desc"]
        assert entry["weather_temp_c"]
        assert entry["weather_city"] == "Guangzhou"
        assert entry["mood"] in ("开心", "难过")
        assert 0.0 <= entry["mood_score"] <= 100.0
        assert 40 <= entry["horoscope_score"] <= 95
    # today must be left untouched
    assert TODAY.isoformat() not in days or "mood_score" not in days[TODAY.isoformat()]


def test_seed_creates_exactly_20_tarot_days_with_full_draw(tmp_path):
    calendar = _seeded_calendar(tmp_path)
    days = calendar.get_days()

    tarot_days = [v for v in days.values() if v.get("tarot_draw")]
    assert len(tarot_days) == 20
    for entry in tarot_days:
        draw = entry["tarot_draw"]
        expected = 1 if draw["spread"] == "single" else 3
        assert len(draw["cards"]) == expected
        assert entry["tarot_spread"] == draw["spread_name"]
        for card in draw["cards"]:
            assert card["name"]
            assert card["orientation_name"] in ("正位", "逆位")
            assert card["keywords"]
            assert card["image"].endswith(".webp")
        assert entry["tarot_event"]


def test_seed_is_idempotent_for_fixed_seed(tmp_path):
    path = tmp_path / "mood_calendar.json"
    seed(MoodCalendar(path), days=30, tarot_days=20, seed_value=7, today=TODAY)
    first = path.read_text(encoding="utf-8")
    seed(MoodCalendar(path), days=30, tarot_days=20, seed_value=7, today=TODAY)
    second = path.read_text(encoding="utf-8")
    assert json.loads(first) == json.loads(second)


def test_build_series_returns_14_continuous_days(tmp_path):
    calendar = _seeded_calendar(tmp_path)
    series = calendar.build_series(days=14, end=TODAY)

    assert len(series) == 14
    first = date.fromisoformat(series[0]["date"])
    for i, row in enumerate(series):
        expected = (first + timedelta(days=i)).isoformat()
        assert row["date"] == expected
        assert row["weekday"] == (first + timedelta(days=i)).weekday()
        assert 0.0 <= row["mood_score"] <= 100.0
        assert isinstance(row["has_tarot"], bool)


def test_build_series_interpolates_missing_scores(tmp_path):
    calendar = MoodCalendar(tmp_path / "mood_calendar.json")
    yesterday = (TODAY - timedelta(days=1)).isoformat()
    calendar.record(day=yesterday, mood_score=80.0, weather_desc="Sunny")
    series = calendar.build_series(days=7, end=TODAY)

    scores = [r["mood_score"] for r in series]
    assert all(s is not None for s in scores)
    assert scores[-2] == 80.0  # yesterday keeps its known value


def test_tarot_history_newest_first_with_cards(tmp_path):
    calendar = _seeded_calendar(tmp_path)
    history = calendar.tarot_history()

    assert len(history) == 20
    dates = [r["date"] for r in history]
    assert dates == sorted(dates, reverse=True)
    for rec in history:
        assert rec["spread_name"]
        assert rec["event"]
        assert len(rec["cards"]) >= 1


def test_predict_mood_bounds_and_weather_sensitivity(tmp_path):
    calendar = _seeded_calendar(tmp_path)

    def row(iso, desc, rain):
        return {"date": iso, "description": desc, "chance_of_rain": str(rain), "max_temp_c": "32"}

    rainy = calendar.predict_mood(
        [row("2026-09-22", "Light rain shower", 70)] * 5, days=5
    )
    sunny = calendar.predict_mood([row("2026-09-22", "Sunny", 0)] * 5, days=5)

    assert len(rainy) == 5 and len(sunny) == 5
    for r in rainy + sunny:
        assert 10.0 <= r["predicted_mood_score"] <= 95.0
    assert rainy[0]["predicted_mood_score"] < sunny[0]["predicted_mood_score"]


def test_predict_mood_never_crashes_without_history(tmp_path):
    calendar = MoodCalendar(tmp_path / "empty.json")
    rows = [{"date": (TODAY + timedelta(days=i + 1)).isoformat(), "description": "Cloudy", "chance_of_rain": "20"} for i in range(5)]
    out = calendar.predict_mood(rows, days=5)
    assert len(out) == 5
    assert all(10.0 <= r["predicted_mood_score"] <= 95.0 for r in out)
