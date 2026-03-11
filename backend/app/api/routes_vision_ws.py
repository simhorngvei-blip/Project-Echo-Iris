"""
Echo-Iris — Vision WebSocket

Endpoint: ``/ws/vision``

Receives base64-encoded JPEG frames from Unity, runs the dual-track
vision pipeline, and returns detected objects + scene descriptions.

Protocol
--------
**Inbound (Unity → Server):**
  ``{"type": "frame", "data": "<base64-JPEG>"}``

**Outbound (Server → Unity):**
  ``{"type": "vision_update", "objects": [...], "scene": "...", "injected": true}``
"""

from __future__ import annotations

import base64
import json
import logging

import cv2
import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

logger = logging.getLogger(__name__)

router = APIRouter()


def _decode_frame(b64_data: str) -> np.ndarray | None:
    """Decode a base64-encoded JPEG string into a BGR numpy array."""
    try:
        # WebGL JS FileReader may append a data URI scheme header; strip it if present.
        if b64_data.startswith("data:"):
            b64_data = b64_data.split(",")[1]

        img_bytes = base64.b64decode(b64_data)
        buf = np.frombuffer(img_bytes, dtype=np.uint8)
        frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        return frame
    except Exception:
        logger.warning("Failed to decode frame")
        return None


@router.websocket("/ws/vision")
async def websocket_vision(ws: WebSocket):
    """
    Vision pipeline WebSocket: receive frames, run YOLO + Ollama vision,
    inject context into STM, return results to Unity.
    """
    await ws.accept()
    logger.info("Vision WebSocket client connected")

    from app.main import get_vision_pipeline

    pipeline = get_vision_pipeline()

    try:
        while True:
            raw = await ws.receive_text()

            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "error": "Invalid JSON"})
                continue

            if payload.get("type") != "frame":
                await ws.send_json({
                    "type": "error",
                    "error": f"Unknown type: {payload.get('type')}",
                })
                continue

            b64_data = payload.get("data", "")
            if not b64_data:
                await ws.send_json({"type": "error", "error": "No frame data"})
                continue

            # Decode the frame
            frame = _decode_frame(b64_data)
            if frame is None:
                await ws.send_json({"type": "error", "error": "Failed to decode frame"})
                continue

            # Run the dual-track pipeline
            result = await pipeline.process_frame(frame)

            # Send result back to Unity
            await ws.send_json({
                "type": "vision_update",
                "objects": result["objects"],
                "scene": result["scene"],
                "sign": result.get("sign"),
                "injected": result["fast_injected"] or result["deep_injected"] or result.get("sign_injected", False),
            })

    except WebSocketDisconnect:
        logger.info("Vision WebSocket client disconnected")
    except Exception:
        logger.exception("Vision WebSocket error")
        if ws.client_state == WebSocketState.CONNECTED:
            await ws.send_json({"type": "error", "error": "Internal server error"})
