import unittest

from companion_agent.memory_adapter import TieredMemoryContext
from companion_agent.memory_router import MemoryRouteDecision
from companion_agent.memory_verifier import MemoryUseVerifier


class MemoryUseVerifierTests(unittest.TestCase):
    def test_verifier_detects_profile_memory_use(self) -> None:
        verifier = MemoryUseVerifier()
        context = TieredMemoryContext(
            profile={"home_city": "广州", "occupation": "自由插画师"},
            memory_count=2,
        )
        route = MemoryRouteDecision(
            need_memory=True,
            retrieval_mode="explicit",
            tiers=["profile"],
            mention_policy="explicit_ok",
            max_per_tier={"profile": 5},
        )

        result = verifier.verify(
            user_message="你还记得我现在住在哪里、做什么吗？",
            assistant_reply="你现在在广州，是自由插画师。",
            memory_context=context,
            memory_route=route,
        )

        self.assertEqual(result.status, "ok")
        self.assertIn("广州", result.matched_terms)

    def test_verifier_flags_missed_preference_memory(self) -> None:
        verifier = MemoryUseVerifier()
        context = TieredMemoryContext(
            preferences={"favorite_beverage": ["like 喜欢冰美式", "dislike 不喜欢拿铁"]},
            memory_count=1,
        )
        route = MemoryRouteDecision(
            need_memory=True,
            retrieval_mode="background",
            tiers=["preferences"],
            mention_policy="implicit_only",
            max_per_tier={"preferences": 2},
        )

        result = verifier.verify(
            user_message="我下午有点困，想买杯喝的，别太甜。",
            assistant_reply="可以喝杯温水，或者随便选一杯咖啡。",
            memory_context=context,
            memory_route=route,
        )

        self.assertEqual(result.status, "missed")
        self.assertIn("冰美式", result.missing_terms)


if __name__ == "__main__":
    unittest.main()
