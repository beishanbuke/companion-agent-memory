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
  2. Stores any new user / assistant turns found in the context. The current
     user message is stored after retrieval, so it is saved in this turn
     without being retrieved as long-term memory for its own response.

All other frames pass through unchanged.
"""

import inspect
from collections.abc import Awaitable, Callable

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

    def __init__(
        self,
        memory: BaseMemory,
        memory_role: str = "system",
        memory_enabled_getter: Callable[[], bool | Awaitable[bool]] | None = None,
    ):
        super().__init__()
        self._memory = memory
        self._memory_role = memory_role
        self._memory_enabled_getter = memory_enabled_getter
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
        messages = self._prune_injected_memory_messages(context)
        latest_user_query = self._latest_user_query(messages)
        try:
            memory_enabled = await self._is_memory_enabled()
            if not memory_enabled:
                self._mark_turns_seen(messages)
                logger.debug("MemoryProcessor: memory disabled, skipped retrieve/store")
                await self.push_frame(frame, FrameDirection.DOWNSTREAM)
                return

            # Step 1 – persist completed turns in the background. The store is
            # fire-and-forget (mirrors voice_bot's _refresh_emotion pattern):
            # memory HTTP writes must not delay the spoken response. The
            # background task stores completed turns first, then the current
            # trailing user turn, preserving the retrieval boundary below.
            self.create_task(self._persist_turns_background(messages))

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

    async def _persist_turns_background(self, messages: list[dict]) -> None:
        """Persist completed + current turns without blocking the pipeline.

        Failures are logged, never raised, so a memory hiccup never breaks
        the voice conversation.
        """
        try:
            await self._store_new_turns(messages)
            await self._store_current_user_turn(messages)
        except Exception as e:
            logger.error(f"MemoryProcessor: background memory store failed: {e}")

    async def _store_new_turns(self, messages: list[dict]) -> None:
        """Persist user/assistant turns that haven't been stored yet."""
        user_assistant = self._user_assistant_messages(messages)
        if user_assistant and user_assistant[-1].get("role") == "user":
            user_assistant = user_assistant[:-1]
        new_turns = user_assistant[self._stored_count :]
        for turn in new_turns:
            await self._memory.store(turn["role"], turn["content"])
        if new_turns:
            self._stored_count += len(new_turns)

    async def _store_current_user_turn(self, messages: list[dict]) -> None:
        """Persist the current trailing user message after memory retrieval."""
        user_assistant = self._user_assistant_messages(messages)
        if not user_assistant or user_assistant[-1].get("role") != "user":
            return
        if self._stored_count >= len(user_assistant):
            return

        current_user = user_assistant[-1]
        await self._memory.store(current_user["role"], current_user["content"])
        self._stored_count = len(user_assistant)

    def _user_assistant_messages(self, messages: list[dict]) -> list[dict]:
        return [
            m
            for m in messages
            if isinstance(m, dict)
            if m.get("role") in ("user", "assistant")
            and isinstance(m.get("content"), str)
            and m.get("content", "").strip()
        ]

    def _mark_turns_seen(self, messages: list[dict]) -> None:
        self._stored_count = len(self._user_assistant_messages(messages))

    def _prune_injected_memory_messages(self, context) -> list[dict]:
        messages = context.get_messages()
        pruned = [message for message in messages if not self._is_injected_memory_message(message)]
        if len(pruned) != len(messages):
            context.set_messages(pruned)
        return pruned

    def _is_injected_memory_message(self, message: dict) -> bool:
        return (
            isinstance(message, dict)
            and message.get("role") == self._memory_role
            and isinstance(message.get("content"), str)
            and message["content"].lstrip().startswith("[Long-term memory]")
        )

    async def _is_memory_enabled(self) -> bool:
        if self._memory_enabled_getter is None:
            return True
        try:
            result = self._memory_enabled_getter()
            if inspect.isawaitable(result):
                result = await result
            return bool(result)
        except Exception as exc:
            logger.warning(f"MemoryProcessor: failed to read memory mode, disabling memory: {exc}")
            return False

    def _latest_user_query(self, messages: list[dict]) -> str:
        for message in reversed(messages):
            if message.get("role") == "user" and isinstance(message.get("content"), str):
                return message["content"]
        return ""
