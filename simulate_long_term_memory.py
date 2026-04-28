"""Synthetic dialogue test for the structured long-term memory demo.

Run:
    python simulate_long_term_memory.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

from memory import StructuredLongTermMemory
from memory.structured import MemoryCandidate


class ScriptedExtractor:
    """Mock extraction stage used to validate the two-stage write pipeline."""

    def __init__(self, mapping: dict[str, list[MemoryCandidate]]):
        self._mapping = mapping

    async def __call__(self, content: str) -> list[MemoryCandidate]:
        return self._mapping.get(content, [])


async def main() -> None:
    with TemporaryDirectory() as tmpdir:
        store_path = Path(tmpdir) / "long_term_memory.json"
        extractor = ScriptedExtractor(
            {
                "我叫小雨，是一名插画师，住在上海。": [
                    MemoryCandidate(
                        memory_type="persona",
                        slot_key="name",
                        value="小雨",
                        summary="用户姓名是小雨",
                        content="我叫小雨，是一名插画师，住在上海。",
                    ),
                    MemoryCandidate(
                        memory_type="persona",
                        slot_key="occupation",
                        value="插画师",
                        summary="用户职业是插画师",
                        content="我叫小雨，是一名插画师，住在上海。",
                    ),
                    MemoryCandidate(
                        memory_type="persona",
                        slot_key="home_city",
                        value="上海",
                        summary="用户当前城市是上海",
                        content="我叫小雨，是一名插画师，住在上海。",
                    ),
                ],
                "我最近和男朋友分手了，晚上总是睡不好。": [
                    MemoryCandidate(
                        memory_type="event",
                        value="我最近和男朋友分手了，晚上总是睡不好。",
                        summary="历史事件：最近分手且睡眠不佳",
                        content="我最近和男朋友分手了，晚上总是睡不好。",
                        tags=["relationship", "sleep"],
                    )
                ],
                "我喜欢喝拿铁，不太能吃辣。": [
                    MemoryCandidate(
                        memory_type="preference",
                        slot_key="favorite_beverage",
                        value="喜欢拿铁",
                        summary="用户饮品偏好：喜欢拿铁",
                        content="我喜欢喝拿铁，不太能吃辣。",
                    ),
                    MemoryCandidate(
                        memory_type="preference",
                        slot_key="food_spice",
                        value="不太能吃辣",
                        summary="用户辣度偏好：不太能吃辣",
                        content="我喜欢喝拿铁，不太能吃辣。",
                    ),
                ],
                "其实我上个月搬到杭州了。": [
                    MemoryCandidate(
                        memory_type="persona",
                        slot_key="home_city",
                        value="杭州",
                        summary="用户当前城市是杭州",
                        content="其实我上个月搬到杭州了。",
                    ),
                    MemoryCandidate(
                        memory_type="event",
                        value="上个月搬到杭州",
                        summary="历史事件：上个月搬到杭州",
                        content="其实我上个月搬到杭州了。",
                        tags=["move"],
                    ),
                ],
                "我现在开始能吃一点辣了，但还是更喜欢清淡。": [
                    MemoryCandidate(
                        memory_type="preference",
                        slot_key="food_spice",
                        value="现在能吃一点辣",
                        summary="用户辣度偏好：现在能吃一点辣",
                        content="我现在开始能吃一点辣了，但还是更喜欢清淡。",
                    ),
                    MemoryCandidate(
                        memory_type="preference",
                        slot_key="food_flavor",
                        value="更喜欢清淡",
                        summary="用户口味偏好：更喜欢清淡",
                        content="我现在开始能吃一点辣了，但还是更喜欢清淡。",
                    ),
                ],
            }
        )

        session_one = StructuredLongTermMemory(
            file_path=str(store_path),
            candidate_extractor=extractor,
        )
        for utterance in [
            "我叫小雨，是一名插画师，住在上海。",
            "我最近和男朋友分手了，晚上总是睡不好。",
            "我喜欢喝拿铁，不太能吃辣。",
        ]:
            await session_one.store("user", utterance)

        # Re-initialize to simulate a new session reading the persisted memory.
        session_two = StructuredLongTermMemory(
            file_path=str(store_path),
            candidate_extractor=extractor,
        )

        recall_identity = await session_two.retrieve("你还记得我住在哪儿、做什么工作吗？")
        assert "上海" in recall_identity, recall_identity
        assert "插画师" in recall_identity, recall_identity

        await session_two.store("user", "其实我上个月搬到杭州了。")
        snapshot_after_move = session_two.snapshot()
        assert snapshot_after_move["persona_slots"]["home_city"]["value"] == "杭州"
        assert snapshot_after_move["conflicts"], snapshot_after_move

        await session_two.store("user", "我现在开始能吃一点辣了，但还是更喜欢清淡。")
        recall_food = await session_two.retrieve("晚饭帮我推荐一下，我最近口味怎么样？")
        assert "清淡" in recall_food, recall_food

        recall_emotion = await session_two.retrieve("我最近心情不太稳定，你知道原因吗？")
        assert "分手" in recall_emotion or "睡不好" in recall_emotion, recall_emotion

        print("=== Identity Recall ===")
        print(recall_identity)
        print("\n=== Food Recall ===")
        print(recall_food)
        print("\n=== Emotion Recall ===")
        print(recall_emotion)
        print("\nStructured memory simulation passed.")


if __name__ == "__main__":
    asyncio.run(main())
