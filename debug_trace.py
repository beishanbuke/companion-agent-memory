#!/usr/bin/env python3
"""Debug script to get full traceback"""

import sys
import traceback
sys.path.insert(0, '/Users/niuniu/Downloads/quickstart')

import asyncio
from companion_agent.memory_adapter import MemoryLayerAdapter
from companion_agent.v2.core_v2 import CompanionAgentCoreV2
from companion_agent.v2.persona_v2 import CharacterStyle

async def test():
    # 创建简单的 memory engine mock
    from memory.base import BaseMemory
    from memory.simple import SimpleMemory
    
    memory = SimpleMemory()
    adapter = MemoryLayerAdapter(memory)
    
    core = CompanionAgentCoreV2(
        memory_engine=adapter,
        character_style=CharacterStyle(name="姜姜"),
        session_id="test-debug-1",
        user_id="test-user",
    )
    try:
        result = await core.generate_reply(
            user_message="我明天要交论文初稿，现在只写了500字，根本写不完，我要崩溃了。",
            memory_enabled=True,
        )
        print("Success:", result.reply[:100])
    except Exception as e:
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
