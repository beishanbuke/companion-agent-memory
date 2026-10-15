import unittest

from companion_agent.memory_policy import MemoryUpdatePolicy


class MemoryUpdatePolicyTest(unittest.IsolatedAsyncioTestCase):
    async def test_short_preference_is_not_low_value(self) -> None:
        policy = MemoryUpdatePolicy()

        decision = await policy.evaluate(
            "我喜欢喝可乐",
            {"persona_slots": {}, "preference_slots": {}},
            "casual_chat",
        )

        self.assertEqual(decision.action, "add")
        self.assertIn("preference", decision.suggested_tags)

    async def test_short_self_fact_is_not_low_value(self) -> None:
        policy = MemoryUpdatePolicy()

        decision = await policy.evaluate(
            "我叫小雨",
            {"persona_slots": {}, "preference_slots": {}},
            "casual_chat",
        )

        self.assertEqual(decision.action, "add")
        self.assertIn("profile", decision.suggested_tags)

    async def test_short_family_visit_is_not_low_value(self) -> None:
        policy = MemoryUpdatePolicy()

        decision = await policy.evaluate(
            "我上周去看了我外婆",
            {"persona_slots": {}, "preference_slots": {}},
            "casual_chat",
        )

        self.assertEqual(decision.action, "add")
        self.assertIn("event", decision.suggested_tags)

    async def test_short_sports_events_are_not_low_value(self) -> None:
        policy = MemoryUpdatePolicy()

        for message in ["上周踢足球", "上周打羽毛球", "我上周还打了羽毛球", "上周心情很差"]:
            with self.subTest(message=message):
                decision = await policy.evaluate(
                    message,
                    {"persona_slots": {}, "preference_slots": {}},
                    "casual_chat",
                )

                self.assertEqual(decision.action, "add")
                self.assertIn("event", decision.suggested_tags)

    async def test_temporal_question_is_low_value(self) -> None:
        policy = MemoryUpdatePolicy()

        decision = await policy.evaluate(
            "上周做了什么",
            {"persona_slots": {}, "preference_slots": {}},
            "casual_chat",
        )

        self.assertEqual(decision.action, "ignore")
