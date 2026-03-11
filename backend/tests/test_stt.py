"""
Tests for the Speech-to-Text (STT) module.

Uses a mocked WhisperModel so tests run without downloading models.
"""

from __future__ import annotations

from collections import namedtuple
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.audio.stt import SpeechToText


# Mock segment object returned by faster-whisper
MockSegment = namedtuple("MockSegment", ["text", "start", "end"])
MockInfo = namedtuple("MockInfo", ["language", "language_probability", "duration"])


@pytest.fixture()
def stt():
    """Create an STT instance with a mocked WhisperModel."""
    with patch("app.audio.stt.WhisperModel") as MockModel:
        mock_instance = MagicMock()
        mock_segments = [
            MockSegment(text="Hello world", start=0.0, end=1.5),
            MockSegment(text="how are you", start=1.5, end=3.0),
        ]
        mock_info = MockInfo(language="en", language_probability=0.95, duration=3.0)
        mock_instance.transcribe.return_value = (iter(mock_segments), mock_info)
        MockModel.return_value = mock_instance

        yield SpeechToText(model_size="tiny", device="cpu", compute_type="int8")


class TestSpeechToText:
    """Unit tests for the STT module."""

    def test_transcribe_returns_text(self, stt: SpeechToText):
        # Generate 1 second of silent PCM audio (16kHz, 16-bit)
        audio = np.zeros(16000, dtype=np.int16).tobytes()
        result = stt.transcribe(audio)
        assert isinstance(result, str)
        assert "Hello world" in result
        assert "how are you" in result

    def test_transcribe_empty_bytes_returns_empty(self, stt: SpeechToText):
        result = stt.transcribe(b"")
        assert result == ""

    def test_transcribe_calls_model_with_float32(self, stt: SpeechToText):
        audio = np.ones(16000, dtype=np.int16).tobytes()
        stt.transcribe(audio)
        # Verify the model was called
        stt._model.transcribe.assert_called_once()
        # First arg should be a float32 numpy array
        call_args = stt._model.transcribe.call_args
        audio_arg = call_args[0][0]
        assert audio_arg.dtype == np.float32

    def test_transcribe_normalises_to_minus_one_one(self, stt: SpeechToText):
        # Max int16 = 32767 → should become ~1.0 after normalisation
        audio = np.array([32767, -32768], dtype=np.int16).tobytes()
        stt.transcribe(audio)
        call_args = stt._model.transcribe.call_args
        audio_arg = call_args[0][0]
        assert abs(audio_arg[0] - 1.0) < 0.001
        assert abs(audio_arg[1] - (-1.0)) < 0.001
