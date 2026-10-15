import unittest

from companion_agent.memory_adapter import MemoryLayerAdapter


class _FakeMemoryEngine:
    def snapshot(self):
        return {
            "persona_slots": {
                "name": {"value": "小雨"},
                "home_city": {"value": "广州"},
                "occupation": {"value": "自由插画师"},
                "work_context": {"value": "绘本项目"},
            },
            "preference_slots": {
                "favorite_beverage": {"value": "喜欢冰美式"},
                "favorite_food": {"value": "喜欢面食"},
            },
            "preference_profiles": {},
            "memories": [
                {
                    "memory_type": "event",
                    "summary": "上周和朋友打篮球",
                    "content": "上周和朋友打篮球，很开心",
                    "updated_at": "2026-06-01T00:00:00+00:00",
                    "status": "active",
                    "tags": [],
                },
                {
                    "memory_type": "event",
                    "summary": "最近总是晚睡",
                    "content": "最近总是晚睡",
                    "updated_at": "2026-06-02T00:00:00+00:00",
                    "status": "active",
                    "tags": ["goal"],
                },
            ],
        }

    async def retrieve(self, query: str = "", limit: int = 6):
        return f"query={query}, limit={limit}"


class MemoryLayerAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_retrieve_tiered_respects_selected_tiers_and_limits(self) -> None:
        adapter = MemoryLayerAdapter(_FakeMemoryEngine())

        context = await adapter.retrieve_tiered(
            query="喝什么",
            tiers=["preferences"],
            max_per_tier={"preferences": 1},
        )

        self.assertEqual(context.profile, {})
        self.assertEqual(context.long_term_goals, [])
        self.assertEqual(context.episodic_events, [])
        self.assertEqual(len(context.preferences), 1)
        self.assertEqual(context.memory_count, 1)

    async def test_retrieve_tiered_applies_global_limit(self) -> None:
        adapter = MemoryLayerAdapter(_FakeMemoryEngine())

        context = await adapter.retrieve_tiered(query="我", limit=2)

        self.assertEqual(context.memory_count, 2)
        self.assertIn("profile", context.lifecycle_trace)
        self.assertTrue(context.lifecycle_trace["profile"])

    async def test_empty_tier_selection_retrieves_no_structured_memory(self) -> None:
        adapter = MemoryLayerAdapter(_FakeMemoryEngine())

        context = await adapter.retrieve_tiered(query="我", tiers=[])

        self.assertEqual(context.memory_count, 0)

    async def test_global_limit_preserves_router_tier_priority(self) -> None:
        adapter = MemoryLayerAdapter(_FakeMemoryEngine())

        context = await adapter.retrieve_tiered(
            query="我",
            tiers=["episodic_events", "profile"],
            max_per_tier={"episodic_events": 2, "profile": 2},
            limit=2,
        )

        self.assertEqual(len(context.episodic_events), 2)
        self.assertEqual(len(context.profile), 0)

    async def test_query_aware_profile_slot_selection(self) -> None:
        adapter = MemoryLayerAdapter(_FakeMemoryEngine())

        context = await adapter.retrieve_tiered(
            query="你还记得我现在住在哪里、做什么吗？",
            tiers=["profile"],
            max_per_tier={"profile": 2},
        )

        self.assertEqual(list(context.profile), ["home_city", "occupation"])

    async def test_query_aware_preference_slot_selection(self) -> None:
        adapter = MemoryLayerAdapter(_FakeMemoryEngine())

        context = await adapter.retrieve_tiered(
            query="我下午有点困，想买杯喝的，别太甜。",
            tiers=["preferences"],
            max_per_tier={"preferences": 1},
        )

        self.assertEqual(list(context.preferences), ["favorite_beverage"])


if __name__ == "__main__":
    unittest.main()
