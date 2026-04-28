"""Simple JSON-file-backed memory implementation.

Stores the last N conversation turns in a local JSON file so memory
survives bot restarts. No external services required.

To upgrade later: swap this class for a vector-DB or Mem0 backed
implementation that shares the same BaseMemory interface.
"""

import json
from collections import deque
from pathlib import Path
from typing import Any, Optional

try:
    from loguru import logger
except ImportError:  # pragma: no cover - local fallback for lightweight tests
    import logging

    logger = logging.getLogger(__name__)

from .base import BaseMemory


class SimpleMemory(BaseMemory):
    """Persists recent conversation turns to a local JSON file.

    Args:
        max_turns: Maximum number of user+assistant turn *pairs* to keep.
            Older turns are dropped automatically (FIFO).
        file_path: Path to the JSON storage file. Defaults to
            ``memory_store.json`` in the current working directory.
    """

    def __init__(
        self,
        max_turns: int = 10,
        file_path: Optional[str] = None,
    ):
        self._max_entries = max_turns * 2  # each pair = user + assistant
        self._file = Path(file_path or "memory_store.json")
        self._turns: deque[dict] = deque(maxlen=self._max_entries)
        self._load()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def store(self, role: str, content: str) -> None:
        content = content.strip()
        if not content:
            return
        entry = {"role": role, "content": content}
        # Avoid appending the exact same entry twice in a row
        if self._turns and self._turns[-1] == entry:
            return
        self._turns.append(entry)
        self._save()
        logger.debug(f"SimpleMemory: stored [{role}] ({len(content)} chars)")

    async def retrieve(
        self,
        query: str = "",
        filters: dict[str, Any] | None = None,
        limit: int = 6,
    ) -> str:
        if not self._turns:
            return ""
        lines = ["[Conversation history from previous turns]"]
        for turn in self._turns:
            label = "User" if turn["role"] == "user" else "Assistant"
            lines.append(f"{label}: {turn['content']}")
        return "\n".join(lines)

    async def clear(self) -> None:
        self._turns.clear()
        if self._file.exists():
            self._file.unlink()
        logger.info("SimpleMemory: cleared all stored turns")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not self._file.exists():
            return
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
            turns = data.get("turns", [])
            # Respect max_entries even for data written by an older config
            self._turns = deque(turns[-self._max_entries :], maxlen=self._max_entries)
            logger.info(f"SimpleMemory: loaded {len(self._turns)} turns from {self._file}")
        except Exception as e:
            logger.warning(f"SimpleMemory: could not load {self._file}: {e}")

    def _save(self) -> None:
        try:
            self._file.write_text(
                json.dumps({"turns": list(self._turns)}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"SimpleMemory: could not save {self._file}: {e}")
