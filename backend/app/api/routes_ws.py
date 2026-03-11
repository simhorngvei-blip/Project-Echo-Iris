"""
Echo-Iris — WebSocket Chat Route

Provides a streaming-friendly, bidirectional WebSocket endpoint at ``/ws/chat``.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.models.schemas import WSMessage, WSResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/chat")
async def websocket_chat(ws: WebSocket):
    """
    Bidirectional chat over WebSocket.

    Inbound JSON::

        {"type": "chat", "message": "Hello!"}

    Outbound JSON::

        {"type": "reply", "reply": "Hi there!", "error": null}
    """
    await ws.accept()
    logger.info("WebSocket client connected")

    from app.main import get_brain  # deferred to avoid circular import

    brain = get_brain()

    try:
        while True:
            raw = await ws.receive_text()
            try:
                payload = WSMessage.model_validate_json(raw)
            except Exception:
                await ws.send_text(
                    WSResponse(type="error", error="Invalid JSON payload").model_dump_json()
                )
                continue

            if payload.type != "chat":
                await ws.send_text(
                    WSResponse(type="error", error=f"Unknown type: {payload.type}").model_dump_json()
                )
                continue

            try:
                result = await brain.process(payload.message)
                resp = WSResponse(type="reply", reply=result["reply"])
            except Exception as exc:
                logger.exception("WS chat processing failed")
                resp = WSResponse(type="error", error=str(exc))

            await ws.send_text(resp.model_dump_json())

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
