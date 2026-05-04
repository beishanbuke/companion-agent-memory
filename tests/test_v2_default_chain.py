"""Test that the default v2 chain is used in server.py."""

import inspect
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any
import pytest

# Add project root to path
project_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_dir))
sys.path.insert(0, str(project_dir / "prototype_demo"))

from prototype_demo.server import DemoSession


# ---------------------------------------------------------------------------
# Unit tests: signature checks (fast, no service needed)
# ---------------------------------------------------------------------------

def test_send_message_defaults_to_v2_brain() -> None:
    sig = inspect.signature(DemoSession.send_message)
    param = sig.parameters.get("use_v2_brain")
    assert param is not None, "use_v2_brain parameter not found in send_message"
    assert param.default is True, f"use_v2_brain should default to True, got {param.default}"


def test_stream_message_defaults_to_v2_brain() -> None:
    sig = inspect.signature(DemoSession.stream_message)
    param = sig.parameters.get("use_v2_brain")
    assert param is not None, "use_v2_brain parameter not found in stream_message"
    assert param.default is True, f"use_v2_brain should default to True, got {param.default}"


def test_context_engine_v2_defaults_to_false() -> None:
    """Ensure the legacy context_engine_v2 flag defaults to False."""
    sig_send = inspect.signature(DemoSession.send_message)
    param_send = sig_send.parameters.get("context_engine_v2")
    assert param_send is not None
    assert param_send.default is False, f"context_engine_v2 in send_message should default to False, got {param_send.default}"

    sig_stream = inspect.signature(DemoSession.stream_message)
    param_stream = sig_stream.parameters.get("context_engine_v2")
    assert param_stream is not None
    assert param_stream.default is False, f"context_engine_v2 in stream_message should default to False, got {param_stream.default}"


# ---------------------------------------------------------------------------
# Integration helpers (require running server on :8765)
# ---------------------------------------------------------------------------

RUN_INTEGRATION = False  # set to True when server is running


@dataclass
class MockIntent:
    primary_intent: str = "companion"
    emotional_state: str = "neutral"
    emotional_intensity: float = 0.3
    conversation_rhythm: str = "chill"
    task_category: str = "none"
    task_urgency: float = 0.0
    action_receptivity: float = 0.5
    topic_shift_type: str = "none"
    pressure_signal: float = 0.0
    intent_confidence: float = 0.8
    clarification_confidence: float = 0.0
    thread_candidates: list = field(default_factory=list)


@pytest.mark.skipif(not RUN_INTEGRATION, reason="integration tests disabled; start server on :8765")
def test_api_chat_defaults_to_v2_brain() -> None:
    import requests
    resp = requests.post(
        "http://127.0.0.1:8765/api/chat",
        json={"message": "在吗", "memory_enabled": True},
        timeout=30,
    )
    data = resp.json()
    context_meta = data.get("context_meta", {})
    assert context_meta.get("v2_brain") is True, f"expected v2_brain=True, got {context_meta}"


@pytest.mark.skipif(not RUN_INTEGRATION, reason="integration tests disabled")
def test_api_chat_stream_defaults_to_v2_brain() -> None:
    import requests
    resp = requests.post(
        "http://127.0.0.1:8765/api/chat-stream",
        json={"message": "在吗", "memory_enabled": True},
        timeout=30,
        stream=True,
    )
    # Read the final payload from SSE stream
    final_payload = None
    for line in resp.iter_lines():
        if not line:
            continue
        text = line.decode("utf-8", errors="ignore")
        if text.startswith("data:"):
            payload = text[5:].strip()
            if payload == "[DONE]":
                break
            try:
                import json
                chunk = json.loads(payload)
                if chunk.get("type") == "final":
                    final_payload = chunk.get("payload", {})
            except Exception:
                pass
    assert final_payload is not None, "no final payload in stream"
    context_meta = final_payload.get("context_meta", {})
    assert context_meta.get("v2_brain") is True


@pytest.mark.skipif(not RUN_INTEGRATION, reason="integration tests disabled")
def test_v2_debug_contains_state_policy_pull_mode() -> None:
    import requests
    resp = requests.post(
        "http://127.0.0.1:8765/api/chat",
        json={"message": "在吗", "memory_enabled": True, "debug": True},
        timeout=30,
    )
    data = resp.json()
    debug = data.get("debug", {})
    state = debug.get("state", {})
    policy = debug.get("policy", {})
    assert "current_state" in state, f"missing state.current_state in debug: {debug.keys()}"
    assert "goal" in policy, f"missing policy.goal in debug: {policy.keys()}"
    assert "pull_mode" in policy, f"missing policy.pull_mode in debug: {policy.keys()}"
    assert "skill_verbosity" in policy, f"missing policy.skill_verbosity in debug: {policy.keys()}"


@pytest.mark.skipif(not RUN_INTEGRATION, reason="integration tests disabled")
def test_legacy_fallback_only_when_disabled() -> None:
    import requests
    resp = requests.post(
        "http://127.0.0.1:8765/api/chat",
        json={"message": "在吗", "memory_enabled": True, "use_v2_brain": False},
        timeout=30,
    )
    data = resp.json()
    context_meta = data.get("context_meta", {})
    # Legacy path should NOT have v2_brain=True
    assert context_meta.get("v2_brain") is not True, "legacy path should not claim v2_brain=True"


@pytest.mark.skipif(not RUN_INTEGRATION, reason="integration tests disabled")
def test_context_meta_has_brain_version() -> None:
    import requests
    resp = requests.post(
        "http://127.0.0.1:8765/api/chat",
        json={"message": "在吗", "memory_enabled": True},
        timeout=30,
    )
    data = resp.json()
    context_meta = data.get("context_meta", {})
    # This is aspirational; if not present yet, xfail instead of fail
    if "brain_version" not in context_meta:
        pytest.xfail("brain_version not yet implemented in context_meta")
    assert context_meta.get("brain_version") == "v2.1"


if __name__ == "__main__":
    test_send_message_defaults_to_v2_brain()
    test_stream_message_defaults_to_v2_brain()
    test_context_engine_v2_defaults_to_false()
    print("All fast unit tests passed!")
