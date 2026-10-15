"""Abstract base class for memory backends.

Defines the pluggable interface. Swap implementations without touching
the pipeline or bot logic.
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseMemory(ABC):
    """Interface for conversation memory backends."""

    @abstractmethod
    async def store(self, role: str, content: str) -> None:
        """Persist a single conversation turn.

        Args:
            role: Speaker role, either "user" or "assistant".
            content: The spoken/generated text content.
        """
        ...

    @abstractmethod
    async def retrieve(
        self,
        query: str = "",
        filters: dict[str, Any] | None = None,
        limit: int = 6,
    ) -> str:
        """Return stored memory as a formatted string for LLM injection.

        Args:
            query: Current user query used to recall the most relevant memory.
            filters: Optional metadata filters such as memory type or slot key.
            limit: Maximum number of relevant items to include.

        Returns:
            A formatted string summarising past turns, or empty string if
            no memory exists yet.
        """
        ...

    @abstractmethod
    async def clear(self) -> None:
        """Erase all stored memory."""
        ...
