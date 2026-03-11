"""
Echo-Iris — YOLO Object Detector (Fast Track)

Runs YOLOv8 on incoming frames for rapid object identification.
Returns a flat list of Detection results with labels, confidence, and bounding boxes.
"""

from __future__ import annotations

import logging
from typing import List, NamedTuple

import numpy as np
from ultralytics import YOLO

from app.config import settings

logger = logging.getLogger(__name__)


class Detection(NamedTuple):
    """A single detected object."""
    label: str
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float


class ObjectDetector:
    """
    YOLO-based real-time object detector.

    Usage::

        detector = ObjectDetector()
        detections = detector.detect(frame)
    """

    def __init__(self, model_name: str | None = None):
        self._model_name = model_name or settings.vision_yolo_model
        logger.info("Loading YOLO model: %s", self._model_name)
        self._model = YOLO(self._model_name)
        logger.info("YOLO model ready")

    def detect(
        self,
        frame: np.ndarray,
        min_confidence: float | None = None,
    ) -> List[Detection]:
        """
        Run YOLO inference on a single frame.

        Parameters
        ----------
        frame : np.ndarray
            BGR image array (H, W, 3) as returned by cv2.imdecode.
        min_confidence : float | None
            Minimum confidence threshold. Defaults to config value.

        Returns
        -------
        list[Detection]
            Filtered detections sorted by confidence (highest first).
        """
        conf = min_confidence if min_confidence is not None else settings.vision_min_confidence

        results = self._model(frame, verbose=False)

        detections: List[Detection] = []
        for result in results:
            for box in result.boxes:
                score = float(box.conf[0])
                if score < conf:
                    continue
                cls_id = int(box.cls[0])
                label = result.names[cls_id]
                coords = box.xyxy[0]
                xyxy = coords.tolist() if hasattr(coords, "tolist") else list(coords)
                x1, y1, x2, y2 = xyxy
                detections.append(Detection(
                    label=label,
                    confidence=round(score, 3),
                    x1=round(x1, 1),
                    y1=round(y1, 1),
                    x2=round(x2, 1),
                    y2=round(y2, 1),
                ))

        # Sort by confidence descending
        detections.sort(key=lambda d: d.confidence, reverse=True)

        if detections:
            labels = ", ".join(f"{d.label}({d.confidence:.0%})" for d in detections[:5])
            logger.debug("YOLO detected: %s", labels)

        return detections
