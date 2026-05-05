#!/usr/bin/env python3
"""
Seed test profile into running server's memory.

通过 /api/memory/store API 向 memory engine 注入格式化的 profile 信息，
让 LLM extractor 自动提取到 persona_slots / preference_slots / memories。

敏感信息（家庭作息冲突）不主动 seed，留给长对话边界测试验证。
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import httpx

BASE_URL = "http://127.0.0.1:8765"
MEMORY_FILE = Path(__file__).resolve().parents[2] / "prototype_memory_store.json"

# 关键信息检查清单（用于 seed 后验证）
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


async def store_memory(client: httpx.AsyncClient, content: str) -> dict:
    """Store a memory via API."""
    resp = await client.post(
        f"{BASE_URL}/api/memory/store",
        json={"role": "user", "content": content},
        timeout=60.0,
    )
    resp.raise_for_status()
    return resp.json()


async def clear_memory(client: httpx.AsyncClient) -> None:
    """Clear memory via API."""
    try:
        resp = await client.post(f"{BASE_URL}/api/clear-memory", json={}, timeout=10.0)
        resp.raise_for_status()
    except Exception as exc:
        print(f"  [warn] clear-memory failed: {exc}")


def build_seed_messages(profile: dict) -> list[str]:
    """Build structured seed messages from profile JSON."""
    seeds = []

    # 1. 基本 profile + 沟通偏好
    comm = profile["communication_style"]
    seeds.append(
        f"我叫{profile['name']}，{profile['age']}岁，"
        f"在{profile['university']}{profile['major']}{profile['year']}。"
        f"性格{'、'.join(profile['personality'])}。"
        f"我喜欢{'、'.join(comm['likes'])}。"
        f"不喜欢{'、'.join(comm['dislikes'])}。"
    )

    # 2. 学业信息
    academic = profile["academic"]
    seeds.append(
        f"这学期课程：{'、'.join(academic['current_courses'])}。"
        f"我擅长{'、'.join(academic['strengths'])}。"
        f"但短板是{'、'.join(academic['weaknesses'])}。"
        f"当前压力：{'、'.join(academic['current_pressure_sources'])}。"
        f"学习习惯：{'、'.join(academic['study_preference'])}。"
    )

    # 3. 爱好
    hobbies = profile["hobbies"]
    seeds.append(
        f"食物：{'、'.join(hobbies['food'])}。"
        f"音乐：{'、'.join(hobbies['music'])}。"
        f"运动：{'、'.join(hobbies['sports'])}。"
        f"娱乐：{'、'.join(hobbies['entertainment'])}。"
        f"旅行风格：{'、'.join(hobbies['travel_style'])}。"
    )

    # 4. 家乡 + 朋友
    family = profile["family"]
    friend_parts = [f"我的朋友{f['name']}是{f['role']}，{'、'.join(f['traits'])}" for f in profile["friends"]["close_friends"]]
    seeds.append(
        f"我老家在{family['hometown']}。"
        + "。".join(friend_parts) + "。"
        f"社交风格：{'、'.join(profile['friends']['social_style'])}。"
    )

    # 5. 最近事件
    event_parts = [f"{e['event']}，感觉{e['emotion']}" for e in profile["recent_events"]]
    seeds.append("最近的事：" + "。".join(event_parts) + "。")

    return seeds


def check_memory_contents(snapshot: dict) -> dict:
    """Check if key profile items exist in memory snapshot."""
    # Flatten all text from snapshot for simple search
    all_text = json.dumps(snapshot, ensure_ascii=False)

    results = {}
    for key, keyword in CHECKLIST.items():
        results[key] = keyword in all_text

    return results


async def seed_profile(profile_path: str, user_id: str, reset: bool = False):
    with open(profile_path, "r", encoding="utf-8") as f:
        profile = json.load(f)

    async with httpx.AsyncClient() as client:
        if reset:
            print("Clearing memory...")
            await clear_memory(client)

        seeds = build_seed_messages(profile)
        print(f"Seeding {len(seeds)} profile messages...")

        for i, seed in enumerate(seeds):
            print(f"  [{i+1}/{len(seeds)}] {seed[:60]}...")
            try:
                result = await store_memory(client, seed)
                updates = result.get("updates", [])
                if updates:
                    for u in updates[:3]:
                        print(f"    -> {u.get('change_type', '?')}: {u.get('label', '')}")
                else:
                    print(f"    -> no structured updates (stored as raw event)")
            except Exception as exc:
                print(f"    [ERROR] {exc}")

        # Verify by reading the memory file directly
        print("\nVerifying memory contents...")
        await asyncio.sleep(0.5)  # Small delay for file write
        if MEMORY_FILE.exists():
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                snapshot = json.load(f)
            checks = check_memory_contents(snapshot)
            found = sum(1 for v in checks.values() if v)
            total = len(checks)
            print(f"  Checklist: {found}/{total} items found")
            for key, ok in checks.items():
                status = "✅" if ok else "❌"
                print(f"    {status} {key}")
        else:
            print("  [warn] Memory file not found, skipping verification")

        print(f"\nProfile seed complete for user={user_id}")


def main():
    parser = argparse.ArgumentParser(description="Seed test profile into memory")
    parser.add_argument("--profile", type=str, required=True)
    parser.add_argument("--user-id", type=str, required=True)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    asyncio.run(seed_profile(args.profile, args.user_id, args.reset))


if __name__ == "__main__":
    main()
