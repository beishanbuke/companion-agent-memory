#!/usr/bin/env python3
"""
Long-Chat Scenario Runner
35+ 轮连续对话测试，验证记忆、个性化和回复质量。

Phase 10.1 升级：
- 完整 debug / policy / memory / timing 采集
- quality flags 自动标记
- latency 统计与 slow turn 识别
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
SLOW_TURN_THRESHOLD_MS = 30000


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
    user_id: str,
    reset: bool = False,
) -> dict[str, Any]:
    """Call chat API and return full response with metadata."""
    payload = {
        "message": message,
        "session_id": session_id,
        "user_id": user_id,
        "memory_enabled": True,
        "use_v2_brain": True,
        "debug": True,
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

        debug = data.get("debug", {})
        companion = data.get("companion", {})
        context_meta = data.get("context_meta", {})

        # Extract full policy from debug
        policy_debug = debug.get("policy", {})
        policy = {
            "goal": policy_debug.get("goal", companion.get("brain_mode", "")),
            "allow_advice": policy_debug.get("allow_advice", False),
            "allow_micro_action": getattr(policy_debug, "allow_micro_action", False) if not isinstance(policy_debug, dict) else policy_debug.get("allow_micro_action", False),
            "allow_direct_pick": getattr(policy_debug, "allow_direct_pick", False) if not isinstance(policy_debug, dict) else policy_debug.get("allow_direct_pick", False),
            "pull_mode": policy_debug.get("pull_mode", "silent"),
            "skill_verbosity": policy_debug.get("skill_verbosity", "hint"),
            "max_questions": policy_debug.get("max_questions", 0) if isinstance(policy_debug, dict) else 0,
            "response_length": policy_debug.get("response_length", "short") if isinstance(policy_debug, dict) else "short",
            "allow_humor": policy_debug.get("allow_humor", True) if isinstance(policy_debug, dict) else True,
            "pull_main_thread": policy_debug.get("pull_main_thread", False) if isinstance(policy_debug, dict) else False,
            "reason": getattr(policy_debug, "reason", "") if not isinstance(policy_debug, dict) else policy_debug.get("reason", ""),
            "hard_constraints": getattr(policy_debug, "hard_constraints", []) if not isinstance(policy_debug, dict) else policy_debug.get("hard_constraints", []),
        }

        # Memory tracking
        memory_decision = companion.get("memory_decision", {})
        memory_write_skipped = debug.get("memory_write_skipped", memory_decision.get("action", "") == "ignore")
        updates = data.get("updates", [])
        memory_written = [u for u in updates if u.get("change_type") in ("add", "update", "pending")]

        # Memory retrieved from debug
        memory_preview = data.get("memory_preview", "")
        memory_retrieved = []
        if memory_preview:
            # Simple extraction: split by newlines and take non-empty lines
            memory_retrieved = [line.strip() for line in memory_preview.split("\n") if line.strip() and not line.strip().startswith("-")]

        # Stage timings
        stage_timings = debug.get("stage_timings", {})

        # Quality flags
        quality_flags = []
        if not policy.get("goal"):
            quality_flags.append("longchat_debug_missing_policy")
        if not stage_timings:
            quality_flags.append("longchat_stage_timings_missing")
        if not debug:
            quality_flags.append("longchat_memory_trace_missing")

        return {
            "reply": data.get("reply", ""),
            "debug": debug,
            "policy": policy,
            "memory_decision": memory_decision,
            "memory_retrieved": memory_retrieved,
            "memory_written": memory_written,
            "memory_write_skipped": memory_write_skipped,
            "stage_timings": stage_timings,
            "quality_flags": quality_flags,
            "companion": companion,
            "context_meta": context_meta,
            "full_response": data,
        }
    except Exception as exc:
        return {"error": str(exc), "reply": "", "quality_flags": ["api_error"]}


async def run_scenario(
    client: httpx.AsyncClient,
    scenario: dict[str, Any],
    session_id: str,
    user_id: str,
    out_dir: Path,
    reset_memory_flag: bool = False,
) -> list[dict[str, Any]]:
    """Run full long-chat scenario."""
    turns = scenario.get("turns", [])
    print(f"Running {len(turns)} turns for session {session_id} (user={user_id})...")

    if reset_memory_flag:
        await reset_memory(client, user_id)
        print("Memory reset.")

    results = []
    latencies = []
    slow_turns = []

    for i, turn in enumerate(turns):
        user_msg = turn["user"]
        print(f"\n[Turn {i+1}/{len(turns)}] {user_msg[:40]}...")

        start = time.time()
        result = await call_chat(client, user_msg, session_id, user_id, reset=(i == 0))
        latency = round((time.time() - start) * 1000, 1)
        latencies.append(latency)

        # Check slow turn
        if latency > SLOW_TURN_THRESHOLD_MS:
            slow_turns.append({"turn": i + 1, "latency_ms": latency, "user": user_msg[:40]})
            if result.get("quality_flags") is not None:
                result["quality_flags"].append("slow_turn")

        if "error" in result and result["error"]:
            print(f"  [ERROR] {result['error']}")
            results.append({
                "turn": i + 1,
                "user": user_msg,
                "error": result["error"],
                "scene": turn.get("scene", ""),
                "expect": turn.get("expect", ""),
                "test_memory": turn.get("test_memory", ""),
                "latency_ms": latency,
                "quality_flags": result.get("quality_flags", []),
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
            "debug": result.get("debug", {}),
            "policy": result.get("policy", {}),
            "memory_decision": result.get("memory_decision", {}),
            "memory_retrieved": result.get("memory_retrieved", []),
            "memory_written": result.get("memory_written", []),
            "memory_write_skipped": result.get("memory_write_skipped", False),
            "stage_timings": result.get("stage_timings", {}),
            "quality_flags": result.get("quality_flags", []),
            "companion": result.get("companion", {}),
            "context_meta": result.get("context_meta", {}),
        }
        results.append(record)

        # Small delay between turns
        await asyncio.sleep(0.5)

    # Calculate latency statistics
    if latencies:
        latencies_sorted = sorted(latencies)
        n = len(latencies_sorted)
        p50 = latencies_sorted[n // 2] if n % 2 == 1 else (latencies_sorted[n // 2 - 1] + latencies_sorted[n // 2]) / 2
        p95_idx = int(n * 0.95)
        p95 = latencies_sorted[min(p95_idx, n - 1)]
    else:
        p50 = p95 = 0

    latency_summary = {
        "avg_ms": round(sum(latencies) / max(len(latencies), 1), 1),
        "p50_ms": round(p50, 1),
        "p95_ms": round(p95, 1),
        "max_ms": round(max(latencies) if latencies else 0, 1),
        "slow_turns": slow_turns,
    }

    # Quality flag aggregation
    all_flags = []
    for r in results:
        all_flags.extend(r.get("quality_flags", []))
    flag_counts = {}
    for f in all_flags:
        flag_counts[f] = flag_counts.get(f, 0) + 1

    # Save results
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = out_dir / "conversation.jsonl"
    with open(log_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    summary = {
        "scenario_id": scenario.get("scenario_id", ""),
        "session_id": session_id,
        "user_id": user_id,
        "total_turns": len(turns),
        "successful_turns": len([r for r in results if "error" not in r]),
        "error_turns": len([r for r in results if "error" in r]),
        "latency_summary": latency_summary,
        "quality_flag_counts": flag_counts,
        "run_trusted": len(slow_turns) <= 3 and flag_counts.get("longchat_debug_missing_policy", 0) == 0,
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
    print(f"Avg latency: {latency_summary['avg_ms']}ms")
    print(f"P95 latency: {latency_summary['p95_ms']}ms")
    print(f"Slow turns: {len(slow_turns)}")
    print(f"Quality flags: {flag_counts}")
    print(f"Run trusted: {summary['run_trusted']}")
    print(f"Log saved: {log_path}")

    return results


async def main():
    parser = argparse.ArgumentParser(description="Long-Chat Scenario Runner")
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--session-id", type=str, default="long_chat_test")
    parser.add_argument("--user-id", type=str, default="test_user")
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
            args.user_id,
            args.out,
            reset_memory_flag=args.reset_memory,
        )


if __name__ == "__main__":
    asyncio.run(main())
