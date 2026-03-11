"""
Tests for the Machine Control & Tool Use module.

Tests cover:
  - get_current_time output format
  - open_application allowlist enforcement (mocked subprocess)
  - set_timer non-blocking behavior and STM injection
  - ToolExecutor timeout and error handling
  - Brain tool-call integration (mocked LLM)
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.stm import ShortTermMemory
from app.tools.executor import ToolExecutor
from app.tools.registry import (
    ALL_TOOLS,
    get_current_time,
    open_application,
    open_url,
    set_timer,
    set_stm_reference,
)


class TestGetCurrentTime:
    """Tests for the get_current_time tool."""

    def test_returns_string(self):
        result = get_current_time.invoke({})
        assert isinstance(result, str)

    def test_contains_date_components(self):
        result = get_current_time.invoke({})
        # Should contain day of week and AM/PM
        assert any(day in result for day in [
            "Monday", "Tuesday", "Wednesday", "Thursday",
            "Friday", "Saturday", "Sunday",
        ])
        assert "AM" in result or "PM" in result


class TestOpenApplication:
    """Tests for the open_application tool (all with mocked subprocess)."""

    @patch("app.tools.registry.subprocess.Popen")
    def test_allowed_app_succeeds(self, mock_popen):
        result = open_application.invoke({"app_name": "notepad"})
        assert "Successfully opened" in result
        mock_popen.assert_called_once()

    @patch("app.tools.registry.subprocess.Popen")
    def test_allowed_app_case_insensitive(self, mock_popen):
        result = open_application.invoke({"app_name": "Notepad"})
        assert "Successfully opened" in result

    @patch("app.tools.registry.subprocess.Popen")
    def test_blocked_app_rejected(self, mock_popen):
        result = open_application.invoke({"app_name": "malware.exe"})
        assert "Cannot open" in result
        assert "not in the allowed" in result
        mock_popen.assert_not_called()

    @patch("app.tools.registry.subprocess.Popen", side_effect=FileNotFoundError)
    def test_app_not_found(self, mock_popen):
        result = open_application.invoke({"app_name": "calculator"})
        assert "Could not find" in result


class TestSetTimer:
    """Tests for the set_timer tool."""

    def test_returns_confirmation(self):
        result = set_timer.invoke({"seconds": 5, "message": "test timer"})
        assert "Timer set for 5 seconds" in result

    def test_negative_seconds_rejected(self):
        result = set_timer.invoke({"seconds": -1, "message": "bad"})
        assert "must be positive" in result

    def test_non_blocking(self):
        """Timer should return immediately, not block."""
        start = time.monotonic()
        set_timer.invoke({"seconds": 10, "message": "future"})
        elapsed = time.monotonic() - start
        assert elapsed < 1.0  # should return in well under 1 second

    def test_stm_injection_on_expiry(self):
        stm = ShortTermMemory(max_messages=50)
        set_stm_reference(stm)

        set_timer.invoke({"seconds": 1, "message": "ding!"})
        # Wait for timer
        time.sleep(1.5)

        raw = stm.get_raw()
        timer_msgs = [e for e in raw if "[Timer]" in e["content"]]
        assert len(timer_msgs) >= 1
        assert "ding!" in timer_msgs[0]["content"]

        # Clean up
        set_stm_reference(None)


class TestOpenUrl:
    """Tests for the open_url tool."""

    @patch("app.tools.registry.webbrowser.open")
    def test_opens_url_with_https(self, mock_open):
        result = open_url.invoke({"url": "google.com"})
        assert "Opened" in result
        mock_open.assert_called_once_with("https://google.com")

    @patch("app.tools.registry.webbrowser.open")
    def test_preserves_existing_https(self, mock_open):
        result = open_url.invoke({"url": "https://youtube.com"})
        assert "Opened" in result
        mock_open.assert_called_once_with("https://youtube.com")

    @patch("app.tools.registry.webbrowser.open", side_effect=Exception("fail"))
    def test_handles_error(self, mock_open):
        result = open_url.invoke({"url": "https://broken.test"})
        assert "Failed" in result


class TestToolExecutor:
    """Tests for the ToolExecutor wrapper."""

    def test_execute_known_tool(self):
        executor = ToolExecutor(ALL_TOOLS)
        result = executor.execute({
            "name": "get_current_time",
            "args": {},
            "id": "test-1",
        })
        assert isinstance(result, str)
        assert len(result) > 0

    def test_execute_unknown_tool(self):
        executor = ToolExecutor(ALL_TOOLS)
        result = executor.execute({
            "name": "nonexistent_tool",
            "args": {},
            "id": "test-2",
        })
        assert "Unknown tool" in result

    @patch("app.tools.registry.subprocess.Popen")
    def test_execute_open_app_via_executor(self, mock_popen):
        executor = ToolExecutor(ALL_TOOLS)
        result = executor.execute({
            "name": "open_application",
            "args": {"app_name": "notepad"},
            "id": "test-3",
        })
        assert "Successfully opened" in result


class TestBrainToolIntegration:
    """Tests for Brain's tool-call detection and execution loop."""

    @pytest.mark.asyncio
    async def test_brain_with_tool_call(self):
        """Brain should detect tool_calls, execute them, and re-invoke."""
        stm = ShortTermMemory(max_messages=50)

        mock_llm = MagicMock()
        mock_llm.bind_tools = MagicMock()

        # First invoke returns a tool call
        tool_response = MagicMock()
        tool_response.tool_calls = [{
            "name": "get_current_time",
            "args": {},
            "id": "call-1",
        }]
        tool_response.content = ""
        mock_llm.invoke_with_tools = AsyncMock(return_value=tool_response)

        # Second invoke (after tool result) returns text
        mock_llm.invoke = AsyncMock(return_value="It's 3 PM on Monday!")

        mock_ltm = MagicMock()
        mock_ltm.retrieve.return_value = []

        # Import Brain but patch settings to disable auto-init
        with patch("app.core.brain.settings") as mock_settings:
            mock_settings.tools_enabled = False
            mock_settings.system_prompt = "You are a test assistant."

            from app.core.brain import Brain
            brain = Brain(stm=stm, ltm=mock_ltm, llm=mock_llm)

        # Manually set up tools
        from app.tools.registry import ALL_TOOLS
        from app.tools.executor import ToolExecutor
        brain._tool_executor = ToolExecutor(ALL_TOOLS)

        result = await brain.process("What time is it?")
        assert "reply" in result
        assert len(result["reply"]) > 0

    @pytest.mark.asyncio
    async def test_brain_without_tool_call(self):
        """Brain should pass-through when no tools are used."""
        stm = ShortTermMemory(max_messages=50)

        mock_llm = MagicMock()
        mock_llm.bind_tools = MagicMock()

        response = MagicMock()
        response.tool_calls = []
        response.content = "Hello there!"
        mock_llm.invoke_with_tools = AsyncMock(return_value=response)

        mock_ltm = MagicMock()
        mock_ltm.retrieve.return_value = []

        with patch("app.core.brain.settings") as mock_settings:
            mock_settings.tools_enabled = False
            mock_settings.system_prompt = "You are a test assistant."

            from app.core.brain import Brain
            brain = Brain(stm=stm, ltm=mock_ltm, llm=mock_llm)

        brain._tool_executor = ToolExecutor(ALL_TOOLS)
        result = await brain.process("Hello!")
        assert result["reply"] == "Hello there!"
