import unittest
from unittest.mock import patch

from companion_agent.memory_router import LLMJudgeMemoryRouterV1, MemoryRouter


class MemoryRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.router = MemoryRouter()

    def test_generic_question_does_not_use_memory(self) -> None:
        decision = self.router.route(
            user_message="今天天气有点热，出门要不要带薄外套？",
            situation="casual_chat",
        )

        self.assertFalse(decision.need_memory)
        self.assertEqual(decision.mention_policy, "forbid")
        self.assertEqual(decision.tiers, [])

    def test_explicit_recall_uses_explicit_policy(self) -> None:
        decision = self.router.route(
            user_message="你还记得我平时喜欢喝什么吗？",
            situation="memory_query",
        )

        self.assertTrue(decision.need_memory)
        self.assertEqual(decision.retrieval_mode, "explicit")
        self.assertEqual(decision.mention_policy, "explicit_ok")
        self.assertIn("preferences", decision.tiers)

    def test_explicit_profile_recall_has_enough_budget(self) -> None:
        decision = self.router.route(
            user_message="你还记得我现在住在哪里、做什么吗？",
            situation="memory_query",
            current_memory_snapshot={
                "persona_slots": {
                    "name": {"value": "小雨"},
                    "home_city": {"value": "杭州"},
                    "occupation": {"value": "自由插画师"},
                }
            },
        )

        self.assertTrue(decision.need_memory)
        self.assertEqual(decision.retrieval_mode, "explicit")
        self.assertIn("profile", decision.tiers)
        self.assertGreaterEqual(decision.max_per_tier.get("profile", 0), 5)
        self.assertGreaterEqual(decision.max_items, 5)

    def test_personalized_advice_uses_background_preferences(self) -> None:
        decision = self.router.route(
            user_message="下午有点困，我想买杯喝的。",
            situation="casual_chat",
        )

        self.assertTrue(decision.need_memory)
        self.assertEqual(decision.retrieval_mode, "background")
        self.assertEqual(decision.mention_policy, "implicit_only")
        self.assertIn("preferences", decision.tiers)

    def test_beverage_advice_prioritizes_preferences_only(self) -> None:
        decision = self.router.route(
            user_message="我下午有点困，想买杯喝的，别太甜。",
            situation="casual_chat",
            current_memory_snapshot={
                "preference_slots": {"favorite_beverage": {"value": "喜欢冰美式；不喜欢拿铁"}},
                "memories": [{"memory_type": "event", "summary": "用户上周赶稿很累"}],
            },
        )

        self.assertTrue(decision.need_memory)
        self.assertEqual(decision.retrieval_mode, "background")
        self.assertEqual(decision.tiers, ["preferences"])

    def test_explicit_disable_overrides_everything(self) -> None:
        decision = self.router.route(
            user_message="别参考我以前的口味，直接给我一个大众推荐。",
            situation="casual_chat",
        )

        self.assertFalse(decision.need_memory)
        self.assertEqual(decision.mention_policy, "forbid")

    def test_short_term_context_request_is_not_long_term_memory(self) -> None:
        decision = self.router.route(
            user_message="我刚才说了啥？",
            situation="memory_query",
        )

        self.assertFalse(decision.need_memory)

    def test_personalized_coding_request_overrides_situation_hint(self) -> None:
        decision = self.router.route(
            user_message="按我之前的编码习惯重构这段 Python。",
            situation="coding_helper",
            current_memory_snapshot={"preferences": {"coding_style": "简洁"}},
        )

        self.assertTrue(decision.need_memory)
        self.assertEqual(decision.mention_policy, "implicit_only")
        self.assertIn("preferences", decision.tiers)

    def test_generic_beginner_request_does_not_personalize(self) -> None:
        decision = self.router.route(
            user_message="给我一个适合新手的番茄钟工作法说明。",
            situation="casual_chat",
            current_memory_snapshot={"preferences": {"study_style": "短时专注"}},
        )

        self.assertFalse(decision.need_memory)

    def test_background_route_filters_unavailable_tiers(self) -> None:
        decision = self.router.route(
            user_message="我今天有点累。",
            situation="emotional_support",
            current_memory_snapshot={"preferences": {"support_style": "温柔"}},
        )

        self.assertEqual(decision.tiers, ["preferences"])
        self.assertTrue(decision.tier_scores)
        self.assertTrue(decision.signals)

    def test_empty_snapshot_disables_background_but_not_explicit_recall(self) -> None:
        background = self.router.route(
            user_message="我今天有点累。",
            situation="emotional_support",
            current_memory_snapshot={},
        )
        explicit = self.router.route(
            user_message="你还记得我喜欢喝什么吗？",
            situation="memory_query",
            current_memory_snapshot={},
        )

        self.assertFalse(background.need_memory)
        self.assertTrue(explicit.need_memory)
        self.assertEqual(explicit.tiers, [])

    def test_memory_followup_uses_history(self) -> None:
        decision = self.router.route(
            user_message="那我呢？",
            conversation_history=[{"role": "user", "content": "你记得我以前喜欢什么音乐吗？"}],
            current_memory_snapshot={"preferences": {"music": "lo-fi"}},
        )

        self.assertTrue(decision.need_memory)
        self.assertIn("memory_followup", decision.signals)

    def test_available_tiers_include_tagged_memories(self) -> None:
        decision = self.router.route(
            user_message="我这个长期目标第一步该怎么做？",
            situation="planning",
            current_memory_snapshot={
                "memories": [
                    {
                        "memory_type": "event",
                        "summary": "用户想长期改善作息",
                        "tags": ["goal"],
                    }
                ]
            },
        )

        self.assertTrue(decision.need_memory)
        self.assertIn("long_term_goals", decision.tiers)

    def test_llm_judge_router_falls_back_without_api_key(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            router = MemoryRouter(version="llm_judge_v1")
            decision = router.route(
                user_message="你还记得我现在住在哪里、做什么吗？",
                situation="memory_query",
                current_memory_snapshot={
                    "persona_slots": {
                        "home_city": {"value": "广州"},
                        "occupation": {"value": "自由插画师"},
                    }
                },
            )

        self.assertTrue(decision.need_memory)
        self.assertEqual(decision.retrieval_mode, "explicit")
        self.assertIn("profile", decision.tiers)
        self.assertIn("llm_judge_failed", decision.signals)

    def test_llm_judge_cannot_suppress_explicit_recall(self) -> None:
        router = LLMJudgeMemoryRouterV1()
        with patch.object(
            router,
            "_judge",
            return_value={
                "need_memory": False,
                "retrieval_mode": "none",
                "tiers": [],
                "mention_policy": "forbid",
                "confidence": 0.8,
                "reason": "mock_wrong_no_memory",
                "signals": ["mock"],
                "tier_scores": {},
            },
        ):
            decision = router.route(
                user_message="你还记得我现在住在哪里、做什么吗？",
                situation="memory_query",
                current_memory_snapshot={
                    "persona_slots": {
                        "home_city": {"value": "广州"},
                        "occupation": {"value": "自由插画师"},
                    }
                },
            )

        self.assertTrue(decision.need_memory)
        self.assertEqual(decision.retrieval_mode, "explicit")
        self.assertEqual(decision.mention_policy, "explicit_ok")
        self.assertIn("profile", decision.tiers)
        self.assertIn("llm_judge_guardrail", decision.signals)

    def test_llm_judge_cannot_suppress_strong_background_memory(self) -> None:
        router = LLMJudgeMemoryRouterV1()
        with patch.object(
            router,
            "_judge",
            return_value={
                "need_memory": False,
                "retrieval_mode": "none",
                "tiers": [],
                "mention_policy": "forbid",
                "confidence": 0.8,
                "reason": "mock_wrong_no_memory",
                "signals": ["mock"],
                "tier_scores": {},
            },
        ):
            decision = router.route(
                user_message="我下午有点困，想买杯喝的，别太甜。",
                situation="casual_chat",
                current_memory_snapshot={
                    "preference_slots": {
                        "favorite_beverage": {"value": "喜欢冰美式；不喜欢拿铁"}
                    }
                },
            )

        self.assertTrue(decision.need_memory)
        self.assertEqual(decision.retrieval_mode, "background")
        self.assertIn("preferences", decision.tiers)
        self.assertIn("llm_judge_guardrail", decision.signals)


if __name__ == "__main__":
    unittest.main()
