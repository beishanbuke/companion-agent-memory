"""Seed the mood calendar with ~30 days of demo history for 小宇.

Backfills one month of plausible Guangzhou weather, a smooth mood curve,
daily horoscope scores and real tarot draws (20 of the 30 days) so the
mood calendar, the trend chart and the tarot journal have meaningful demo
content. Deterministic for a fixed seed: re-running produces the same data.

Usage:
    python prototype_demo/seed_calendar_history.py [--days 30] [--tarot-days 20] [--seed 7]

Today is never touched so live data keeps ownership of the current day.
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import date, timedelta
from pathlib import Path

PROTOTYPE_DIR = Path(__file__).resolve().parent
MCP_SHARED_DIR = PROTOTYPE_DIR.parent / "mcp" / "shared"
for path in (str(MCP_SHARED_DIR), str(PROTOTYPE_DIR)):
    if path not in sys.path:
        sys.path.insert(0, str(path))

from mood_calendar import MoodCalendar  # noqa: E402
from tarot_engine import TarotEngine, SPREADS  # noqa: E402

DEFAULT_CALENDAR_PATH = PROTOTYPE_DIR / ".run" / "mood_calendar.json"
DEFAULT_SEED = 7

# wttr.in-style snapshots for late-summer/early-autumn Guangzhou (Nansha).
# (description, temp_min, temp_max, weight)
WEATHER_POOL: list[tuple[str, int, int, float]] = [
    ("Sunny", 31, 35, 2.2),
    ("Partly cloudy", 30, 34, 2.6),
    ("Cloudy", 28, 33, 1.8),
    ("Patchy rain nearby", 27, 32, 1.6),
    ("Light rain shower", 26, 31, 1.0),
    ("Moderate or heavy rain shower", 26, 30, 0.5),
    ("Thundery outbreaks possible", 27, 32, 0.7),
    ("Overcast", 28, 32, 0.6),
]

# Rainy descriptions: matched case-insensitively (wttr.in uses lowercase
# "rain"), used to bias the mood curve down and to flag rainy days.
RAIN_KEYS = ("雨", "rain", "drizzle", "shower", "thunder")


def _is_rain(desc: str) -> bool:
    lowered = desc.lower()
    return any(k in lowered for k in RAIN_KEYS)


def pick_weather(rng: random.Random, midterm_window: bool) -> tuple[str, int]:
    pool = WEATHER_POOL
    if midterm_window:
        rainy = [w for w in WEATHER_POOL if _is_rain(w[0])]
        pool = rainy * 3 + list(WEATHER_POOL)
    desc, t_min, t_max, weight = rng.choices(pool, weights=[w[3] for w in pool], k=1)[0]
    return desc, rng.randint(t_min, t_max)


def mood_curve(rng: random.Random, day: date, weather_desc: str) -> float:
    """Smooth-ish 0-100 mood score: weekend up, rain down, midterm dip."""
    score = 66.0
    if day.weekday() == 5:
        score += 6.0
    elif day.weekday() == 6:
        score += 4.0
    if _is_rain(weather_desc):
        score -= 5.0
    if date(2026, 9, 7) <= day <= date(2026, 9, 10):
        score -= 19.0  # 期中周低谷
    score += rng.uniform(-5.0, 5.0)
    return max(20.0, min(92.0, score))


# Small-life event notes attached to seeded tarot days (小宇's world).
TAROT_EVENTS = [
    "社团招新忙了一整天，晚上回宿舍煲了玉米胡萝卜汤",
    "实习面试结束，自我感觉发挥得还不错",
    "和室友坐十八号线去南沙看海，吹了很久的风",
    "毕设选题终于定了方向，心里踏实了一点",
    "夜跑五公里，暴汗之后整个人都松了",
    "给爸妈打了很久电话，聊的都是家常",
    "在图书馆泡了一整天，效率意外的高",
    "宿舍空调坏了，热得一夜没睡踏实",
    "和朋友去唱K，吼了几首老歌解压",
    "收到了心仪实习的回复，约了下轮沟通",
    "帮学弟学妹看简历，被夸有耐心",
    "下雨天窝在宿舍看了一整部电影",
    "系队训练赛赢了一局，跑位都顺了",
    "整理相册翻到刚入学的照片，有点感慨",
    "陪同学去体检，顺便自己也查了视力",
    "在食堂发现一个新的窗口，味道意外不错",
    "赶 ddl 到凌晨两点，咖啡续了两杯",
    "周末回了趟家，妈妈做了白切鸡",
    "宿舍楼下那只小猫今天终于让摸了",
    "开始规划毕业旅行，默默攒起了钱",
]

TAROT_QUESTIONS = [
    "最近考试周能顺利度过吗",
    "这份实习适不适合我",
    "毕业设计选这个方向好吗",
    "和室友的小矛盾该怎么化解",
    "要不要报名参加那个比赛",
    "这个月的花销会不会超预算",
]


def pick_weather(rng: random.Random, midterm_window: bool) -> tuple[str, int]:
    pool = WEATHER_POOL
    if midterm_window:
        pool = [w for w in WEATHER_POOL if any(k in w[0] for k in RAIN_KEYS)] * 3 + list(WEATHER_POOL)
    desc, t_min, t_max, weight = rng.choices(pool, weights=[w[3] for w in pool], k=1)[0]
    return desc, rng.randint(t_min, t_max)


def mood_curve(rng: random.Random, day: date, weather_desc: str) -> float:
    """Smooth-ish 0-100 mood score: weekend up, rain down, midterm dip."""
    score = 66.0
    if day.weekday() == 5:
        score += 6.0
    elif day.weekday() == 6:
        score += 4.0
    if any(k in weather_desc for k in RAIN_KEYS):
        score -= 5.0
    if date(2026, 9, 7) <= day <= date(2026, 9, 10):
        score -= 19.0  # 期中周低谷
    score += rng.uniform(-5.0, 5.0)
    return max(20.0, min(92.0, score))


def draw_seeded(engine: TarotEngine, spread: str, rng: random.Random) -> dict:
    """TarotEngine-compatible draw driven by our seeded rng (idempotent)."""
    positions = SPREADS[spread]["positions"]
    chosen = rng.sample(engine._cards, len(positions))  # noqa: SLF001
    cards = [
        engine._drawn_card_payload(card, rng.random() < 0.5, position)  # noqa: SLF001
        for position, card in zip(positions, chosen)
    ]
    return {
        "spread": spread,
        "spread_name": SPREADS[spread]["name"],
        "positions": positions,
        "cards": cards,
    }


def seed(
    calendar: MoodCalendar,
    *,
    days: int = 30,
    tarot_days: int = 20,
    seed_value: int = DEFAULT_SEED,
    today: date | None = None,
) -> dict:
    rng = random.Random(seed_value)
    engine = TarotEngine()
    today = today or date.today()

    targets = [today - timedelta(days=n) for n in range(days, 0, -1)]
    tarot_dates = set(rng.sample(targets, k=min(tarot_days, len(targets))))
    events = rng.sample(TAROT_EVENTS, k=len(TAROT_EVENTS))

    for offset, day in enumerate(targets):
        desc, temp = pick_weather(rng, midterm_window=date(2026, 9, 6) <= day <= date(2026, 9, 10))
        score = mood_curve(rng, day, desc)
        fields: dict = {
            "weather_city": "Guangzhou",
            "weather_temp_c": str(temp),
            "weather_desc": desc,
            "mood_score": round(score, 1),
            "mood": "开心" if score >= 60 else "难过",
            "mood_intensity": round(abs(score - 50.0) / 50.0, 2),
            "horoscope_score": int(max(40, min(95, round(score + rng.uniform(-8.0, 8.0))))),
            "horoscope_theme": "综合",
            "zodiac_sign": "天秤座",
        }
        if day in tarot_dates:
            spread = "single" if rng.random() < 0.7 else "three"
            draw = draw_seeded(engine, spread, rng)
            fields["tarot_cards"] = [c["name"] + c["orientation_name"] for c in draw["cards"]]
            fields["tarot_spread"] = draw["spread_name"]
            fields["tarot_draw"] = draw
            fields["tarot_event"] = events[offset % len(events)]
            if rng.random() < 0.15:
                fields["tarot_question"] = rng.choice(TAROT_QUESTIONS)
        calendar.record(day=day.isoformat(), **fields)

    return {
        "seeded_days": len(targets),
        "tarot_days": len(tarot_dates),
        "range": f"{targets[0].isoformat()} ~ {targets[-1].isoformat()}",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the mood calendar with demo history.")
    parser.add_argument("--path", default=str(DEFAULT_CALENDAR_PATH), help="mood_calendar.json path")
    parser.add_argument("--days", type=int, default=30, help="how many past days to backfill")
    parser.add_argument("--tarot-days", type=int, default=20, help="days (of them) that get a tarot draw")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="rng seed (deterministic output)")
    args = parser.parse_args()

    calendar = MoodCalendar(Path(args.path))
    summary = seed(calendar, days=args.days, tarot_days=args.tarot_days, seed_value=args.seed)
    print(f"Seeded {summary['seeded_days']} days ({summary['range']}), tarot on {summary['tarot_days']} days.")


if __name__ == "__main__":
    main()
