import sys
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
PROTOTYPE_DEMO_DIR = PROJECT_DIR / "prototype_demo"
if str(PROTOTYPE_DEMO_DIR) not in sys.path:
    sys.path.insert(0, str(PROTOTYPE_DEMO_DIR))

from context_engine import detect_scene, memory_query_options, pack_context_messages


class ContextEngineTests(unittest.TestCase):
    def test_detect_scene_memory_probe(self) -> None:
        self.assertEqual(detect_scene("你还记得我住哪里吗"), "memory_probe")

    def test_detect_scene_emotional_support(self) -> None:
        self.assertEqual(detect_scene("今天真的好焦虑，压力很大"), "emotional_support")

    def test_pack_context_messages_applies_scene_strategy_and_window(self) -> None:
        history = [{"role": "user", "content": f"u{i}"} for i in range(10)]
        packed = pack_context_messages(
            base_system_prompt="你是一个助手",
            user_message="我有点难过",
            short_history=history,
            memory_text="[Long-term memory]\n- event",
            ncp_payload={"invoked": False, "context_text": ""},
            strategies={
                "default": {"tone": "自然", "response_rules": ["先回应"], "memory_focus": "相关"},
                "emotional_support": {"tone": "共情", "response_rules": ["先接住情绪"], "memory_focus": "情绪相关"},
            },
            scene_router_enabled=True,
            context_packer_enabled=True,
            rerank_enabled=True,
        )

        self.assertEqual(packed.scene, "emotional_support")
        self.assertEqual(packed.history_window, 10)
        self.assertEqual(packed.memory_limit, 6)
        self.assertIn("scene", packed.memory_filters)
        self.assertEqual(packed.memory_filters["scene"], "emotional_support")
        self.assertEqual(packed.messages[0]["role"], "system")
        self.assertEqual(packed.messages[-1], {"role": "user", "content": "我有点难过"})

    def test_memory_query_options_can_disable_scene_filter(self) -> None:
        filters, _ = memory_query_options("smalltalk", rerank_enabled=False)
        self.assertNotIn("scene", filters)


if __name__ == "__main__":
    unittest.main()
