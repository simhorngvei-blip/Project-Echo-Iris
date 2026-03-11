"""
Tests for the Sign Language Translation module.

Tests cover:
  - GestureBuffer stride logic
  - GestureClassifier template matching
  - DTW distance computation
  - Cooldown gating (via pipeline integration)
  - STM injection as "user" role
"""

from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from app.core.stm import ShortTermMemory
from app.vision.sign_language import (
    GestureBuffer,
    GestureClassifier,
    SignLanguageRecognizer,
    _dtw_distance,
)


class TestGestureBuffer:
    """Tests for the sliding window gesture buffer."""

    def test_push_returns_none_until_full(self):
        buf = GestureBuffer(window_size=5, stride=3)
        lm = np.random.randn(21, 3).astype(np.float32)
        for _ in range(4):
            assert buf.push(lm) is None

    def test_push_returns_array_at_stride(self):
        buf = GestureBuffer(window_size=5, stride=5)
        lm = np.random.randn(21, 3).astype(np.float32)
        for _ in range(4):
            buf.push(lm)
        result = buf.push(lm)
        assert result is not None
        assert result.shape == (5, 21, 3)

    def test_stride_resets_counter(self):
        buf = GestureBuffer(window_size=3, stride=3)
        lm = np.random.randn(21, 3).astype(np.float32)
        # Fill buffer and trigger first classification
        for _ in range(2):
            buf.push(lm)
        result = buf.push(lm)
        assert result is not None
        # Next push should return None (counter reset)
        assert buf.push(lm) is None

    def test_clear_resets(self):
        buf = GestureBuffer(window_size=5, stride=3)
        lm = np.random.randn(21, 3).astype(np.float32)
        for _ in range(3):
            buf.push(lm)
        buf.clear()
        assert not buf.is_full


class TestDTWDistance:
    """Tests for the DTW distance function."""

    def test_identical_sequences_zero_distance(self):
        seq = np.random.randn(10, 63).astype(np.float32)
        dist = _dtw_distance(seq, seq)
        assert dist == pytest.approx(0.0, abs=1e-5)

    def test_different_sequences_positive_distance(self):
        seq_a = np.zeros((10, 63), dtype=np.float32)
        seq_b = np.ones((10, 63), dtype=np.float32)
        dist = _dtw_distance(seq_a, seq_b)
        assert dist > 0

    def test_symmetry(self):
        seq_a = np.random.randn(10, 63).astype(np.float32)
        seq_b = np.random.randn(10, 63).astype(np.float32)
        assert _dtw_distance(seq_a, seq_b) == pytest.approx(
            _dtw_distance(seq_b, seq_a), abs=1e-5
        )


class TestGestureClassifier:
    """Tests for the DTW-based gesture classifier."""

    def _make_template_dir(self, tmpdir, name, sequence):
        """Helper to create a gesture template JSON."""
        template = {
            "name": name,
            "landmarks": sequence.tolist(),
            "description": f"Test gesture: {name}",
        }
        filepath = os.path.join(tmpdir, f"{name}.json")
        with open(filepath, "w") as f:
            json.dump(template, f)
        return filepath

    def test_matches_known_template(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            seq = np.random.randn(10, 21, 3).astype(np.float32)
            self._make_template_dir(tmpdir, "wave", seq)

            classifier = GestureClassifier(tmpdir, threshold=1.0)
            # Identical sequence should match
            result = classifier.classify(seq)
            assert result == "wave"

    def test_rejects_unknown_gesture(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            template_seq = np.zeros((10, 21, 3), dtype=np.float32)
            self._make_template_dir(tmpdir, "wave", template_seq)

            classifier = GestureClassifier(tmpdir, threshold=0.5)
            # Very different sequence should not match
            random_seq = np.random.randn(10, 21, 3).astype(np.float32) * 100
            result = classifier.classify(random_seq)
            assert result is None

    def test_empty_templates_returns_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            classifier = GestureClassifier(tmpdir, threshold=2.0)
            seq = np.random.randn(10, 21, 3).astype(np.float32)
            assert classifier.classify(seq) is None

    def test_template_count(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            seq = np.random.randn(10, 21, 3).astype(np.float32)
            self._make_template_dir(tmpdir, "a", seq)
            self._make_template_dir(tmpdir, "b", seq)
            classifier = GestureClassifier(tmpdir, threshold=2.0)
            assert classifier.template_count == 2


class TestSTMInjection:
    """Tests for sign language → STM integration."""

    @pytest.mark.asyncio
    async def test_sign_injects_as_user(self):
        """Recognised gesture should inject as 'user' role in STM."""
        stm = ShortTermMemory(max_messages=50)

        mock_detector = MagicMock()
        mock_detector.detect.return_value = []

        mock_describer = MagicMock()
        mock_describer.describe = AsyncMock(return_value=None)

        mock_recognizer = MagicMock()
        mock_recognizer.process_frame.return_value = "hello"

        from app.vision.pipeline import VisionPipeline
        pipeline = VisionPipeline(
            detector=mock_detector,
            describer=mock_describer,
            stm=stm,
            sign_recognizer=mock_recognizer,
        )
        # Override the cooldown and deep interval directly
        pipeline._sign_cooldown = 0.0
        pipeline._deep_interval = 999.0
        pipeline._last_deep_time = 1e15  # prevent deep track from firing

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = await pipeline.process_frame(frame)

        assert result["sign"] == "hello"
        assert result["sign_injected"] is True

        # Check STM has the user message
        raw = stm.get_raw()
        sign_msgs = [e for e in raw if "[Sign Language]" in e["content"]]
        assert len(sign_msgs) >= 1
        assert sign_msgs[0]["role"] == "user"
        assert "hello" in sign_msgs[0]["content"]

    @pytest.mark.asyncio
    async def test_cooldown_prevents_flooding(self):
        """Second recognition within cooldown should be suppressed."""
        stm = ShortTermMemory(max_messages=50)

        mock_detector = MagicMock()
        mock_detector.detect.return_value = []

        mock_describer = MagicMock()
        mock_describer.describe = MagicMock(return_value=None)

        mock_recognizer = MagicMock()
        mock_recognizer.process_frame.return_value = "hello"

        from app.vision.pipeline import VisionPipeline
        pipeline = VisionPipeline(
            detector=mock_detector,
            describer=mock_describer,
            stm=stm,
            sign_recognizer=mock_recognizer,
        )
        pipeline._sign_cooldown = 999.0  # very long cooldown
        pipeline._deep_interval = 999.0
        pipeline._last_deep_time = 1e15

        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # First call should inject
        r1 = await pipeline.process_frame(frame)
        assert r1["sign_injected"] is True

        # Second call within cooldown should NOT inject
        r2 = await pipeline.process_frame(frame)
        assert r2["sign_injected"] is False
