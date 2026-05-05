#!/usr/bin/env python3
"""
Long-Chat Scenario Runner
35+ 轮连续对话测试，验证记忆、个性化和回复质量。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import Any

import httpx

BASE_URL = "http://127.0.0.1:8765"


async def reset_memory(client: httpx.AsyncClient, user_id: str) -> None:
    """Reset memory for test user."""
    try:
        await client.post(f"{BASE_URL}/api/clear-memory", json={}, timeout=10.0)
    except Exception:
        pass


async def call_chat(
    client: httpx.AsyncClient,
    message: str,
    session_id: str,
    reset: bool = False,
) -> dict[str, Any]:
    """Call chat API and return full response with metadata."""
    payload = {
        "message": message,
        "session_id": session_id,
        "use_v2_brain": True,
    }
    if reset:
        payload["reset"] = True

    try:
        resp = await client.post(
            f"{BASE_URL}/api/chat",
            json=payload,
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "reply": data.get("reply", ""),
            "metadata": {
                "intent_primary": data.get("companion", {}).get("situation", ""),
                "policy_goal": data.get("context_meta", {}).get("policy.goal", ""),
                "policy_allow_advice": data.get("context_meta", {}).get("policy.allow_advice"),
                "current_state": data.get("companion", {}).get("current_state", ""),
                "conversation_rhythm": data.get("companion", {}).get("conversation_rhythm", ""),
                "memory_decision": data.get("companion", {}).get("memory_decision", {}),
                "emotional_state": data.get("companion", {}).get("emotional_state", ""),
                "stage_timings": data.get("stage_timings", {}),
                "v2_brain": data.get("context_meta", {}).get("v2_brain", False),
                "legacy_fallback_used": data.get("context_meta", {}).get("legacy_fallback_used", False),
            },
            "full_response": data,
        }
    except Exception as exc:
        return {"error": str(exc), "reply": ""}


async def run_scenario(
    client: httpx.AsyncClient,
    scenario: dict[str, Any],
    session_id: str,
    out_dir: Path,
    reset_memory_flag: bool = False,
) -> list[dict[str, Any]]:
    """Run full long-chat scenario."""
    turns = scenario.get("turns", [])
    print(f"Running {len(turns)} turns for session {session_id}...")

    if reset_memory_flag:
        await reset_memory(client, session_id)
        print("Memory reset.")

    results = []
    for i, turn in enumerate(turns):
        user_msg = turn["user"]
        print(f"\n[Turn {i+1}/{len(turns)}] {user_msg[:40]}...")

        start = time.time()
        result = await call_chat(client, user_msg, session_id, reset=(i == 0))
        latency = round((time.time() - start) * 1000, 1)

        if "error" in result and result["error"]:
            print(f"  [ERROR] {result['error']}")
            results.append({
                "turn": i + 1,
                "user": user_msg,
                "error": result["error"],
                "scene": turn.get("scene", ""),
                "expect": turn.get("expect", ""),
                "test_memory": turn.get("test_memory", ""),
            })
            continue

        reply = result["reply"]
        print(f"  -> {reply[:80]}...")

        record = {
            "turn": i + 1,
            "user": user_msg,
            "assistant": reply,
            "scene": turn.get("scene", ""),
            "expect": turn.get("expect", ""),
            "test_memory": turn.get("test_memory", ""),
            "latency_ms": latency,
            **result["metadata"],
        }
        results.append(record)

        # Small delay between turns
        await asyncio.sleep(0.5)

    # Save results
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "conversation.jsonl"
    with open(log_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    summary = {
        "scenario_id": scenario.get("scenario_id", ""),
        "session_id": session_id,
        "total_turns": len(turns),
        "successful_turns": len([r for r in results if "error" not in r]),
        "error_turns": len([r for r in results if "error" in r]),
        "avg_latency_ms": round(sum(r.get("latency_ms", 0) for r in results) / max(len(results), 1), 1),
    }
    summary_path = out_dir / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*50}")
    print("LONG CHAT COMPLETE")
    print(f"{'='*50}")
    print(f"Total turns: {summary['total_turns']}")
    print(f"Successful: {summary['successful_turns']}")
    print(f"Errors: {summary['error_turns']}")
    print(f"Avg latency: {summary['avg_latency_ms']}ms")
    print(f"Log saved: {log_path}")

    return results


async def main():
    parser = argparse.ArgumentParser(description="Long-Chat Scenario Runner")
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--session-id", type=str, default="long_chat_test")
    parser.add_argument("--out", type=Path, default=Path("tests/long_chat_results/run_default"))
    parser.add_argument("--reset-memory", action="store_true")
    args = parser.parse_args()

    with open(args.scenario, "r", encoding="utf-8") as f:
        scenario = json.load(f)

    async with httpx.AsyncClient() as client:
        await run_scenario(
            client,
            scenario,
            args.session_id,
            args.out,
            reset_memory_flag=args.reset_memory,
        )


if __name__ == "__main__":
    asyncio.run(main())
