"""
Echo-Iris — ElevenLabs TTS Provider

Streaming text-to-speech using the ElevenLabs Python SDK.
Consumes text chunks from the LLM stream and yields PCM audio chunks.
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

from elevenlabs import ElevenLabs

from app.audio.tts_base import TTSBase
from app.config import settings

logger = logging.getLogger(__name__)


class ElevenLabsTTS(TTSBase):
    """
    ElevenLabs streaming TTS provider.

    Uses the ElevenLabs SDK to convert text → PCM audio. Supports both
    full-text synthesis and streaming (text chunks → audio chunks).
    """

    def __init__(
        self,
        api_key: str | None = None,
        voice_id: str | None = None,
        model_id: str | None = None,
        fallback_tts: TTSBase | None = None,
    ):
        self._api_key = api_key or settings.elevenlabs_api_key
        self._voice_id = voice_id or settings.elevenlabs_voice_id
        self._model_id = model_id or settings.elevenlabs_model_id
        self._fallback_tts = fallback_tts

        self._client = ElevenLabs(api_key=self._api_key)

        logger.info(
            "ElevenLabs TTS initialised — voice=%s  model=%s",
            self._voice_id,
            self._model_id,
        )

    async def synthesize_stream(
        self,
        text_stream: AsyncIterator[str],
    ) -> AsyncIterator[bytes]:
        """
        Stream text chunks into ElevenLabs and yield PCM audio chunks.

        Collects text into sentence-level buffers before sending to
        ElevenLabs for better synthesis quality while maintaining low
        latency.
        """
        buffer = ""
        # Sentence-ending punctuation triggers a flush
        flush_chars = {".", "!", "?", "\n", ";", ":"}

        async for text_chunk in text_stream:
            buffer += text_chunk

            # Check if buffer contains a natural break point
            should_flush = any(c in buffer for c in flush_chars)

            if should_flush and len(buffer.strip()) > 0:
                async for audio_chunk in self._synthesize_text(buffer.strip()):
                    yield audio_chunk
                buffer = ""

        # Flush remaining text
        if buffer.strip():
            async for audio_chunk in self._synthesize_text(buffer.strip()):
                yield audio_chunk

    async def synthesize(self, text: str) -> bytes:
        """Synthesize complete text into a single PCM byte buffer."""
        chunks = []
        async for chunk in self._synthesize_text(text):
            chunks.append(chunk)
        return b"".join(chunks)

    async def _synthesize_text(self, text: str) -> AsyncIterator[bytes]:
        """
        Call ElevenLabs API for a text segment and yield audio chunks.

        Uses the synchronous SDK in a thread executor to avoid blocking
        the async event loop.
        """
        logger.debug("ElevenLabs synthesising: %s", text[:60])

        loop = asyncio.get_event_loop()

        # Run the synchronous ElevenLabs generate call in a thread
        try:
            audio_iterator = await loop.run_in_executor(
                None,
                lambda: self._client.text_to_speech.convert(
                    voice_id=self._voice_id,
                    text=text,
                    model_id=self._model_id,
                    output_format=f"pcm_{settings.tts_output_sample_rate}",
                ),
            )

            # The SDK returns an iterator of bytes chunks
            for chunk in audio_iterator:
                if chunk:
                    yield chunk
                    
        except Exception as e:
            logger.warning("ElevenLabs generation failed: %s", e)
            if self._fallback_tts is not None:
                logger.info("Falling back to alternative TTS provider")
                async for chunk in self._fallback_tts._synthesize_text(text):
                    yield chunk
            else:
                logger.error("No fallback TTS available!")
                raise e
