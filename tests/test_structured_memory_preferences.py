import os
import tempfile
import unittest

from memory.structured import StructuredLongTermMemory


class StructuredMemoryPreferenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        fd, self.store_path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.unlink(self.store_path)
        self.memory = StructuredLongTermMemory(file_path=self.store_path)

    async def asyncTearDown(self) -> None:
        await self.memory.clear()

    async def test_dislike_only_replaces_targeted_beverage(self) -> None:
        await self.memory.store("user", "我喜欢拿铁")
        await self.memory.store("user", "我喜欢美式")
        await self.memory.store("user", "我现在讨厌拿铁了")

        snapshot = self.memory.snapshot()
        active_values = [
            item["value"]
            for item in snapshot["preference_profiles"].get("favorite_beverage", [])
            if item["status"] == "active"
        ]

        self.assertIn("喜欢美式", active_values)
        self.assertIn("不喜欢拿铁", active_values)
        self.assertNotIn("喜欢拿铁", active_values)

    async def test_compound_beverage_preference_is_split_before_update(self) -> None:
        await self.memory.store("user", "我喜欢拿铁和美式")
        await self.memory.store("user", "我现在讨厌拿铁了")

        snapshot = self.memory.snapshot()
        active_values = [
            item["value"]
            for item in snapshot["preference_profiles"].get("favorite_beverage", [])
            if item["status"] == "active"
        ]

        self.assertEqual(set(active_values), {"喜欢美式", "不喜欢拿铁"})


if __name__ == "__main__":
    unittest.main()
