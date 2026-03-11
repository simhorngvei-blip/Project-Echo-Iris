"""
Echo-Iris — Speech-to-Text (STT)

Local transcription powered by faster-whisper (CTranslate2 backend).
Accepts raw PCM 16-bit audio bytes and returns transcribed text.
Supports automatic multilingual detection.
"""

from __future__ import annotations

import io
import logging

import numpy as np
from faster_whisper import WhisperModel

from app.config import settings

logger = logging.getLogger(__name__)


class SpeechToText:
    """
    Whisper-based speech-to-text engine.

    Usage::

        stt = SpeechToText()
        text = stt.transcribe(pcm_bytes)
    """

    def __init__(
        self,
        model_size: str | None = None,
        device: str | None = None,
        compute_type: str | None = None,
    ):
        self._model_size = model_size or settings.stt_model_size
        self._device = device or settings.stt_device
        self._compute_type = compute_type or settings.stt_compute_type

        logger.info(
            "STT loading model=%s  device=%s  compute=%s",
            self._model_size,
            self._device,
            self._compute_type,
        )
        self._model = WhisperModel(
            self._model_size,
            device=self._device,
            compute_type=self._compute_type,
        )
        logger.info("STT model ready")

    def transcribe(
        self,
        audio_bytes: bytes,
        sample_rate: int = 16000,
        language: str | None = None,
    ) -> str:
        """
        Transcribe raw PCM 16-bit signed LE audio bytes to text.

        Parameters
        ----------
        audio_bytes : bytes
            Raw PCM audio (16-bit signed, little-endian, mono).
        sample_rate : int
            Sample rate of the input audio (default 16000).
        language : str | None
            ISO language code, or ``None`` for auto-detect.

        Returns
        -------
        str
            The transcribed text (empty string if nothing detected).
        """
        if not audio_bytes:
            return ""

        # Convert PCM int16 → float32 normalised to [-1.0, 1.0]
        audio_np = (
            np.frombuffer(audio_bytes, dtype=np.int16)
            .astype(np.float32)
            / 32768.0
        )

        segments, info = self._model.transcribe(
            audio_np,
            language=language,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
        )

        text = " ".join(seg.text for seg in segments).strip()
        logger.info(
            "STT transcribed (%s, %.1fs): %s",
            info.language,
            info.duration,
            text[:80],
        )
        return text
