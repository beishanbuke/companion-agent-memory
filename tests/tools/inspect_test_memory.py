#!/usr/bin/env python3
"""
Inspect test memory contents.

读取 prototype_memory_store.json，格式化输出各 tier 的内容，
并检查关键 profile 信息是否存在。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

MEMORY_FILE = Path(__file__).resolve().parents[2] / "prototype_memory_store.json"

# 关键信息检查清单
CHECKLIST = {
    "name": "林昊文",
    "university": "南方科技大学",
    "major": "通信工程",
    "year": "大三",
    "dislikes_education": "不喜欢被教育",
    "dislikes_big_plan": "不喜欢完整大计划",
    "prefers_micro_action": "30-60分钟",
    "courses": "数字通信",
    "strengths": "电路分析",
    "weaknesses": "考试前容易拖延",
    "friend_aze": "阿哲",
    "friend_xiaoman": "小满",
    "friend_rain": "Rain",
    "food_iced_americano": "冰美式",
    "food_luosifen": "螺蛳粉",
    "hometown": "南宁",
    "music": "落日飞车",
    "recent_travel": "旅游",
    "recent_exam": "考完期末",
    "upcoming_pressure": "下周",
}


def inspect_memory(user_id: str = "") -> dict:
    """Inspect memory snapshot and return structured report."""
    if not MEMORY_FILE.exists():
        print(f"Memory file not found: {MEMORY_FILE}")
        return {}

    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
        snapshot = json.load(f)

    print("=" * 50)
    print("MEMORY INSPECT REPORT")
    print("=" * 50)

    # Tier 1: Profile
    persona_slots = snapshot.get("persona_slots", {})
    print(f"\n【Profile Slots】({len(persona_slots)} items)")
    for key, slot in persona_slots.items():
        value = slot.get("value", "")
        print(f"  • {key}: {value}")

    # Tier 2: Preferences
    pref_slots = snapshot.get("preference_slots", {})
    print(f"\n【Preference Slots】({len(pref_slots)} items)")
    for key, slot in pref_slots.items():
        value = slot.get("value", "")
        print(f"  • {key}: {value}")

    # Tier 3: Memories (events)
    memories = snapshot.get("memories", [])
    active_memories = [m for m in memories if m.get("status") == "active"]
    print(f"\n【Memories】({len(active_memories)} active / {len(memories)} total)")
    for mem in active_memories[-10:]:  # Show last 10
        summary = mem.get("summary", "")
        mem_type = mem.get("memory_type", "")
        tags = mem.get("tags", [])
        print(f"  • [{mem_type}] {summary}")
        if tags:
            print(f"    tags: {', '.join(tags)}")

    # Checklist
    all_text = json.dumps(snapshot, ensure_ascii=False)
    print(f"\n【Checklist】")
    checks = {}
    for key, keyword in CHECKLIST.items():
        ok = keyword in all_text
        checks[key] = ok
        status = "✅" if ok else "❌"
        print(f"  {status} {key}: '{keyword}'")

    found = sum(1 for v in checks.values() if v)
    total = len(checks)
    print(f"\n  Total: {found}/{total} ({round(found/total*100, 1)}%)")

    # Academic profile check
    has_courses = any(c in all_text for c in ["数字通信", "微波工程", "嵌入式系统"])
    print(f"\n  Academic profile detected: {'Yes' if has_courses else 'No'}")

    # Sensitive content check
    sensitive = "家庭作息冲突" in all_text or "11点前睡" in all_text
    print(f"  Sensitive family content: {'Yes (unexpected!)' if sensitive else 'No (good)'}")

    return {
        "persona_slot_count": len(persona_slots),
        "preference_slot_count": len(pref_slots),
        "active_memory_count": len(active_memories),
        "checklist": checks,
        "checklist_score": round(found / total, 2) if total else 0,
        "has_academic_profile": has_courses,
        "has_sensitive_family": sensitive,
    }


def main():
    parser = argparse.ArgumentParser(description="Inspect test memory")
    parser.add_argument("--user-id", type=str, default="")
    args = parser.parse_args()

    inspect_memory(args.user_id)


if __name__ == "__main__":
    main()
