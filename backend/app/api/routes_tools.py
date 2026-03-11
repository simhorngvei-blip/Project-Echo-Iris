"""
Echo-Iris — Tool REST Endpoints

Provides HTTP endpoints so the Unity DebugUI can directly trigger
tools without going through the LLM's LangChain pipeline.

    POST /api/tools/timer    — set a countdown timer
    POST /api/tools/open_app — launch a desktop app
    POST /api/tools/robot    — send a robot command
"""

from __future__ import annotations

import logging
from pydantic import BaseModel, Field

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tools", tags=["tools"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class TimerRequest(BaseModel):
    seconds: int = Field(..., gt=0, le=3600, description="Timer duration in seconds")
    message: str = Field("Timer expired!", description="Notification message")


class OpenAppRequest(BaseModel):
    app_name: str = Field(..., description="Application name to open")


class RobotRequest(BaseModel):
    action: str = Field(..., description="Robot action to execute")
    parameters: str = Field("{}", description="JSON string of action parameters")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/timer")
async def set_timer_endpoint(req: TimerRequest):
    """Set a countdown timer that injects a notification into STM."""
    from app.tools.registry import set_timer
    result = set_timer.invoke({"seconds": req.seconds, "message": req.message})
    logger.info("Tool REST: set_timer(%ds, %s) -> %s", req.seconds, req.message, result)
    return {"status": "ok", "result": result}


@router.post("/open_app")
async def open_app_endpoint(req: OpenAppRequest):
    """Launch a desktop application by name."""
    from app.tools.registry import open_application
    result = open_application.invoke({"app_name": req.app_name})
    logger.info("Tool REST: open_app(%s) -> %s", req.app_name, result)
    return {"status": "ok", "result": result}


@router.post("/robot")
async def robot_command_endpoint(req: RobotRequest):
    """Send a command to the physical robot."""
    from app.tools.registry import execute_robot_action
    result = execute_robot_action.invoke(
        {"action": req.action, "parameters": req.parameters}
    )
    logger.info("Tool REST: robot(%s) -> %s", req.action, result)
    return {"status": "ok", "result": result}
