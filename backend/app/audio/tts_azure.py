"""
Echo-Iris — Azure (Edge) TTS Provider

Provides a fallback text-to-speech mechanism using the free edge-tts library.
"""

from __future__ import annotations

import asyncio
import io
import logging
from typing import AsyncIterator

import edge_tts
from pydub import AudioSegment

from app.audio.tts_base import TTSBase
from app.config import settings

logger = logging.getLogger(__name__)


class AzureTTS(TTSBase):
    """
    Azure TTS provider using edge-tts.
    Acts as a fallback when ElevenLabs fails or is unconfigured.
    Converts generated MP3 audio into PCM 16-bit 44100Hz chunks.
    """

    def __init__(self, voice: str | None = None):
        self._voice = voice or settings.azure_tts_voice
        logger.info("Azure TTS initialised — voice=%s", self._voice)

    async def synthesize_stream(
        self,
        text_stream: AsyncIterator[str],
    ) -> AsyncIterator[bytes]:
        buffer = ""
        flush_chars = {".", "!", "?", "\n", ";", ":"}

        async for text_chunk in text_stream:
            buffer += text_chunk
            should_flush = any(c in buffer for c in flush_chars)

            if should_flush and len(buffer.strip()) > 0:
                async for audio_chunk in self._synthesize_text(buffer.strip()):
                    yield audio_chunk
                buffer = ""

        if buffer.strip():
            async for audio_chunk in self._synthesize_text(buffer.strip()):
                yield audio_chunk

    async def synthesize(self, text: str) -> bytes:
        chunks = []
        async for chunk in self._synthesize_text(text):
            chunks.append(chunk)
        return b"".join(chunks)

    async def _synthesize_text(self, text: str) -> AsyncIterator[bytes]:
        logger.debug("Azure TTS synthesising: %s", text[:60])

        communicate = edge_tts.Communicate(text, self._voice)
        audio_data = b""

        try:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]
        except Exception as e:
            logger.error("Azure TTS failed to stream audio: %s", e)
            return

        if not audio_data:
            return

        try:
            loop = asyncio.get_event_loop()
            pcm_data = await loop.run_in_executor(
                None,
                self._convert_to_pcm,
                audio_data
            )
            
            chunk_size = settings.tts_chunk_size
            for i in range(0, len(pcm_data), chunk_size):
                yield pcm_data[i : i + chunk_size]
                
        except Exception as e:
            logger.error("Azure TTS failed to process audio: %s", e)

    def _convert_to_pcm(self, mp3_bytes: bytes) -> bytes:
        audio = AudioSegment.from_file(io.BytesIO(mp3_bytes), format="mp3")
        audio = audio.set_channels(1)
        audio = audio.set_sample_width(2)
        audio = audio.set_frame_rate(settings.tts_output_sample_rate)
        return audio.raw_data
