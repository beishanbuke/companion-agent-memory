"""Replay sampled conversation JSON files against the structured memory backend.

Usage:
    python replay_conversation_dataset.py \
        --dataset /mnt/dengzhijie/mydata/memory/crawl/conversations \
        --samples 3 \
        --seed 7
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from memory import StructuredLongTermMemory


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--seed", type=int, default=7)
    return parser.parse_args()


async def replay_profile(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))

    with TemporaryDirectory() as tmpdir:
        store_path = Path(tmpdir) / f"{path.stem}_memory.json"
        memory = StructuredLongTermMemory(file_path=str(store_path))

        for seed_text in collect_seed_facts(data):
            await memory.store("user", seed_text)

        for utterance in collect_user_turns(data):
            await memory.store("user", utterance)

        before_update = memory.snapshot()
        synthetic_updates = build_synthetic_updates(before_update)
        for update in synthetic_updates:
            await memory.store("user", update["utterance"])

        after_update = memory.snapshot()

        queries = build_queries(after_update)
        recalls = {}
        for label, query in queries.items():
            recalls[label] = await memory.retrieve(query=query)

        return {
            "profile_id": data.get("profile_id", path.stem),
            "file": str(path),
            "seed_fact_count": len(collect_seed_facts(data)),
            "user_turn_count": len(collect_user_turns(data)),
            "synthetic_updates": synthetic_updates,
            "conflicts_before": len(before_update["conflicts"]),
            "conflicts_after": len(after_update["conflicts"]),
            "update_effects": summarize_update_effects(before_update, after_update, synthetic_updates),
            "persona_slots": after_update["persona_slots"],
            "preference_slots": after_update["preference_slots"],
            "recalls": recalls,
        }


def collect_seed_facts(data: dict[str, Any]) -> list[str]:
    profile = data.get("profile", {})
    facts = []

    raw_facts = profile.get("raw_facts", [])
    facts.extend(raw_facts)

    occupation = profile.get("occupation", {}).get("description")
    if occupation:
        facts.append(occupation)

    personality = profile.get("personality", {}).get("description")
    if personality:
        facts.append(personality)

    for item in profile.get("interests_like", [])[:4]:
        thing = item.get("item")
        if thing:
            facts.append(f"I enjoy {thing}.")

    for item in profile.get("dislikes", [])[:3]:
        thing = item.get("item")
        if thing:
            facts.append(f"I don't like {thing}.")

    return dedupe_texts(facts)


def collect_user_turns(data: dict[str, Any]) -> list[str]:
    utterances: list[str] = []
    for event in data.get("events", []):
        for session in event.get("sessions", []):
            for turn in session.get("turns", []):
                if turn.get("speaker") == "user" and turn.get("text"):
                    utterances.append(turn["text"])
    return utterances


def build_synthetic_updates(snapshot: dict[str, Any]) -> list[dict[str, str]]:
    updates: list[dict[str, str]] = []
    preferences = snapshot.get("preference_slots", {})
    persona = snapshot.get("persona_slots", {})

    if "favorite_beverage" in preferences:
        updates.append(
            {
                "slot_key": "favorite_beverage",
                "utterance": "My favorite drink now is chamomile tea.",
                "expected_value_contains": "chamomile tea",
            }
        )
    if "favorite_food" in preferences:
        updates.append(
            {
                "slot_key": "favorite_food",
                "utterance": "My favorite food now is grilled salmon.",
                "expected_value_contains": "grilled salmon",
            }
        )
    if "activity_style" in preferences:
        updates.append(
            {
                "slot_key": "activity_style",
                "utterance": "I enjoy quiet walks now.",
                "expected_value_contains": "quiet walks",
            }
        )
    if "living_preference" in preferences:
        updates.append(
            {
                "slot_key": "living_preference",
                "utterance": "I want to live in a quiet mountain town now.",
                "expected_value_contains": "mountain town",
            }
        )
    if "relationship_status" in persona:
        updates.append(
            {
                "slot_key": "relationship_status",
                "utterance": "I am remarried now.",
                "expected_value_contains": "remarried",
            }
        )

    if not updates:
        updates.append(
            {
                "slot_key": "favorite_beverage",
                "utterance": "My favorite drink now is herbal tea.",
                "expected_value_contains": "herbal tea",
            }
        )

    return updates[:2]


def build_queries(snapshot: dict[str, Any]) -> dict[str, str]:
    queries = {
        "identity": "What do you remember about me and my background?",
        "preference": "What do you remember about my preferences and favorite things?",
        "recent_context": "What important longer-term context should you remember about what has been happening in my life?",
    }
    if "favorite_beverage" in snapshot.get("preference_slots", {}):
        queries["beverage_update"] = "What is my current favorite drink?"
    if "relationship_status" in snapshot.get("persona_slots", {}):
        queries["relationship_update"] = "What is my current relationship status?"
    return queries


def dedupe_texts(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def choose_samples(dataset: Path, samples: int, seed: int) -> list[Path]:
    files = sorted(path for path in dataset.glob("*.json") if path.is_file())
    rng = random.Random(seed)
    if samples >= len(files):
        return files
    return sorted(rng.sample(files, samples))


def summarize_update_effects(
    before_update: dict[str, Any],
    after_update: dict[str, Any],
    synthetic_updates: list[dict[str, str]],
) -> list[dict[str, Any]]:
    effects = []
    before_persona = before_update.get("persona_slots", {})
    before_preference = before_update.get("preference_slots", {})
    after_persona = after_update.get("persona_slots", {})
    after_preference = after_update.get("preference_slots", {})

    for update in synthetic_updates:
        slot_key = update["slot_key"]
        before_slot = before_persona.get(slot_key) or before_preference.get(slot_key)
        after_slot = after_persona.get(slot_key) or after_preference.get(slot_key)
        before_value = before_slot.get("value") if before_slot else None
        after_value = after_slot.get("value") if after_slot else None
        effects.append(
            {
                "slot_key": slot_key,
                "utterance": update["utterance"],
                "before_value": before_value,
                "after_value": after_value,
                "updated": before_value != after_value,
                "matched_expected": bool(
                    after_value and update["expected_value_contains"].lower() in after_value.lower()
                ),
            }
        )
    return effects


async def main() -> None:
    args = parse_args()
    sample_files = choose_samples(args.dataset, args.samples, args.seed)

    reports = []
    for path in sample_files:
        reports.append(await replay_profile(path))

    print(json.dumps({"seed": args.seed, "samples": reports}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
