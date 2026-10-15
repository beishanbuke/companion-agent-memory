import asyncio
import unittest
from types import SimpleNamespace

from companion_agent.core import CompanionAgentCore


class _FakeMemoryEngine:
    def __init__(self):
        self.stored: list[tuple[str, str]] = []

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
        self.stored.append((role, content))


def _raising_client(counter: dict) -> SimpleNamespace:
    """Stand-in openai client whose completions.create raises when called."""

    async def _create(**kwargs):
        counter["llm_calls"] += 1
        raise RuntimeError("LLM called despite feature switch disabled")

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=_create)))


def _offline_emotion_detector(core: CompanionAgentCore) -> None:
    core.emotion_detector._judge_with_llm = lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("offline")
    )


class CompanionCoreFeatureSwitchTests(unittest.IsolatedAsyncioTestCase):
    async def _build_core(self, *, router_llm: bool, policy_llm: bool):
        engine = _FakeMemoryEngine()
        core = CompanionAgentCore(
            memory_engine=engine,
            enable_llm_router=router_llm,
            enable_llm_memory_policy=policy_llm,
        )
        counter = {"llm_calls": 0}
        core.router._client = _raising_client(counter)
        core.memory_policy._client = _raising_client(counter)
        _offline_emotion_detector(core)
        return core, engine, counter

    async def test_disabled_switches_make_no_llm_calls(self) -> None:
        core, engine, counter = await self._build_core(router_llm=False, policy_llm=False)

        result = await core.process_message(
            "我最近开始学着做手冲咖啡，想把它变成每天早上的习惯",
            conversation_history=[],
            memory_enabled=True,
        )

        self.assertEqual(counter["llm_calls"], 0)
        self.assertIn(result.situation, core.router.SITUATIONS)
        self.assertFalse(result.safety_flag)
        # Rule-based policy still flags the durable preference/habit.
        self.assertEqual(result.memory_decision.action, "add")
        # Background store runs to completion without any LLM call.
        self.assertTrue(result.memory_updated)
        self.assertIsNotNone(result.store_future)
        await asyncio.wrap_future(result.store_future)
        self.assertEqual(engine.stored, [("user", "我最近开始学着做手冲咖啡，想把它变成每天早上的习惯")])

    async def test_disabled_switches_work_with_memory_disabled(self) -> None:
        core, _engine, counter = await self._build_core(router_llm=False, policy_llm=False)

        result = await core.process_message(
            "随便聊聊，今天天气真不错",
            conversation_history=[],
            memory_enabled=False,
        )

        self.assertEqual(counter["llm_calls"], 0)
        self.assertEqual(result.memory_decision.action, "ignore")
        self.assertFalse(result.memory_updated)
        self.assertIsNone(result.store_future)

    async def test_core_timings_recorded_for_each_stage(self) -> None:
        core, _engine, _counter = await self._build_core(router_llm=False, policy_llm=False)

        result = await core.process_message("你好呀", conversation_history=[])

        timings = result.debug_info["core_timings"]
        for key in (
            "snapshot_ms",
            "wave1_ms",
            "emotion_ms",
            "routing_ms",
            "policy_ms",
            "retrieve_ms",
            "total_ms",
        ):
            self.assertIn(key, timings)


if __name__ == "__main__":
    unittest.main()
