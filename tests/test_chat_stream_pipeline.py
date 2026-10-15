import json
import os
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parent.parent
PROTOTYPE_DIR = PROJECT_DIR / "prototype_demo"
MCP_SHARED_DIR = PROJECT_DIR / "mcp" / "shared"
for path in (str(PROJECT_DIR), str(MCP_SHARED_DIR), str(PROTOTYPE_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

import server  # noqa: E402
from companion_agent.core import CompanionAgentCore  # noqa: E402

# Importing server loads the project's .env via load_dotenv(override=True),
# which sets MEMORY_LLM_API_KEY and turns RemoteLLMMemoryExtractor /
# RemoteLLMWriteResolver "live" for every StructuredLongTermMemory built
# afterwards — making unrelated tests hit the real network and flake on rate
# limits. The pre-existing suite never loaded .env, so drop the key to keep
# that deterministic behavior.
os.environ.pop("MEMORY_LLM_API_KEY", None)


class _FakeMemoryEngine:
    def snapshot(self) -> dict:
        return {
            "persona_slots": {},
            "preference_slots": {},
            "preference_profiles": {},
            "memories": [],
        }

    async def retrieve(self, query: str = "", limit: int = 6):
        return ""

    async def store(self, role: str, content: str) -> None:
        return None


def _build_core() -> CompanionAgentCore:
    core = CompanionAgentCore(memory_engine=_FakeMemoryEngine())
    core.router._client = None
    core.memory_policy._client = None
    core.emotion_detector._judge_with_llm = lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("offline")
    )
    return core


def _build_session() -> "server.DemoSession":
    return server.DemoSession(memory=_FakeMemoryEngine(), companion_core=_build_core())


def _stub_turn_side_effects(monkeypatch) -> None:
    monkeypatch.setattr(
        server, "run_mcp_context_tools", lambda *a, **k: ([], [], None, None)
    )
    monkeypatch.setattr(server, "persist_emotion_output", lambda *a, **k: None)


# ---------------------------------------------------------------------------
# Task 6: final event precedes the background memory rewrite
# ---------------------------------------------------------------------------


def test_stream_final_precedes_background_rewrite(monkeypatch) -> None:
    session = _build_session()
    _stub_turn_side_effects(monkeypatch)
    monkeypatch.setattr(
        server, "iter_chat_completion_chunks", lambda messages: iter(["你好", "呀"])
    )

    captured: dict[str, str] = {}
    rewrite_done = threading.Event()

    def fake_rewrite(*, user_message, assistant_reply, original_messages, companion_result):
        captured["assistant_reply"] = assistant_reply
        time.sleep(0.2)
        rewrite_done.set()
        return "改写后的话", {"rewrite_applied": True}

    monkeypatch.setattr(server, "maybe_rewrite_with_memory", fake_rewrite)

    events = list(session.stream_message("早上好", memory_enabled=True))
    assert [event["type"] for event in events] == ["assistant_delta", "assistant_delta", "final"]

    final_event = events[-1]
    assert final_event["payload"]["reply"] == "你好呀"
    # The final event (and its history snapshot) carries the pre-rewrite text.
    assert final_event["payload"]["messages"][-1]["content"] == "你好呀"
    # The rewrite is scheduled after final and has not finished yet.
    assert not rewrite_done.is_set()

    # Once the rewrite completes, the stored history turn is updated and the
    # pending flag is released.
    assert rewrite_done.wait(timeout=5)
    deadline = time.time() + 5
    while time.time() < deadline:
        if session.short_history and session.short_history[-1]["content"] == "改写后的话":
            break
        time.sleep(0.01)
    assert session.short_history[-1]["content"] == "改写后的话"
    assert captured["assistant_reply"] == "你好呀"
    assert session.history_write_pending.is_set()
    verifier = session.last_companion_debug.get("memory_use_verifier")
    assert verifier == {"rewrite_applied": True}


def test_stream_rewrite_failure_releases_pending_flag(monkeypatch) -> None:
    session = _build_session()
    _stub_turn_side_effects(monkeypatch)
    monkeypatch.setattr(server, "iter_chat_completion_chunks", lambda messages: iter(["嗯"]))

    def failing_rewrite(**kwargs):
        raise RuntimeError("rewrite provider down")

    monkeypatch.setattr(server, "maybe_rewrite_with_memory", failing_rewrite)

    events = list(session.stream_message("在吗", memory_enabled=True))
    assert events[-1]["type"] == "final"
    assert session.history_write_pending.wait(timeout=5)
    # Original reply kept in history when the rewrite fails.
    assert session.short_history[-1]["content"] == "嗯"


# ---------------------------------------------------------------------------
# Task 8: mid-stream failure must not replay the whole stream
# ---------------------------------------------------------------------------


def _stub_endpoints(monkeypatch, fake_stream):
    calls: list[str] = []
    monkeypatch.setattr(server, "_endpoint_candidates", lambda endpoint: ["ep1", "ep2"])
    monkeypatch.setattr(server, "_chat_api_config", lambda: ("key", "ep", "model"))

    def tracked_stream(endpoint, api_key, payload):
        calls.append(endpoint)
        return fake_stream(endpoint)

    monkeypatch.setattr(server, "_stream_chat_completion_once", tracked_stream)
    return calls


def test_midstream_failure_does_not_replay(monkeypatch) -> None:
    def fake_stream(endpoint):
        if endpoint == "ep1":
            yield "你好"
            raise RuntimeError("connection dropped mid-stream")
        yield "不该出现"

    calls = _stub_endpoints(monkeypatch, fake_stream)
    monkeypatch.setattr(
        server,
        "call_chat_completion",
        lambda messages: (_ for _ in ()).throw(AssertionError("non-streaming fallback must not run")),
    )

    seen: list[str] = []
    with pytest.raises(RuntimeError, match="connection dropped"):
        for chunk in server.iter_chat_completion_chunks([{"role": "user", "content": "hi"}]):
            seen.append(chunk)

    assert seen == ["你好"]
    assert calls == ["ep1"]


def test_pre_yield_failure_retries_next_endpoint(monkeypatch) -> None:
    def fake_stream(endpoint):
        if endpoint == "ep1":
            raise RuntimeError("connect refused")
        yield "完整回复"

    calls = _stub_endpoints(monkeypatch, fake_stream)

    chunks = list(
        server.iter_chat_completion_chunks([{"role": "user", "content": "hi"}])
    )

    assert chunks == ["完整回复"]
    assert calls == ["ep1", "ep2"]


# ---------------------------------------------------------------------------
# SSE contract smoke over real HTTP
# ---------------------------------------------------------------------------


def _post_chat_stream(port: int, message: str) -> tuple[str, str, bytes]:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/chat-stream",
        data=json.dumps({"message": message, "memory_enabled": True}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.headers.get("Content-Type", ""), resp.headers.get("Connection", ""), resp.read()


def test_chat_stream_http_sse_contract(monkeypatch) -> None:
    session = _build_session()
    _stub_turn_side_effects(monkeypatch)
    monkeypatch.setattr(server, "SESSION", session)
    monkeypatch.setattr(
        server,
        "iter_chat_completion_chunks",
        lambda messages: iter(["早上好", "，今天", "也想你"]),
    )
    monkeypatch.setattr(
        server,
        "maybe_rewrite_with_memory",
        lambda **kwargs: (kwargs["assistant_reply"], {"rewrite_applied": False}),
    )

    httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.PrototypeHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        content_type, connection, raw = _post_chat_stream(
            httpd.server_address[1], "早上好"
        )
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)

    assert content_type == "application/x-ndjson; charset=utf-8"
    assert connection == "close"

    lines = [line for line in raw.decode("utf-8").splitlines() if line.strip()]
    events = [json.loads(line) for line in lines]
    assert [event["type"] for event in events] == [
        "assistant_delta",
        "assistant_delta",
        "assistant_delta",
        "final",
    ]
    for event in events[:3]:
        assert set(event.keys()) == {"type", "delta"}
        assert event["delta"]
    final_event = events[-1]
    assert set(final_event.keys()) == {"type", "payload"}
    assert final_event["payload"]["reply"] == "早上好，今天也想你"
    assert "memory_panel" in final_event["payload"]
    assert "companion" in final_event["payload"]
    assert session.history_write_pending.wait(timeout=5)


def test_chat_stream_http_error_event(monkeypatch) -> None:
    session = _build_session()
    _stub_turn_side_effects(monkeypatch)
    monkeypatch.setattr(server, "SESSION", session)

    def failing_chunks(messages):
        raise RuntimeError("provider down")
        yield  # pragma: no cover - keeps this a generator

    monkeypatch.setattr(server, "iter_chat_completion_chunks", failing_chunks)

    httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.PrototypeHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        _content_type, _connection, raw = _post_chat_stream(
            httpd.server_address[1], "在吗"
        )
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)

    lines = [line for line in raw.decode("utf-8").splitlines() if line.strip()]
    events = [json.loads(line) for line in lines]
    assert events[-1]["type"] == "error"
    assert "provider down" in events[-1]["error"]
