"""Academic memory slot unit tests.

Verify MemoryLayerAdapter extracts academic_profile from memory snapshots.
"""

import sys
from pathlib import Path

project_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_dir))

from companion_agent.memory_adapter import MemoryLayerAdapter


class MockMemoryEngine:
    """Mock memory engine with academic-related memories."""

    def __init__(self, snapshot_data: dict):
        self._snapshot = snapshot_data

    async def retrieve(self, query: str = "", limit: int = 6) -> str:
        return ""

    async def store(self, role: str, content: str) -> None:
        pass

    async def clear(self) -> None:
        pass

    async def delete_memory(self, memory_id: str):
        return None

    def snapshot(self) -> dict:
        return self._snapshot


def test_extract_academic_from_memories() -> None:
    """Academic info in memories should be extracted to academic_profile."""
    snapshot = {
        "persona_slots": {},
        "preference_slots": {},
        "preference_profiles": {},
        "conflicts": [],
        "memories": [
            {
                "id": "1",
                "memory_type": "event",
                "summary": "学期课程",
                "content": "这学期课程：数字通信、微波工程、现代传感技术、嵌入式系统、工程电磁场。",
                "role": "user",
                "created_at": "2026-01-01",
                "updated_at": "2026-01-01",
                "status": "active",
                "tags": [],
            },
            {
                "id": "2",
                "memory_type": "event",
                "summary": "学术优势",
                "content": "我擅长电路分析、信号系统、实验动手、报告排版、把复杂东西讲清楚。",
                "role": "user",
                "created_at": "2026-01-01",
                "updated_at": "2026-01-01",
                "status": "active",
                "tags": [],
            },
            {
                "id": "3",
                "memory_type": "event",
                "summary": "当前压力",
                "content": "当前压力：一周内有两个quiz、嵌入式project还没调完、微波工程作业没写、presentation slides还很空。",
                "role": "user",
                "created_at": "2026-01-01",
                "updated_at": "2026-01-01",
                "status": "active",
                "tags": [],
            },
        ],
    }

    engine = MockMemoryEngine(snapshot)
    adapter = MemoryLayerAdapter(engine)
    context = adapter._extract_academic_profile(snapshot)

    assert "courses" in context, f"Expected courses in academic_profile, got {context}"
    assert any("数字通信" in c for c in context["courses"]), f"Expected 数字通信 in courses, got {context['courses']}"

    assert "strengths" in context, f"Expected strengths in academic_profile, got {context}"
    assert any("电路分析" in s for s in context["strengths"]), f"Expected 电路分析 in strengths, got {context['strengths']}"

    assert "current_tasks" in context, f"Expected current_tasks in academic_profile, got {context}"
    assert any("quiz" in t for t in context["current_tasks"]), f"Expected quiz in tasks, got {context['current_tasks']}"


def test_academic_prompt_section() -> None:
    """Academic profile should appear in prompt section."""
    snapshot = {
        "persona_slots": {},
        "preference_slots": {},
        "preference_profiles": {},
        "conflicts": [],
        "memories": [
            {
                "id": "1",
                "memory_type": "event",
                "summary": "学期课程",
                "content": "这学期课程：数字通信、微波工程。",
                "role": "user",
                "created_at": "2026-01-01",
                "updated_at": "2026-01-01",
                "status": "active",
                "tags": [],
            },
        ],
    }

    engine = MockMemoryEngine(snapshot)
    adapter = MemoryLayerAdapter(engine)

    import asyncio
    context = asyncio.run(adapter.retrieve_tiered(query="考试", situation="study"))

    prompt = context.to_prompt_section()
    assert "学业档案" in prompt, f"Expected 学业档案 in prompt, got {prompt[:200]}"
    assert "数字通信" in prompt, f"Expected 数字通信 in prompt, got {prompt[:200]}"


def test_no_academic_empty() -> None:
    """No academic info -> empty academic_profile."""
    snapshot = {
        "persona_slots": {},
        "preference_slots": {},
        "preference_profiles": {},
        "conflicts": [],
        "memories": [
            {
                "id": "1",
                "memory_type": "event",
                "summary": "旅游",
                "content": "我和朋友去海边玩了一整天。",
                "role": "user",
                "created_at": "2026-01-01",
                "updated_at": "2026-01-01",
                "status": "active",
                "tags": [],
            },
        ],
    }

    engine = MockMemoryEngine(snapshot)
    adapter = MemoryLayerAdapter(engine)
    context = adapter._extract_academic_profile(snapshot)

    assert context == {}, f"Expected empty academic_profile, got {context}"


if __name__ == "__main__":
    test_extract_academic_from_memories()
    test_academic_prompt_section()
    test_no_academic_empty()
    print("All academic memory slot tests passed!")
