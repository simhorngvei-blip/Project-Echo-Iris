"""
Echo-Iris — Short-Term Memory (STM)

Manages the active conversational context window as a bounded deque of
chat messages.  Provides helpers to convert the window into LangChain
message objects for prompt assembly.
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timezone

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.config import settings

logger = logging.getLogger(__name__)


class MemoryEntry:
    """A single message stored in the STM window."""

    __slots__ = ("role", "content", "timestamp")

    def __init__(self, role: str, content: str, timestamp: datetime | None = None):
        if role not in ("user", "assistant", "system"):
            raise ValueError(f"Invalid role: {role!r}")
        self.role = role
        self.content = content
        self.timestamp = timestamp or datetime.now(timezone.utc)

    def to_langchain(self) -> BaseMessage:
        """Convert to a LangChain BaseMessage subclass."""
        if self.role == "user":
            return HumanMessage(content=self.content)
        if self.role == "assistant":
            return AIMessage(content=self.content)
        return SystemMessage(content=self.content)

    def __repr__(self) -> str:
        preview = self.content[:40] + "…" if len(self.content) > 40 else self.content
        return f"MemoryEntry(role={self.role!r}, content={preview!r})"


class ShortTermMemory:
    """
    Sliding-window context manager.

    Stores the last ``max_messages`` entries and exposes them as LangChain
    message objects for direct injection into a prompt chain.
    """

    def __init__(self, max_messages: int | None = None):
        self._max = max_messages or settings.stm_max_messages
        self._window: deque[MemoryEntry] = deque(maxlen=self._max)
        logger.info("STM initialised — window size %d", self._max)

    # -- public API -----------------------------------------------------------

    def append(self, role: str, content: str) -> None:
        """Add a message to the window (oldest entries are auto-evicted)."""
        entry = MemoryEntry(role=role, content=content)
        self._window.append(entry)
        logger.debug("STM append  [%s] %s", role, content[:60])

    def get_context(self) -> list[BaseMessage]:
        """Return the current window as a list of LangChain messages."""
        return [entry.to_langchain() for entry in self._window]

    def get_raw(self) -> list[dict]:
        """Return the window as plain dicts (useful for debugging / tests)."""
        return [
            {"role": e.role, "content": e.content, "ts": e.timestamp.isoformat()}
            for e in self._window
        ]

    def clear(self) -> None:
        """Flush all entries from the window."""
        self._window.clear()
        logger.info("STM cleared")

    @property
    def count(self) -> int:
        return len(self._window)

    @property
    def max_messages(self) -> int:
        return self._max
