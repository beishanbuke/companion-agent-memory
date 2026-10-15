import unittest
from datetime import datetime, timezone

from companion_agent.memory_adapter import TieredMemoryContext
from companion_agent.memory_lifecycle import MemoryLifecycleManager


class MemoryLifecycleManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = MemoryLifecycleManager(
            reference_time=datetime(2026, 7, 14, tzinfo=timezone.utc)
        )

    def test_deleted_and_contradicted_memories_are_not_injected(self) -> None:
        context = TieredMemoryContext(
            episodic_events=[
                {
                    "summary": "已经删除的事件",
                    "status": "deleted",
                    "updated_at": "2026-07-01T00:00:00+00:00",
                },
                {
                    "summary": "被纠正的旧偏好事件",
                    "status": "contradicted",
                    "updated_at": "2026-07-01T00:00:00+00:00",
                },
                {
                    "summary": "可用事件",
                    "status": "active",
                    "updated_at": "2026-07-01T00:00:00+00:00",
                },
            ]
        )

        trace = self.manager.apply(context, snapshot={})

        self.assertEqual(len(context.episodic_events), 1)
        self.assertEqual(context.episodic_events[0]["summary"], "可用事件")
        self.assertEqual(trace["episodic_events"][0]["lifecycle_state"], "deleted")
        self.assertFalse(trace["episodic_events"][0]["injectable"])
        self.assertEqual(trace["episodic_events"][1]["lifecycle_state"], "contradicted")
        self.assertFalse(trace["episodic_events"][1]["injectable"])

    def test_historical_memory_only_injects_for_history_query(self) -> None:
        current_context = TieredMemoryContext(
            long_term_goals=[
                {
                    "description": "以前想去日本交换",
                    "status": "historical",
                    "date": "2026-01-01T00:00:00+00:00",
                }
            ]
        )
        self.manager.apply(current_context, snapshot={}, query="我明天怎么安排？")

        history_context = TieredMemoryContext(
            long_term_goals=[
                {
                    "description": "以前想去日本交换",
                    "status": "historical",
                    "date": "2026-01-01T00:00:00+00:00",
                }
            ]
        )
        self.manager.apply(history_context, snapshot={}, query="我以前有什么目标？")

        self.assertEqual(current_context.long_term_goals, [])
        self.assertEqual(len(history_context.long_term_goals), 1)

    def test_event_freshness_decays_faster_than_profile(self) -> None:
        old_date = "2026-01-01T00:00:00+00:00"

        event_meta = self.manager.evaluate_item(
            tier="episodic_events",
            item={"status": "active", "updated_at": old_date},
        )
        profile_meta = self.manager.evaluate_item(
            tier="profile",
            item={"status": "active", "updated_at": old_date},
        )

        self.assertLess(event_meta.freshness, profile_meta.freshness)
        self.assertEqual(event_meta.lifecycle_state, "stale")

    def test_repeated_preference_evidence_increases_confidence(self) -> None:
        single = self.manager.evaluate_item(
            tier="preferences",
            item={"status": "active", "updated_at": "2026-07-01T00:00:00+00:00"},
        )
        repeated = self.manager.evaluate_item(
            tier="preferences",
            item={
                "status": "active",
                "updated_at": "2026-07-01T00:00:00+00:00",
                "evidence_count": 4,
            },
        )

        self.assertGreater(repeated.confidence, single.confidence)
        self.assertEqual(repeated.evidence_count, 4)

    def test_safety_notes_do_not_auto_decay(self) -> None:
        metadata = self.manager.evaluate_item(
            tier="safety_notes",
            item={"status": "active", "updated_at": "2020-01-01T00:00:00+00:00"},
        )

        self.assertEqual(metadata.freshness, 1.0)
        self.assertEqual(metadata.lifecycle_state, "active")

    def test_preference_snapshot_status_controls_mapping_injection(self) -> None:
        context = TieredMemoryContext(
            preferences={
                "favorite_beverage": "喜欢拿铁",
                "favorite_food": "喜欢面食",
            }
        )
        snapshot = {
            "preference_slots": {
                "favorite_beverage": {
                    "value": "喜欢拿铁",
                    "status": "contradicted",
                    "updated_at": "2026-07-01T00:00:00+00:00",
                },
                "favorite_food": {
                    "value": "喜欢面食",
                    "status": "active",
                    "updated_at": "2026-07-01T00:00:00+00:00",
                },
            },
            "preference_profiles": {},
        }

        trace = self.manager.apply(context, snapshot=snapshot)

        self.assertEqual(context.preferences, {"favorite_food": "喜欢面食"})
        self.assertFalse(trace["preferences"][0]["injectable"])
        self.assertTrue(trace["preferences"][1]["injectable"])


if __name__ == "__main__":
    unittest.main()
