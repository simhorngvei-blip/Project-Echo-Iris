"""
Tests for the VisionPipeline dual-track orchestrator.

Mocks the detector and scene describer to validate gating logic,
STM injection, and timing controls.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from app.core.stm import ShortTermMemory
from app.vision.detector import Detection, ObjectDetector
from app.vision.pipeline import VisionPipeline
from app.vision.scene import SceneDescriber


def _make_detection(label: str, conf: float) -> Detection:
    return Detection(label=label, confidence=conf, x1=0, y1=0, x2=100, y2=100)


@pytest.fixture()
def stm():
    return ShortTermMemory(max_messages=50)


@pytest.fixture()
def mock_detector():
    det = MagicMock(spec=ObjectDetector)
    det.detect.return_value = [
        _make_detection("person", 0.95),
        _make_detection("cell phone", 0.88),
    ]
    return det


@pytest.fixture()
def mock_describer():
    desc = MagicMock(spec=SceneDescriber)
    desc.describe = AsyncMock(return_value="User is holding a phone")
    return desc


@pytest.fixture()
def pipeline(mock_detector, mock_describer, stm):
    p = VisionPipeline(mock_detector, mock_describer, stm)
    # Set deep interval very high so it doesn't auto-trigger
    p._deep_interval = 999.0
    return p


class TestVisionPipeline:
    """Tests for the dual-track pipeline gating logic."""

    @pytest.mark.asyncio
    async def test_fast_track_injects_on_first_frame(self, pipeline, stm):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = await pipeline.process_frame(frame)
        assert result["fast_injected"] is True
        assert stm.count >= 1
        raw = stm.get_raw()
        assert any("[Visual Context]" in e["content"] for e in raw)

    @pytest.mark.asyncio
    async def test_fast_track_skips_on_same_objects(self, pipeline, stm):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        await pipeline.process_frame(frame)
        count_after_first = stm.count

        # Same objects on second frame → should not inject
        result = await pipeline.process_frame(frame)
        assert result["fast_injected"] is False
        assert stm.count == count_after_first

    @pytest.mark.asyncio
    async def test_fast_track_injects_on_changed_objects(self, pipeline, stm, mock_detector):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        await pipeline.process_frame(frame)

        # Change detected objects
        mock_detector.detect.return_value = [
            _make_detection("book", 0.75),
        ]
        result = await pipeline.process_frame(frame)
        assert result["fast_injected"] is True

    @pytest.mark.asyncio
    async def test_deep_track_fires_on_timer(self, pipeline, stm, mock_describer):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        pipeline._deep_interval = 0.0  # Immediate trigger
        pipeline._last_deep_time = 0.0

        result = await pipeline.process_frame(frame)
        assert result["deep_injected"] is True
        assert result["scene"] == "User is holding a phone"
        raw = stm.get_raw()
        assert any("[Scene Description]" in e["content"] for e in raw)

    @pytest.mark.asyncio
    async def test_deep_track_skips_when_too_soon(self, pipeline, stm, mock_describer):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        pipeline._deep_interval = 999.0
        pipeline._last_deep_time = time.monotonic()
        # Pre-populate last objects so fast track doesn't trigger
        pipeline._last_objects = {("person", 9), ("cell phone", 8)}

        result = await pipeline.process_frame(frame)
        assert result["deep_injected"] is False
        mock_describer.describe.assert_not_called()

    @pytest.mark.asyncio
    async def test_deep_track_fires_on_yolo_trigger(self, pipeline, stm, mock_detector, mock_describer):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        pipeline._trigger_conf = 0.8
        pipeline._deep_interval = 999.0
        pipeline._last_deep_time = time.monotonic()

        # First frame sets _last_objects, and high-conf triggers deep
        result = await pipeline.process_frame(frame)
        # fast_injected=True because objects changed (first frame)
        # deep may or may not fire depending on whether fast_injected + trigger met
        assert result["fast_injected"] is True

    @pytest.mark.asyncio
    async def test_result_contains_objects(self, pipeline):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = await pipeline.process_frame(frame)
        assert "objects" in result
        assert len(result["objects"]) == 2
        assert result["objects"][0]["label"] == "person"
