"""
Echo-Iris — Tool Registry

Defines LangChain @tool functions for OS interaction:
  - get_current_time
  - open_application (with allowlist)
  - open_url (open websites in default browser)
  - set_timer (non-blocking, STM injection)
  - execute_robot_action (serial robot commands)
"""

from __future__ import annotations

import json
import logging
import subprocess
import threading
import webbrowser
from datetime import datetime

from langchain_core.tools import tool

from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application allowlist — maps friendly names to executables
# ---------------------------------------------------------------------------
_APP_ALLOWLIST: dict[str, str] = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "paint": "mspaint.exe",
    "snipping tool": "SnippingTool.exe",
    "snip": "SnippingTool.exe",
    "task manager": "taskmgr.exe",
    "cmd": "cmd.exe",
    "command prompt": "cmd.exe",
    "powershell": "powershell.exe",
    "terminal": "powershell.exe",
    "browser": "explorer.exe",
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "firefox": "firefox.exe",
    "edge": "msedge.exe",
    "microsoft edge": "msedge.exe",
}

# Reference to STM — set by the Brain during init
_stm_ref = None


def set_stm_reference(stm) -> None:
    """Allow the Brain to provide the STM instance for timer callbacks."""
    global _stm_ref
    _stm_ref = stm


# Reference to RobotLink — set by the Brain during init
_robot_link_ref = None


def set_robot_link_reference(robot_link) -> None:
    """Allow the Brain to provide the RobotLink instance for robot commands."""
    global _robot_link_ref
    _robot_link_ref = robot_link


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

@tool
def get_current_time() -> str:
    """Get the current local date and time. Use this when the user asks what time or date it is."""
    now = datetime.now()
    return now.strftime("%A, %B %d, %Y at %I:%M %p")


@tool
def open_application(app_name: str) -> str:
    """Open a Windows application by name. Supported: notepad, calculator, explorer, paint, snipping tool, task manager, cmd, powershell. Use this when the user asks to open or launch an application."""
    name_lower = app_name.strip().lower()

    # Check allowlist
    executable = _APP_ALLOWLIST.get(name_lower)
    if executable is None:
        allowed = ", ".join(sorted(set(_APP_ALLOWLIST.values())))
        logger.warning("Blocked app launch attempt: %s", app_name)
        return (
            f"Cannot open '{app_name}' — not in the allowed applications list. "
            f"Allowed: {allowed}"
        )

    try:
        # Use subprocess.Popen for non-blocking launch
        subprocess.Popen(
            [executable],
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info("Launched application: %s (%s)", app_name, executable)
        return f"Successfully opened {app_name}."
    except FileNotFoundError:
        logger.error("Application not found: %s", executable)
        return f"Could not find '{app_name}' on this system."
    except Exception as e:
        logger.exception("Failed to open %s", app_name)
        return f"Failed to open '{app_name}': {e}"


@tool
def set_timer(seconds: int, message: str) -> str:
    """Set a countdown timer that fires after the given number of seconds with a notification message. Use this when the user asks to set a timer, reminder, or alarm."""
    if seconds <= 0:
        return "Timer duration must be positive."
    if seconds > settings.tools_timer_max_seconds:
        return f"Timer too long. Maximum is {settings.tools_timer_max_seconds} seconds."

    def _on_timer_expire():
        notification = f"[Timer] ⏰ Timer expired: {message}"
        logger.info(notification)
        if _stm_ref is not None:
            _stm_ref.append("system", notification)

    timer = threading.Timer(seconds, _on_timer_expire)
    timer.daemon = True
    timer.start()

    logger.info("Timer set: %ds — %s", seconds, message)
    return f"Timer set for {seconds} seconds: {message}"


@tool
def open_url(url: str) -> str:
    """Open a website URL in the user's default web browser. Use this when the user asks to go to a website, search something online, or open a web page. Add https:// if missing."""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        webbrowser.open(url)
        logger.info("Opened URL: %s", url)
        return f"Opened {url} in your default browser."
    except Exception as e:
        logger.exception("Failed to open URL: %s", url)
        return f"Failed to open {url}: {e}"

@tool
def execute_robot_action(action: str, parameters: str = "{}") -> str:
    """Send a command to the physical robot. Actions: move_forward, move_backward, turn_left, turn_right, stop, wave_arm, nod_head, set_led, play_tone. Parameters is a JSON string with optional keys like speed, duration_ms, angle, r, g, b, freq."""
    from app.robot.robot_link import ROBOT_ACTIONS

    action_lower = action.strip().lower()

    if action_lower not in ROBOT_ACTIONS:
        return (
            f"Unknown robot action: '{action}'. "
            f"Allowed: {', '.join(sorted(ROBOT_ACTIONS))}"
        )

    if _robot_link_ref is None or not _robot_link_ref.is_connected:
        return "Robot not connected."

    # Parse parameters JSON
    try:
        params = json.loads(parameters) if parameters else {}
    except json.JSONDecodeError:
        return f"Invalid parameters JSON: {parameters}"

    result = _robot_link_ref.send_command(action_lower, params)
    logger.info("Robot action: %s(%s) -> %s", action, parameters, result)
    return result


# ---------------------------------------------------------------------------
# Registry — collect all tools for binding
# ---------------------------------------------------------------------------

ALL_TOOLS = [get_current_time, open_application, open_url, set_timer, execute_robot_action]
