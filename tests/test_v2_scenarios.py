#!/usr/bin/env python3
"""
V2 核心场景回归测试

运行4个黄金场景的固定回归样例，验证：
- goal 是否正确
- target_state 是否正确
- 是否误拉回主线
- 是否触发复盘模式
- 是否生成 next_action
- 是否写入 review_summary

用法：
    uv run python tests/test_v2_scenarios.py

要求：
    服务必须在 http://127.0.0.1:8765 运行
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Any

import requests

BASE_URL = "http://127.0.0.1:8765"
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "v2_conversations"


def load_fixture(name: str) -> list[dict[str, Any]]:
    """加载场景 fixture。"""
    path = FIXTURES_DIR / f"{name}.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def check_expected(actual: dict[str, Any], expected: dict[str, Any], context: str = "") -> list[str]:
    """检查结果是否符合预期。"""
    errors = []
    for key, expected_val in expected.items():
        actual_val = actual.get(key)
        
        if key.endswith("_in"):
            real_key = key[:-3]
            actual_val = actual.get(real_key)
            if actual_val not in expected_val:
                errors.append(f"{context} {real_key}={actual_val!r} not in {expected_val}")
        elif key.startswith("has_"):
            real_key = key[4:]
            sub_actual = actual.get(real_key) if isinstance(actual, dict) else None
            if not sub_actual:
                errors.append(f"{context} missing or empty '{real_key}'")
        elif isinstance(expected_val, dict):
            if actual_val is None:
                errors.append(f"{context} {key}=None, expected nested checks")
                continue
            for sub_key, sub_expected in expected_val.items():
                if sub_key.startswith("has_"):
                    sub_real_key = sub_key[4:]
                    sub_actual_val = actual_val.get(sub_real_key) if isinstance(actual_val, dict) else None
                    if not sub_actual_val:
                        errors.append(f"{context} {key}.{sub_real_key} missing or empty")
                elif sub_key.endswith("_in"):
                    sub_real_key = sub_key[:-3]
                    sub_actual_val = actual_val.get(sub_real_key) if isinstance(actual_val, dict) else None
                    if sub_actual_val not in sub_expected:
                        errors.append(f"{context} {key}.{sub_real_key}={sub_actual_val!r} not in {sub_expected}")
                else:
                    sub_actual_val = actual_val.get(sub_key) if isinstance(actual_val, dict) else None
                    if sub_actual_val != sub_expected:
                        errors.append(f"{context} {key}.{sub_key}={sub_actual_val!r} != {sub_expected!r}")
        else:
            if actual_val != expected_val:
                errors.append(f"{context} {key}={actual_val!r} != {expected_val!r}")
    
    return errors


def send_message(message: str, session_id: str) -> dict[str, Any]:
    """发送消息并返回响应。"""
    resp = requests.post(
        f"{BASE_URL}/api/chat",
        json={
            "message": message,
            "memory_enabled": True,
            "use_v2_brain": True,
            "session_id": session_id,
            "user_id": "test-user",
        },
        timeout=60,
    )
    data = resp.json()
    if "error" in data:
        raise RuntimeError(data["error"])
    return data


def run_scenario(fixture: dict[str, Any]) -> list[str]:
    """运行一个场景并返回所有错误。"""
    errors = []
    scenario_name = fixture["scenario"]
    description = fixture.get("description", scenario_name)
    turns = fixture["turns"]
    
    print(f"\n{'='*60}")
    print(f"场景: {description}")
    print(f"{'='*60}")
    
    session_id = f"test-{scenario_name}-{uuid.uuid4().hex[:8]}"
    
    for i, turn in enumerate(turns):
        user_msg = turn["user"]
        expected = turn.get("expected", {})
        
        print(f"\n  第{i+1}轮: {user_msg[:40]}...")
        
        try:
            data = send_message(user_msg, session_id)
        except Exception as e:
            errors.append(f"第{i+1}轮异常: {e}")
            print(f"    ❌ 异常: {e}")
            continue
        
        # 提取 companion 信息
        companion = data.get("companion", {})
        
        # 检查 policy goal
        if "policy_goal" in expected or "policy_goal_in" in expected:
            goal = companion.get("brain_mode", "")
            if "policy_goal_in" in expected:
                if goal not in expected["policy_goal_in"]:
                    errors.append(f"第{i+1}轮 brain_mode={goal!r} not in {expected['policy_goal_in']}")
            elif goal != expected.get("policy_goal"):
                errors.append(f"第{i+1}轮 brain_mode={goal!r} != {expected.get('policy_goal')!r}")
        
        # 检查 target_state
        current_state = companion.get("current_state", "")
        if "target_state" in expected:
            if current_state != expected["target_state"]:
                errors.append(f"第{i+1}轮 current_state={current_state!r} != {expected['target_state']!r}")
        elif "target_state_in" in expected:
            if current_state not in expected["target_state_in"]:
                errors.append(f"第{i+1}轮 current_state={current_state!r} not in {expected['target_state_in']}")
        
        # 检查 allow_advice / allow_humor（从 debug 中获取）
        debug_info = data.get("debug") or data.get("debug_info", {})
        policy_debug = debug_info.get("policy", {}) if isinstance(debug_info, dict) else {}
        
        if "allow_advice" in expected:
            actual = policy_debug.get("allow_advice")
            if actual != expected["allow_advice"]:
                errors.append(f"第{i+1}轮 allow_advice={actual!r} != {expected['allow_advice']!r}")
        
        if "allow_humor" in expected:
            actual = policy_debug.get("allow_humor")
            if actual != expected["allow_humor"]:
                errors.append(f"第{i+1}轮 allow_humor={actual!r} != {expected['allow_humor']!r}")
        
        # 检查 review_summary
        review_summary = data.get("review_summary")
        if "review_summary_scope" in expected:
            if review_summary is None:
                errors.append(f"第{i+1}轮 review_summary=None")
            elif review_summary.get("scope") != expected["review_summary_scope"]:
                errors.append(f"第{i+1}轮 review_summary.scope={review_summary.get('scope')!r} != {expected['review_summary_scope']!r}")
        
        if "review_summary_structured" in expected:
            if review_summary is None:
                errors.append(f"第{i+1}轮 review_summary=None")
            else:
                struct = review_summary.get("structured", {})
                for sub_key, sub_expected in expected["review_summary_structured"].items():
                    if sub_key.startswith("has_"):
                        sub_real_key = sub_key[4:]
                        actual_val = struct.get(sub_real_key)
                        if not actual_val:
                            errors.append(f"第{i+1}轮 review_summary.structured.{sub_real_key} missing or empty")
                    elif sub_key.endswith("_in"):
                        sub_real_key = sub_key[:-3]
                        actual_val = struct.get(sub_real_key)
                        if actual_val not in sub_expected:
                            errors.append(f"第{i+1}轮 review_summary.structured.{sub_real_key}={actual_val!r} not in {sub_expected}")
        
        # 检查是否误拉回主线
        if expected.get("pull_main_thread") is False:
            # 检查 active_thread 是否变化或 policy 是否包含 resume_main_thread
            if companion.get("brain_mode") == "resume_main_thread":
                errors.append(f"第{i+1}轮 误拉回主线: brain_mode=resume_main_thread")
        
        if any(e.startswith(f"第{i+1}轮") for e in errors):
            for e in errors:
                if e.startswith(f"第{i+1}轮"):
                    print(f"    ❌ {e}")
        else:
            print(f"    ✅ 通过")
    
    return errors


def main():
    print("="*60)
    print("Companion Agent v2 核心场景回归测试")
    print("="*60)
    
    # 检查服务状态
    try:
        resp = requests.post(f"{BASE_URL}/api/companion/status", json={}, timeout=5)
        print(f"\n✅ 服务状态: {resp.status_code}")
    except Exception as e:
        print(f"\n❌ 服务未启动: {e}")
        print("请先运行: ./start_prototype_demo.sh")
        sys.exit(1)
    
    all_errors: list[str] = []
    
    scenarios = [
        "high_pressure_switch",
        "daily_review",
        "weekly_review",
        "vent_then_push",
    ]
    
    for name in scenarios:
        fixtures = load_fixture(name)
        for fixture in fixtures:
            errors = run_scenario(fixture)
            all_errors.extend(errors)
    
    # 总结
    print("\n" + "="*60)
    print("测试结果")
    print("="*60)
    
    if all_errors:
        print(f"\n❌ 共 {len(all_errors)} 个失败:\n")
        for e in all_errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("\n✅ 所有场景通过")
        sys.exit(0)


if __name__ == "__main__":
    main()
