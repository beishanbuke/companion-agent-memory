#!/usr/bin/env python3
"""
Memory Audit Runner
审计长对话中的记忆使用：记住了什么、漏记了什么、错记了什么。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def audit_memory(conversation: list[dict], expected_items: list[str]) -> dict[str, Any]:
    """Audit memory usage across conversation."""
    
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
    for turn in conversation:
        assistant = turn.get("assistant", "")
        if "我记得" in assistant or "你说过" in assistant:
            forced_memory += 1
        # Natural references: using friend names, food, places without "remember"
        if any(kw in assistant for kw in ["阿哲", "小满", "Rain", "螺蛳粉", "冰美式", "南宁", "落日飞车"]):
            if "我记得" not in assistant and "你说过" not in assistant:
                natural_memory += 1

    # Check boundary respect
    boundary_turns = [t for t in conversation if "别记" in t.get("user", "") or "别记" in t.get("test_memory", "")]
    boundary_respected = all("记得" not in t.get("assistant", "") or "懂的" in t.get("assistant", "") for t in boundary_turns)

    # Find missed personalization opportunities
    missed = []
    for turn in conversation:
        test_mem = turn.get("test_memory", "")
        assistant = turn.get("assistant", "")
        if "记住" in test_mem:
            # Check if this info was used in later turns
            item_keywords = test_mem.replace("记住", "").replace("测试：", "").strip()
            # Simple heuristic: if the item was supposed to be remembered but never referenced again
            # This is a simplified check
            pass

    # Calculate precision
    found_items = sum(1 for r in recall.values() if r["found"])
    precision = found_items / len(recall) if recall else 0

    return {
        "recall": recall,
        "precision": round(precision, 2),
        "found_count": found_items,
        "total_expected": len(expected_items),
        "forced_memory_count": forced_memory,
        "natural_memory_count": natural_memory,
        "boundary_respected": boundary_respected,
        "boundary_turns": len(boundary_turns),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    with open(args.log, "r", encoding="utf-8") as f:
        conversation = [json.loads(line.strip()) for line in f]

    with open(args.scenario, "r", encoding="utf-8") as f:
        scenario = json.load(f)

    expected_items = scenario.get("expected_memory_items", [])
    audit = audit_memory(conversation, expected_items)

    print(f"Memory Audit Results")
    print(f"  Precision: {audit['precision']} ({audit['found_count']}/{audit['total_expected']})")
    print(f"  Natural memory uses: {audit['natural_memory_count']}")
    print(f"  Forced '我记得': {audit['forced_memory_count']}")
    print(f"  Boundary respected: {audit['boundary_respected']} ({audit['boundary_turns']} turns)")
    print(f"\nDetailed recall:")
    for item, result in audit["recall"].items():
        status = "✅" if result["found"] else "❌"
        print(f"  {status} {item} (turns: {result['turns']})")

    args.out.mkdir(parents=True, exist_ok=True)
    out_path = args.out / "memory_audit.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(audit, f, ensure_ascii=False, indent=2)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
