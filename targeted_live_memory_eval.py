"""Targeted real-profile evaluation for the long-term memory system.

This script uses a small curated subset of real JSON profiles and applies
deliberate follow-up updates so we can inspect whether the system:
1. seeds stable long-term memories from profile facts and conversation turns,
2. updates slot memories when newer facts arrive,
3. records conflicts for overwritten slots,
4. retrieves the latest state in query-time recall.

Run:
    python targeted_live_memory_eval.py
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from memory import StructuredLongTermMemory

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - fallback when dotenv is unavailable
    load_dotenv = None


DATASET_DIR = Path("/mnt/dengzhijie/mydata/memory/crawl/conversations")

TARGET_CASES = [
    {
        "profile_id": "00a1406672cb",
        "description": "nurse profile with relationship, drink, and work-context updates",
        "seed_raw_fact_indexes": [0, 1, 3, 4],
        "seed_event_pairs": [(0, 0), (1, 0)],
        "updates": [
            "I am remarried now.",
            "My favorite drink now is chamomile tea.",
            "I work in pediatrics now instead of the emergency room.",
        ],
        "queries": [
            "What do you remember about my relationship status, work context, and favorite drink?",
        ],
        "watch_slots": ["relationship_status", "favorite_beverage", "work_context"],
    },
    {
        "profile_id": "03fd78176c2c",
        "description": "mother/nurse profile with food and music preference changes",
        "seed_raw_fact_indexes": [0, 1, 2, 3, 4],
        "seed_event_pairs": [(0, 0), (1, 0)],
        "updates": [
            "My favorite food now is grilled salmon.",
            "My favorite band now is Fleetwood Mac.",
        ],
        "queries": [
            "What do you remember about my favorite food and music now?",
        ],
        "watch_slots": ["favorite_food", "music_style", "occupation"],
    },
    {
        "profile_id": "01c44fccffbc",
        "description": "retired social profile with living-preference and social-style updates",
        "seed_raw_fact_indexes": [0, 1, 3, 4],
        "seed_event_pairs": [(0, 0), (1, 0)],
        "updates": [
            "I want to live in a quiet mountain town now.",
            "I do not like talking to strangers anymore.",
        ],
        "queries": [
            "What do you remember about where I want to live and my social preferences now?",
        ],
        "watch_slots": ["living_preference", "social_style"],
    },
]


async def main() -> None:
    if load_dotenv is not None:
        load_dotenv(override=True)

    reports = []
    for case in TARGET_CASES:
        reports.append(await evaluate_case(case))

    print(json.dumps({"cases": reports}, ensure_ascii=False, indent=2))


async def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    profile_path = DATASET_DIR / f"{case['profile_id']}.json"
    data = json.loads(profile_path.read_text(encoding="utf-8"))
    seed_utterances = collect_seed_utterances(data, case)

    with TemporaryDirectory() as tmpdir:
        store_path = Path(tmpdir) / f"{case['profile_id']}_memory.json"
        memory = StructuredLongTermMemory(file_path=str(store_path))

        for utterance in seed_utterances:
            await memory.store("user", utterance)

        before_snapshot = memory.snapshot()

        for utterance in case["updates"]:
            await memory.store("user", utterance)

        after_snapshot = memory.snapshot()
        recalls = {
            query: await memory.retrieve(query)
            for query in case["queries"]
        }

    return {
        "profile_id": case["profile_id"],
        "description": case["description"],
        "seed_utterances": seed_utterances,
        "updates": case["updates"],
        "before_slots": watch_slot_values(before_snapshot, case["watch_slots"]),
        "after_slots": watch_slot_values(after_snapshot, case["watch_slots"]),
        "conflicts_before": len(before_snapshot["conflicts"]),
        "conflicts_after": len(after_snapshot["conflicts"]),
        "recent_conflicts": after_snapshot["conflicts"][-5:],
        "recalls": recalls,
    }


def collect_seed_utterances(data: dict[str, Any], case: dict[str, Any]) -> list[str]:
    profile = data.get("profile", {})
    utterances: list[str] = []

    raw_facts = profile.get("raw_facts", [])
    for index in case["seed_raw_fact_indexes"]:
        if 0 <= index < len(raw_facts):
            utterances.append(raw_facts[index])

    events = data.get("events", [])
    for event_index, session_index in case["seed_event_pairs"]:
        if not (0 <= event_index < len(events)):
            continue
        sessions = events[event_index].get("sessions", [])
        if not (0 <= session_index < len(sessions)):
            continue
        first_user_turn = next(
            (
                turn.get("text", "").strip()
                for turn in sessions[session_index].get("turns", [])
                if turn.get("speaker") == "user" and turn.get("text")
            ),
            "",
        )
        if first_user_turn:
            utterances.append(first_user_turn)

    deduped = []
    seen = set()
    for utterance in utterances:
        if utterance and utterance not in seen:
            seen.add(utterance)
            deduped.append(utterance)
    return deduped


def watch_slot_values(snapshot: dict[str, Any], slot_keys: list[str]) -> dict[str, str | None]:
    persona = snapshot.get("persona_slots", {})
    preference = snapshot.get("preference_slots", {})
    values = {}
    for key in slot_keys:
        values[key] = (
            persona.get(key, {}).get("value")
            or preference.get(key, {}).get("value")
        )
    return values


if __name__ == "__main__":
    asyncio.run(main())
