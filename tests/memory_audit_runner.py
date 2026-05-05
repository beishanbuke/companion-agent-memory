#!/usr/bin/env python3
"""
Memory Audit Runner (Phase 10.1 Upgrade)

审计长对话中的记忆使用：
1. Seed profile recall
2. Conversation fact extraction
3. Natural memory use
4. Memory precision
5. Memory recall
6. Do-not-remember compliance
7. Over-personalization
8. Hallucinated memory
9. Missed personalization opportunity
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_expected_items(profile: dict[str, Any]) -> list[str]:
    """Build expected memory items from profile JSON."""
    items = []

    # Basic profile
    items.append(f"name/{profile.get('name', '')}")
    items.append(f"university/{profile.get('university', '')}")
    items.append(f"major/{profile.get('major', '')}")
    items.append(f"year/{profile.get('year', '')}")

    # Academic
    academic = profile.get("academic", {})
    for course in academic.get("current_courses", []):
        items.append(f"course/{course}")
    for strength in academic.get("strengths", []):
        items.append(f"strength/{strength}")
    for weakness in academic.get("weaknesses", []):
        items.append(f"weakness/{weakness}")

    # Hobbies
    hobbies = profile.get("hobbies", {})
    for food in hobbies.get("food", []):
        items.append(f"food/{food}")
    for music in hobbies.get("music", []):
        items.append(f"music/{music}")
    items.append(f"hometown/{profile.get('family', {}).get('hometown', '')}")

    # Friends
    for friend in profile.get("friends", {}).get("close_friends", []):
        items.append(f"friend/{friend['name']}")

    # Recent events
    for event in profile.get("recent_events", []):
        items.append(f"event/{event['event']}")

    return [i for i in items if i.split("/")[1]]


def audit_memory(conversation: list[dict], profile: dict[str, Any]) -> dict[str, Any]:
    """Audit memory usage across conversation."""

    expected_items = load_expected_items(profile)

    # Track which expected items were mentioned in assistant replies
    recall = {}
    for item in expected_items:
        keywords = item.split("/")
        found_turns = []
        for turn in conversation:
            assistant = turn.get("assistant", "")
            if any(kw in assistant for kw in keywords if len(kw) > 1):
                found_turns.append(turn["turn"])
        recall[item] = {
            "found": len(found_turns) > 0,
            "turns": found_turns,
            "count": len(found_turns),
        }

    # Check natural memory use (not forced "我记得")
    forced_memory = 0
    natural_memory = 0
    natural_memory_cases = []
    for turn in conversation:
        assistant = turn.get("assistant", "")
        if "我记得" in assistant or "你说过" in assistant:
            forced_memory += 1
        # Natural references: using friend names, food, places without "remember"
        natural_keywords = ["阿哲", "小满", "Rain", "螺蛳粉", "冰美式", "南宁", "落日飞车", "数字通信", "微波工程", "嵌入式"]
        found_kws = [kw for kw in natural_keywords if kw in assistant]
        if found_kws:
            if "我记得" not in assistant and "你说过" not in assistant:
                natural_memory += 1
                natural_memory_cases.append({
                    "turn": turn["turn"],
                    "user": turn.get("user", "")[:40],
                    "assistant": assistant[:60],
                    "keywords": found_kws,
                })

    # Check boundary respect
    boundary_turns = [t for t in conversation if "别记" in t.get("user", "") or "别记" in t.get("test_memory", "")]
    do_not_remember_violations = []
    for t in boundary_turns:
        assistant = t.get("assistant", "")
        memory_decision = t.get("memory_decision", {})
        action = memory_decision.get("action", "") if isinstance(memory_decision, dict) else ""
        if action not in ("ignore", "session-only"):
            do_not_remember_violations.append({
                "turn": t["turn"],
                "user": t.get("user", "")[:40],
                "assistant": assistant[:60],
                "memory_action": action,
            })
    boundary_respected = len(do_not_remember_violations) == 0

    # Check hallucinated memory (mentions not in profile)
    hallucinated_cases = []
    all_profile_text = json.dumps(profile, ensure_ascii=False)
    for turn in conversation:
        assistant = turn.get("assistant", "")
        # Simple heuristic: if assistant mentions a friend not in profile
        friend_mentions = [w for w in ["阿哲", "小满", "Rain"] if w in assistant]
        for friend in friend_mentions:
            if friend not in all_profile_text:
                hallucinated_cases.append({
                    "turn": turn["turn"],
                    "friend": friend,
                    "assistant": assistant[:60],
                })

    # Missed personalization opportunities
    missed = []
    for i, turn in enumerate(conversation):
        test_mem = turn.get("test_memory", "")
        assistant = turn.get("assistant", "")
        if "记住" in test_mem or "测试" in test_mem:
            # Check if this info was referenced in later turns
            item_hint = test_mem.replace("记住", "").replace("测试：", "").strip()
            later_text = " ".join(t.get("assistant", "") for t in conversation[i+1:])
            if item_hint and item_hint not in later_text:
                missed.append({
                    "turn": turn["turn"],
                    "hint": item_hint[:50],
                    "assistant": assistant[:60],
                })

    # Over-personalization: forcing memory mention when not relevant
    over_personalization = []
    for turn in conversation:
        assistant = turn.get("assistant", "")
        scene = turn.get("scene", "")
        if scene == "casual" and any(kw in assistant for kw in ["我记得", "你说过", "上次你说"]):
            over_personalization.append({
                "turn": turn["turn"],
                "assistant": assistant[:60],
            })

    # Calculate precision
    found_items = sum(1 for r in recall.values() if r["found"])
    precision = found_items / len(recall) if recall else 0

    # Calculate recall score (0-5)
    if precision >= 0.85:
        recall_score = 5.0
    elif precision >= 0.7:
        recall_score = 4.0
    elif precision >= 0.5:
        recall_score = 3.0
    elif precision >= 0.3:
        recall_score = 2.0
    else:
        recall_score = 1.0

    return {
        "recall": recall,
        "precision": round(precision, 2),
        "found_count": found_items,
        "total_expected": len(recall),
        "memory_recall_score": recall_score,
        "natural_memory_use_count": natural_memory,
        "natural_memory_use_cases": natural_memory_cases,
        "forced_memory_count": forced_memory,
        "missed_important_facts": missed,
        "hallucinated_memory_cases": hallucinated_cases,
        "over_personalization_cases": over_personalization,
        "do_not_remember_violations": do_not_remember_violations,
        "boundary_respected": boundary_respected,
        "boundary_turns": len(boundary_turns),
        "session_only_respected": boundary_respected,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    with open(args.log, "r", encoding="utf-8") as f:
        conversation = [json.loads(line.strip()) for line in f]

    with open(args.profile, "r", encoding="utf-8") as f:
        profile = json.load(f)

    audit = audit_memory(conversation, profile)

    print("=" * 50)
    print("MEMORY AUDIT RESULTS")
    print("=" * 50)
    print(f"  Precision: {audit['precision']} ({audit['found_count']}/{audit['total_expected']})")
    print(f"  Recall score: {audit['memory_recall_score']}/5.0")
    print(f"  Natural memory uses: {audit['natural_memory_use_count']}")
    print(f"  Forced '我记得': {audit['forced_memory_count']}")
    print(f"  Boundary respected: {audit['boundary_respected']} ({audit['boundary_turns']} turns)")
    print(f"  Do-not-remember violations: {len(audit['do_not_remember_violations'])}")
    print(f"  Hallucinated cases: {len(audit['hallucinated_memory_cases'])}")
    print(f"  Missed opportunities: {len(audit['missed_important_facts'])}")
    print(f"  Over-personalization: {len(audit['over_personalization_cases'])}")

    print(f"\n  Detailed recall:")
    for item, result in audit["recall"].items():
        status = "✅" if result["found"] else "❌"
        print(f"    {status} {item} (turns: {result['turns']})")

    args.out.mkdir(parents=True, exist_ok=True)
    out_path = args.out / "memory_audit.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(audit, f, ensure_ascii=False, indent=2)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
