"""
Tests for the YOLO Object Detector module.

Uses a mocked YOLO model so tests run without downloading weights.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.vision.detector import Detection, ObjectDetector


class MockBox:
    """Simulates a YOLO box result."""
    def __init__(self, cls_id: int, conf: float, xyxy: list):
        self.cls = [cls_id]
        self.conf = [conf]
        self.xyxy = [xyxy]


class MockResult:
    """Simulates a YOLO result object."""
    def __init__(self, boxes: list, names: dict):
        self.boxes = boxes
        self.names = names


@pytest.fixture()
def detector():
    """Create a detector with a mocked YOLO model."""
    with patch("app.vision.detector.YOLO") as MockYOLO:
        mock_model = MagicMock()

        mock_boxes = [
            MockBox(cls_id=0, conf=0.92, xyxy=[10.0, 20.0, 100.0, 200.0]),
            MockBox(cls_id=1, conf=0.45, xyxy=[50.0, 60.0, 150.0, 250.0]),
            MockBox(cls_id=2, conf=0.87, xyxy=[30.0, 40.0, 120.0, 220.0]),
        ]
        mock_result = MockResult(
            boxes=mock_boxes,
            names={0: "person", 1: "cat", 2: "cell phone"},
        )
        mock_model.return_value = [mock_result]
        MockYOLO.return_value = mock_model

        yield ObjectDetector(model_name="yolov8n.pt")


class TestObjectDetector:
    """Unit tests for the YOLO detector."""

    def test_detect_returns_list(self, detector: ObjectDetector):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        results = detector.detect(frame)
        assert isinstance(results, list)

    def test_detect_filters_low_confidence(self, detector: ObjectDetector):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        # Default min confidence is 0.5, so cat (0.45) should be filtered
        results = detector.detect(frame, min_confidence=0.5)
        labels = [d.label for d in results]
        assert "person" in labels
        assert "cell phone" in labels
        assert "cat" not in labels

    def test_detect_sorted_by_confidence(self, detector: ObjectDetector):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        results = detector.detect(frame, min_confidence=0.0)
        confs = [d.confidence for d in results]
        assert confs == sorted(confs, reverse=True)

    def test_detection_is_namedtuple(self, detector: ObjectDetector):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        results = detector.detect(frame)
        assert len(results) > 0
        d = results[0]
        assert hasattr(d, "label")
        assert hasattr(d, "confidence")
        assert hasattr(d, "x1")
        assert hasattr(d, "y1")
        assert hasattr(d, "x2")
        assert hasattr(d, "y2")

    def test_detect_empty_on_high_threshold(self, detector: ObjectDetector):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        results = detector.detect(frame, min_confidence=0.99)
        assert results == []
