"""
Echo-Iris — TTS Abstract Base Class

Defines the interface every TTS provider must implement so that
providers can be swapped without changing any upstream code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator


class TTSBase(ABC):
    """
    Abstract text-to-speech provider.

    Subclasses must implement :meth:`synthesize_stream`, which consumes
    an async stream of text chunks (as they arrive from the LLM) and
    yields PCM audio byte chunks suitable for sending to the client.
    """

    @abstractmethod
    async def synthesize_stream(
        self,
        text_stream: AsyncIterator[str],
    ) -> AsyncIterator[bytes]:
        """
        Convert a stream of text chunks into a stream of audio bytes.

        Parameters
        ----------
        text_stream : AsyncIterator[str]
            An async iterator that yields text fragments as the LLM
            generates them.

        Yields
        ------
        bytes
            Raw PCM audio chunks (16-bit signed LE, provider-specific
            sample rate).
        """
        ...  # pragma: no cover
        # Make this a proper async generator for type-checking
        yield b""  # type: ignore[misc]  # noqa: E501

    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """
        Synthesize a complete text string into audio bytes (non-streaming).

        Useful for short utterances or testing.
        """
        ...  # pragma: no cover
