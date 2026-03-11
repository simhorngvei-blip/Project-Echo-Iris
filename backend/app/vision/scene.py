"""
Echo-Iris — Ollama Vision Scene Describer (Deep Track)

Sends a frame to an Ollama vision-capable model (e.g., llava) and
returns a natural-language scene description. Fully async via httpx.
"""

from __future__ import annotations

import base64
import logging

import cv2
import httpx
import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)

_SCENE_PROMPT = (
    "Describe what you see in this image in one concise sentence. "
    "Focus on the person, what they are doing, and any notable objects."
)


class SceneDescriber:
    """
    Ollama vision-LLM scene description engine.

    Usage::

        describer = SceneDescriber()
        description = await describer.describe(frame)
    """

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
    ):
        self._model = model or settings.vision_ollama_model
        self._base_url = base_url or settings.ollama_base_url
        logger.info("Scene describer ready — model=%s", self._model)

    async def describe(self, frame: np.ndarray) -> str:
        """
        Send a frame to the Ollama vision model for scene description.

        Parameters
        ----------
        frame : np.ndarray
            BGR image array (H, W, 3).

        Returns
        -------
        str
            Natural language description of the scene.
        """
        # Encode frame as JPEG → base64
        success, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        if not success:
            logger.warning("Failed to encode frame as JPEG")
            return ""

        img_b64 = base64.b64encode(buf.tobytes()).decode("utf-8")

        # Call Ollama vision API
        payload = {
            "model": self._model,
            "prompt": _SCENE_PROMPT,
            "images": [img_b64],
            "stream": False,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self._base_url}/api/generate",
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                description = data.get("response", "").strip()
                logger.info("Scene description: %s", description[:80])
                return description
        except Exception:
            logger.exception("Scene description failed")
            return ""
