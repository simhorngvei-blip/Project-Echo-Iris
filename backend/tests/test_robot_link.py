"""
Tests for the Physical Robot Control module.

Tests cover:
  - RobotLink command queueing (non-blocking)
  - Action allowlist enforcement
  - Safety param clamping (speed, duration, angle, RGB, freq)
  - Auto-detection with no ports
  - Disconnect sends stop
  - Tool behaviour when robot not connected
  - execute_robot_action tool validation
"""

from __future__ import annotations

import json
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from app.robot.robot_link import ROBOT_ACTIONS, RobotLink


class TestRobotLinkCommands:
    """Tests for RobotLink command queueing."""

    def test_send_command_when_disconnected(self):
        link = RobotLink(port="COM99")
        result = link.send_command("wave_arm")
        assert "not connected" in result.lower()

    def test_send_unknown_action_rejected(self):
        link = RobotLink()
        link._connected = True  # simulate connected
        result = link.send_command("self_destruct")
        assert "Unknown robot action" in result

    def test_send_valid_action_queues(self):
        link = RobotLink()
        link._connected = True
        result = link.send_command("wave_arm")
        assert "sent" in result.lower()
        # Verify it was queued
        data = link._write_queue.get_nowait()
        payload = json.loads(data.decode().strip())
        assert payload["cmd"] == "wave_arm"

    def test_send_with_params(self):
        link = RobotLink()
        link._connected = True
        link.send_command("move_forward", {"speed": 50, "duration_ms": 1000})
        data = link._write_queue.get_nowait()
        payload = json.loads(data.decode().strip())
        assert payload["cmd"] == "move_forward"
        assert payload["speed"] == 50
        assert payload["duration_ms"] == 1000

    def test_queue_full_returns_error(self):
        link = RobotLink()
        link._connected = True
        # Fill the queue
        for _ in range(64):
            link.send_command("stop")
        # Next should fail
        result = link.send_command("stop")
        assert "busy" in result.lower() or "dropped" in result.lower()


class TestSafetyClamping:
    """Tests for parameter safety limits."""

    def test_speed_clamped_to_100(self):
        result = RobotLink._clamp_params({"speed": 200})
        assert result["speed"] == 100

    def test_speed_clamped_to_0(self):
        result = RobotLink._clamp_params({"speed": -50})
        assert result["speed"] == 0

    def test_duration_capped_at_5000(self):
        result = RobotLink._clamp_params({"duration_ms": 99999})
        assert result["duration_ms"] == 5000

    def test_angle_clamped(self):
        result = RobotLink._clamp_params({"angle": 500})
        assert result["angle"] == 360

    def test_rgb_clamped(self):
        result = RobotLink._clamp_params({"r": 300, "g": -10, "b": 128})
        assert result["r"] == 255
        assert result["g"] == 0
        assert result["b"] == 128

    def test_freq_clamped(self):
        result = RobotLink._clamp_params({"freq": 50000})
        assert result["freq"] == 20000

    def test_normal_params_unchanged(self):
        result = RobotLink._clamp_params({"speed": 50, "duration_ms": 2000})
        assert result["speed"] == 50
        assert result["duration_ms"] == 2000


class TestAutoDetection:
    """Tests for serial port auto-detection."""

    @patch("serial.tools.list_ports.comports", return_value=[])
    def test_no_ports_returns_none(self, mock_comports):
        result = RobotLink._auto_detect_port()
        assert result is None

    @patch("serial.tools.list_ports.comports")
    def test_detects_arduino(self, mock_comports):
        mock_port = MagicMock()
        mock_port.device = "COM3"
        mock_port.description = "Arduino Mega 2560"
        mock_port.manufacturer = "Arduino"
        mock_comports.return_value = [mock_port]
        result = RobotLink._auto_detect_port()
        assert result == "COM3"

    @patch("serial.tools.list_ports.comports")
    def test_detects_esp32(self, mock_comports):
        mock_port = MagicMock()
        mock_port.device = "COM5"
        mock_port.description = "CP2102 USB to UART"
        mock_port.manufacturer = "ESP32 manufacturer"
        mock_comports.return_value = [mock_port]
        # CP210 keyword should match
        result = RobotLink._auto_detect_port()
        assert result == "COM5"

    @patch("serial.tools.list_ports.comports")
    def test_ignores_unknown_devices(self, mock_comports):
        mock_port = MagicMock()
        mock_port.device = "COM7"
        mock_port.description = "Random USB gadget"
        mock_port.manufacturer = "Unknown"
        mock_comports.return_value = [mock_port]
        result = RobotLink._auto_detect_port()
        assert result is None


class TestDisconnect:
    """Tests for disconnect behaviour."""

    def test_disconnect_sends_stop(self):
        link = RobotLink()
        mock_serial = MagicMock()
        mock_serial.is_open = True
        link._serial = mock_serial
        link._connected = True
        link._running = True

        link.disconnect()

        # Verify stop was written
        mock_serial.write.assert_called_once()
        written = mock_serial.write.call_args[0][0]
        payload = json.loads(written.decode().strip())
        assert payload["cmd"] == "stop"
        assert not link.is_connected

    def test_disconnect_when_already_disconnected(self):
        link = RobotLink()
        link.disconnect()  # Should not raise


class TestRobotActionTool:
    """Tests for the execute_robot_action LLM tool."""

    def test_unknown_action_rejected(self):
        from app.tools.registry import execute_robot_action
        result = execute_robot_action.invoke({"action": "fly_away"})
        assert "Unknown robot action" in result

    def test_robot_not_connected(self):
        from app.tools import registry
        registry._robot_link_ref = None
        result = registry.execute_robot_action.invoke({"action": "wave_arm"})
        assert "not connected" in result.lower()

    def test_robot_connected_sends_command(self):
        from app.tools import registry
        mock_link = MagicMock()
        mock_link.is_connected = True
        mock_link.send_command.return_value = "Robot command sent: wave_arm"
        registry._robot_link_ref = mock_link

        result = registry.execute_robot_action.invoke(
            {"action": "wave_arm", "parameters": "{}"}
        )
        assert "sent" in result.lower()
        mock_link.send_command.assert_called_once_with("wave_arm", {})

        # Cleanup
        registry._robot_link_ref = None

    def test_invalid_parameters_json(self):
        from app.tools import registry
        mock_link = MagicMock()
        mock_link.is_connected = True
        registry._robot_link_ref = mock_link

        result = registry.execute_robot_action.invoke(
            {"action": "wave_arm", "parameters": "{bad json"}
        )
        assert "Invalid parameters JSON" in result

        # Cleanup
        registry._robot_link_ref = None

    def test_robot_actions_set_is_complete(self):
        expected = {
            "move_forward", "move_backward", "turn_left", "turn_right",
            "stop", "wave_arm", "nod_head", "set_led", "play_tone",
        }
        assert ROBOT_ACTIONS == expected
