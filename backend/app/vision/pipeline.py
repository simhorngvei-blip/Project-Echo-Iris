"""
Echo-Iris — Triple-Track Vision Pipeline

Orchestrates the Fast Track (YOLO), Deep Track (Ollama vision),
and Sign Language Track (MediaPipe + DTW) with smart gating.
Runs heavy compute in a dedicated thread pool to avoid blocking
the chat/audio event loop.
"""

from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

from app.config import settings
from app.core.stm import ShortTermMemory
from app.vision.detector import Detection, ObjectDetector
from app.vision.scene import SceneDescriber
from app.vision.sign_language import SignLanguageRecognizer

logger = logging.getLogger(__name__)

# Dedicated thread pool for vision tasks — isolated from the main loop
_vision_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="vision")


class VisionPipeline:
    """
    Triple-track vision orchestrator.

    - **Fast Track**: YOLO on every frame. Injects ``[Visual Context]``
      into STM only when detected objects *change*.
    - **Deep Track**: Ollama vision LLM. Fires on a timer or when YOLO
      detects a new high-confidence object.
    - **Sign Language Track**: MediaPipe hand landmarks + DTW classifier.
      Injects recognised gestures as ``"user"`` messages in STM.

    Usage::

        pipeline = VisionPipeline(detector, describer, stm)
        result = await pipeline.process_frame(frame)
    """

    def __init__(
        self,
        detector: ObjectDetector,
        describer: SceneDescriber,
        stm: ShortTermMemory,
        sign_recognizer: Optional[SignLanguageRecognizer] = None,
    ):
        self.detector = detector
        self.describer = describer
        self.stm = stm
        self._sign_recognizer = sign_recognizer

        # Gate state
        self._last_objects: Set[Tuple[str, int]] = set()
        self._last_deep_time: float = 0.0
        self._deep_interval: float = settings.vision_deep_interval
        self._trigger_conf: float = settings.vision_yolo_trigger_conf

        # Sign language cooldown
        self._last_sign_time: float = 0.0
        self._sign_cooldown: float = settings.sign_language_cooldown

    async def process_frame(self, frame: np.ndarray) -> Dict[str, Any]:
        """
        Run both tracks on a single frame.

        Returns
        -------
        dict
            {
                "objects": [{"label": ..., "confidence": ...}, ...],
                "scene": str | None,
                "fast_injected": bool,
                "deep_injected": bool,
            }
        """
        loop = asyncio.get_event_loop()

        # --- Fast Track: YOLO in thread pool ---
        detections: List[Detection] = await loop.run_in_executor(
            _vision_executor,
            self.detector.detect,
            frame,
        )

        # Build object summary for response
        objects = [
            {"label": d.label, "confidence": d.confidence}
            for d in detections
        ]

        # --- Fast Track gating: did objects change? ---
        current_obj_set = self._detection_fingerprint(detections)
        fast_injected = False

        if current_obj_set != self._last_objects and detections:
            # Objects changed — inject into STM
            obj_str = ", ".join(
                f"{d.label} ({d.confidence:.0%})" for d in detections[:8]
            )
            self.stm.append(
                "system",
                f"[Visual Context] Objects detected: {obj_str}",
            )
            fast_injected = True
            logger.info("Fast track injected: %s", obj_str[:80])

        self._last_objects = current_obj_set

        # --- Deep Track gating ---
        now = time.monotonic()
        should_deep = False
        scene: Optional[str] = None
        deep_injected = False

        # Timer-based trigger
        if (now - self._last_deep_time) >= self._deep_interval:
            should_deep = True

        # YOLO trigger: new high-confidence object appeared
        if fast_injected and any(d.confidence >= self._trigger_conf for d in detections):
            should_deep = True

        if should_deep:
            self._last_deep_time = now
            scene = await self.describer.describe(frame)
            if scene:
                self.stm.append(
                    "system",
                    f"[Scene Description] {scene}",
                )
                deep_injected = True
                logger.info("Deep track injected: %s", scene[:80])

        # --- Sign Language Track ---
        sign_text: Optional[str] = None
        sign_injected = False

        if self._sign_recognizer is not None:
            sign_text = await loop.run_in_executor(
                _vision_executor,
                self._sign_recognizer.process_frame,
                frame,
            )
            if sign_text and (now - self._last_sign_time) > self._sign_cooldown:
                self._last_sign_time = now
                self.stm.append("user", f"[Sign Language] {sign_text}")
                sign_injected = True
                logger.info("Sign language injected: %s", sign_text)

        return {
            "objects": objects,
            "scene": scene,
            "sign": sign_text,
            "fast_injected": fast_injected,
            "deep_injected": deep_injected,
            "sign_injected": sign_injected,
        }

    @staticmethod
    def _detection_fingerprint(detections: List[Detection]) -> Set[Tuple[str, int]]:
        """
        Build a hashable fingerprint of detected objects.

        Uses (label, confidence_bucket) where bucket = int(conf * 10)
        to tolerate minor confidence jitter between frames.
        """
        return {(d.label, int(d.confidence * 10)) for d in detections}
