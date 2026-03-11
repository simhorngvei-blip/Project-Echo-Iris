"""
Echo-Iris — Sign Language Recognition

Real-time hand gesture recognition using MediaPipe landmarks,
a sliding-window gesture buffer, and DTW-based classification.

Classes
-------
- HandTracker     — MediaPipe 21-landmark extraction
- GestureBuffer   — Sliding window with stride-based classification trigger
- GestureClassifier — DTW template matching
- SignLanguageRecognizer — Top-level orchestrator
"""

from __future__ import annotations

import json
import logging
import os
from collections import deque
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hand Landmark Extraction
# ---------------------------------------------------------------------------


class HandTracker:
    """
    Extract 21 hand landmarks per frame using MediaPipe Hands.
    Landmarks are normalized relative to the wrist for translation/scale
    invariance.
    """

    def __init__(
        self,
        max_num_hands: int = 2,
        min_detection_confidence: float = 0.7,
        min_tracking_confidence: float = 0.5,
    ):
        import mediapipe as mp

        self._hands = mp.solutions.hands.Hands(
            static_image_mode=False,
            max_num_hands=max_num_hands,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )
        logger.info("HandTracker initialised (max_hands=%d)", max_num_hands)

    def extract(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """
        Extract normalised hand landmarks from a BGR frame.

        Returns
        -------
        np.ndarray of shape [21, 3] for the dominant (first) hand,
        or None if no hand is detected.
        """
        import cv2

        # MediaPipe expects RGB
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self._hands.process(rgb)

        if not results.multi_hand_landmarks:
            return None

        # Take the first (dominant) hand
        hand = results.multi_hand_landmarks[0]
        landmarks = np.array(
            [[lm.x, lm.y, lm.z] for lm in hand.landmark],
            dtype=np.float32,
        )  # shape [21, 3]

        # Normalise: translate so wrist (landmark 0) is at origin
        wrist = landmarks[0].copy()
        landmarks -= wrist

        # Scale by palm width (distance from wrist to middle finger MCP)
        palm_width = np.linalg.norm(landmarks[9])  # MCP of middle finger
        if palm_width > 1e-6:
            landmarks /= palm_width

        return landmarks

    def close(self):
        """Release MediaPipe resources."""
        self._hands.close()


# ---------------------------------------------------------------------------
# Gesture Buffer (Sliding Window)
# ---------------------------------------------------------------------------


class GestureBuffer:
    """
    Collects landmark frames in a sliding window and triggers
    classification every `stride` frames.
    """

    def __init__(self, window_size: int = 30, stride: int = 5):
        self._buffer: deque[np.ndarray] = deque(maxlen=window_size)
        self._window_size = window_size
        self._stride = stride
        self._counter = 0

    def push(self, landmarks: np.ndarray) -> Optional[np.ndarray]:
        """
        Push a frame of landmarks into the buffer.

        Returns the buffer as a numpy array of shape [window_size, 21, 3]
        every `stride` frames when the buffer is full, else None.
        """
        self._buffer.append(landmarks)
        self._counter += 1

        if self._counter >= self._stride and len(self._buffer) == self._window_size:
            self._counter = 0
            return np.array(list(self._buffer))  # [W, 21, 3]

        return None

    def clear(self):
        """Reset the buffer."""
        self._buffer.clear()
        self._counter = 0

    @property
    def is_full(self) -> bool:
        return len(self._buffer) == self._window_size


# ---------------------------------------------------------------------------
# DTW Gesture Classifier
# ---------------------------------------------------------------------------


def _dtw_distance(seq_a: np.ndarray, seq_b: np.ndarray) -> float:
    """
    Compute Dynamic Time Warping distance between two sequences.

    Parameters
    ----------
    seq_a, seq_b : np.ndarray of shape [T, D]
        Flattened landmark sequences.

    Returns
    -------
    float — DTW distance (lower = more similar).
    """
    n, m = len(seq_a), len(seq_b)
    # Cost matrix
    cost = np.full((n + 1, m + 1), np.inf)
    cost[0, 0] = 0.0

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            d = np.linalg.norm(seq_a[i - 1] - seq_b[j - 1])
            cost[i, j] = d + min(cost[i - 1, j], cost[i, j - 1], cost[i - 1, j - 1])

    return float(cost[n, m])


class GestureClassifier:
    """
    Classify gesture sequences by comparing against pre-recorded
    templates using Dynamic Time Warping (DTW).
    """

    def __init__(self, templates_dir: str, threshold: float = 2.0):
        self._templates: dict[str, np.ndarray] = {}
        self._threshold = threshold
        self._templates_dir = templates_dir
        self._load_templates()

    def _load_templates(self):
        """Load all JSON gesture templates from the templates directory."""
        templates_path = Path(self._templates_dir)
        if not templates_path.exists():
            logger.warning("Gesture templates dir not found: %s", self._templates_dir)
            return

        for json_file in templates_path.glob("*.json"):
            try:
                with open(json_file, "r") as f:
                    data = json.load(f)
                name = data.get("name", json_file.stem)
                landmarks = np.array(data["landmarks"], dtype=np.float32)
                self._templates[name] = landmarks
                logger.info("Loaded gesture template: %s (%d frames)", name, len(landmarks))
            except Exception:
                logger.exception("Failed to load template: %s", json_file)

    def classify(self, sequence: np.ndarray) -> Optional[str]:
        """
        Compare a gesture sequence against all templates.

        Parameters
        ----------
        sequence : np.ndarray of shape [T, 21, 3]

        Returns
        -------
        str — gesture name if best match < threshold, else None.
        """
        if not self._templates:
            return None

        # Flatten frames: [T, 21, 3] -> [T, 63]
        seq_flat = sequence.reshape(len(sequence), -1)

        best_name = None
        best_dist = float("inf")

        for name, template in self._templates.items():
            tmpl_flat = template.reshape(len(template), -1)
            dist = _dtw_distance(seq_flat, tmpl_flat)
            if dist < best_dist:
                best_dist = dist
                best_name = name

        if best_dist < self._threshold and best_name is not None:
            logger.info("Gesture recognised: %s (dist=%.2f)", best_name, best_dist)
            return best_name

        return None

    @property
    def template_count(self) -> int:
        return len(self._templates)

    @property
    def template_names(self) -> list[str]:
        return list(self._templates.keys())


# ---------------------------------------------------------------------------
# Top-Level Recogniser
# ---------------------------------------------------------------------------


class SignLanguageRecognizer:
    """
    Top-level sign language recognition: tracker + buffer + classifier.
    Thread-safe for use in the vision ThreadPoolExecutor.
    """

    def __init__(
        self,
        templates_dir: str,
        threshold: float = 2.0,
        buffer_size: int = 30,
        stride: int = 5,
    ):
        self._tracker = HandTracker()
        self._buffer = GestureBuffer(window_size=buffer_size, stride=stride)
        self._classifier = GestureClassifier(
            templates_dir=templates_dir,
            threshold=threshold,
        )
        logger.info(
            "SignLanguageRecognizer ready — %d templates loaded",
            self._classifier.template_count,
        )

    def process_frame(self, frame: np.ndarray) -> Optional[str]:
        """
        Process a single video frame.

        Returns the recognised gesture name (e.g. "hello") or None.
        """
        landmarks = self._tracker.extract(frame)
        if landmarks is None:
            return None

        sequence = self._buffer.push(landmarks)
        if sequence is None:
            return None

        return self._classifier.classify(sequence)

    def record_gesture(self, name: str, frames: list[np.ndarray], output_dir: str) -> str:
        """
        Record and save a new gesture template.

        Parameters
        ----------
        name : str — gesture name
        frames : list of BGR frames
        output_dir : str — directory to save the JSON template

        Returns
        -------
        str — path to the saved template file.
        """
        landmark_sequence = []
        for frame in frames:
            lm = self._tracker.extract(frame)
            if lm is not None:
                landmark_sequence.append(lm.tolist())

        if not landmark_sequence:
            raise ValueError("No hand landmarks detected in any frame")

        os.makedirs(output_dir, exist_ok=True)
        filepath = os.path.join(output_dir, f"{name}.json")
        template = {
            "name": name,
            "landmarks": landmark_sequence,
            "description": f"Recorded gesture: {name}",
        }
        with open(filepath, "w") as f:
            json.dump(template, f, indent=2)

        # Reload templates
        self._classifier._load_templates()
        logger.info("Recorded gesture template: %s (%d frames)", name, len(landmark_sequence))
        return filepath

    def close(self):
        """Release resources."""
        self._tracker.close()
