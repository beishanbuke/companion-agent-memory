"""Memory-injecting FrameProcessor for Pipecat pipelines.

Place this processor immediately before your LLM service in the pipeline:

    Pipeline([
        transport.input(),
        stt,
        user_aggregator,
        MemoryProcessor(memory),   # <-- here
        llm,
        tts,
        transport.output(),
        assistant_aggregator,
    ])

On every LLMContextFrame the processor:
  1. Reads accumulated memory and injects it as a system message.
  2. Stores any new user / assistant turns found in the context.

All other frames pass through unchanged.
"""

try:
    from loguru import logger
except ImportError:  # pragma: no cover - local fallback for lightweight tests
    import logging

    logger = logging.getLogger(__name__)

from pipecat.frames.frames import Frame, LLMContextFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from memory.base import BaseMemory


class MemoryProcessor(FrameProcessor):
    """Injects conversation memory into the LLM context before each inference.

    Args:
        memory: Any BaseMemory implementation. Swap freely without touching
            the rest of the pipeline.
        memory_role: Role used for the injected memory message.
            "system" keeps it out of the visible transcript; "user" works
            as a fallback for models that ignore system messages.
    """

    def __init__(self, memory: BaseMemory, memory_role: str = "system"):
        super().__init__()
        self._memory = memory
        self._memory_role = memory_role
        # Track how many user/assistant messages we've already persisted so
        # we only store genuinely new turns each call.
        self._stored_count: int = 0

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, LLMContextFrame) and direction == FrameDirection.DOWNSTREAM:
            await self._handle_context_frame(frame)
        else:
            await self.push_frame(frame, direction)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _handle_context_frame(self, frame: LLMContextFrame):
        context = frame.context
        messages = context.get_messages()
        latest_user_query = self._latest_user_query(messages)
        try:
            # Step 1 – persist completed turns only. The current trailing user
            # message is already present in the live context, so we keep it out
            # of long-term memory until the next LLM call.
            await self._store_new_turns(messages)

            # Step 2 – inject the most relevant long-term memory for the
            # current user query.
            memory_text = await self._memory.retrieve(query=latest_user_query)
            if memory_text:
                context.add_message({"role": self._memory_role, "content": memory_text})
                logger.debug("MemoryProcessor: injected memory into context")

        except Exception as e:
            logger.error(f"MemoryProcessor: error processing context frame: {e}")
            await self.push_error(error_msg=f"MemoryProcessor error: {e}", exception=e)

        await self.push_frame(frame, FrameDirection.DOWNSTREAM)

    async def _store_new_turns(self, messages: list[dict]) -> None:
        """Persist user/assistant turns that haven't been stored yet."""
        user_assistant = [
            m
            for m in messages
            if m.get("role") in ("user", "assistant")
            and isinstance(m.get("content"), str)
        ]
        if user_assistant and user_assistant[-1].get("role") == "user":
            user_assistant = user_assistant[:-1]
        new_turns = user_assistant[self._stored_count :]
        for turn in new_turns:
            await self._memory.store(turn["role"], turn["content"])
        if new_turns:
            self._stored_count += len(new_turns)

    def _latest_user_query(self, messages: list[dict]) -> str:
        for message in reversed(messages):
            if message.get("role") == "user" and isinstance(message.get("content"), str):
                return message["content"]
        return ""
