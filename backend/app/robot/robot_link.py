"""
Echo-Iris — Robot Link

Manages a serial connection to an external microcontroller
(ATmega2560 / ESP32) for physical robot control.

Features:
  - Auto-detection of common boards (Arduino, ESP32, CH340)
  - Non-blocking write queue (daemon thread)
  - Background read thread for ACK parsing
  - JSON newline-delimited command protocol
  - Safety: speed clamping, duration caps, emergency stop on disconnect
"""

from __future__ import annotations

import json
import logging
import queue
import threading
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Safety limits
_MAX_SPEED = 100
_MAX_DURATION_MS = 5000

# Allowed robot actions
ROBOT_ACTIONS = frozenset({
    "move_forward", "move_backward",
    "turn_left", "turn_right",
    "stop",
    "wave_arm", "nod_head",
    "set_led", "play_tone",
})


class RobotLink:
    """
    Serial connection manager for physical robot control.

    Non-blocking: commands are queued and sent by a background thread.
    Thread-safe for use from the LLM tool executor.
    """

    def __init__(
        self,
        port: Optional[str] = None,
        baud_rate: int = 115200,
        timeout: float = 1.0,
    ):
        self._port = port
        self._baud_rate = baud_rate
        self._timeout = timeout

        self._serial = None
        self._connected = False
        self._running = False

        # Non-blocking write queue
        self._write_queue: queue.Queue[bytes] = queue.Queue(maxsize=64)
        self._writer_thread: Optional[threading.Thread] = None
        self._reader_thread: Optional[threading.Thread] = None

        # Last response from MCU
        self._last_response: Optional[str] = None
        self._lock = threading.Lock()

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def last_response(self) -> Optional[str]:
        with self._lock:
            return self._last_response

    # --- Connection management ------------------------------------------------

    def connect(self) -> bool:
        """
        Open serial connection. Auto-detects port if not specified.
        Returns True on success, False on failure.
        """
        try:
            import serial
            import serial.tools.list_ports
        except ImportError:
            logger.error("pyserial not installed — run: pip install pyserial")
            return False

        # Resolve port
        port = self._port
        if port is None or port.lower() == "auto":
            port = self._auto_detect_port()
            if port is None:
                logger.warning("No robot board detected on any serial port")
                return False

        try:
            self._serial = serial.Serial(
                port=port,
                baudrate=self._baud_rate,
                timeout=self._timeout,
            )
            self._connected = True
            self._running = True

            # Start background threads
            self._writer_thread = threading.Thread(
                target=self._writer_loop, daemon=True, name="robot-writer"
            )
            self._writer_thread.start()

            self._reader_thread = threading.Thread(
                target=self._reader_loop, daemon=True, name="robot-reader"
            )
            self._reader_thread.start()

            logger.info("Robot connected on %s @ %d baud", port, self._baud_rate)
            return True

        except Exception as e:
            logger.error("Failed to connect to robot on %s: %s", port, e)
            self._connected = False
            return False

    def disconnect(self) -> None:
        """Disconnect from the robot. Sends emergency stop first."""
        if not self._connected:
            return

        # Send emergency stop (bypass queue — direct write)
        try:
            if self._serial and self._serial.is_open:
                stop_cmd = json.dumps({"cmd": "stop"}) + "\n"
                self._serial.write(stop_cmd.encode())
                self._serial.flush()
                logger.info("Emergency stop sent on disconnect")
        except Exception:
            pass

        self._running = False
        self._connected = False

        try:
            if self._serial:
                self._serial.close()
        except Exception:
            pass

        logger.info("Robot disconnected")

    # --- Command sending ------------------------------------------------------

    def send_command(self, cmd: str, params: Optional[dict[str, Any]] = None) -> str:
        """
        Queue a command to the robot.

        Parameters
        ----------
        cmd : str — action name (must be in ROBOT_ACTIONS)
        params : dict — optional parameters (speed, angle, etc.)

        Returns
        -------
        str — confirmation or error message.
        """
        if not self._connected:
            return "Robot not connected."

        if cmd not in ROBOT_ACTIONS:
            return f"Unknown robot action: '{cmd}'. Allowed: {', '.join(sorted(ROBOT_ACTIONS))}"

        # Build payload with safety clamping
        payload: dict[str, Any] = {"cmd": cmd}
        if params:
            payload.update(self._clamp_params(params))

        # Serialise and queue
        line = json.dumps(payload) + "\n"
        try:
            self._write_queue.put_nowait(line.encode())
            logger.info("Queued robot command: %s", cmd)
            return f"Robot command sent: {cmd}"
        except queue.Full:
            logger.warning("Robot write queue full — command dropped: %s", cmd)
            return f"Robot busy — command '{cmd}' dropped."

    @staticmethod
    def _clamp_params(params: dict[str, Any]) -> dict[str, Any]:
        """Apply safety limits to command parameters."""
        clamped = dict(params)

        if "speed" in clamped:
            clamped["speed"] = max(0, min(int(clamped["speed"]), _MAX_SPEED))

        if "duration_ms" in clamped:
            clamped["duration_ms"] = max(0, min(int(clamped["duration_ms"]), _MAX_DURATION_MS))

        if "angle" in clamped:
            clamped["angle"] = max(-360, min(int(clamped["angle"]), 360))

        # RGB clamping
        for ch in ("r", "g", "b"):
            if ch in clamped:
                clamped[ch] = max(0, min(int(clamped[ch]), 255))

        if "freq" in clamped:
            clamped["freq"] = max(20, min(int(clamped["freq"]), 20000))

        return clamped

    # --- Background threads ---------------------------------------------------

    def _writer_loop(self):
        """Background thread: drain write queue → serial port."""
        while self._running:
            try:
                data = self._write_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                if self._serial and self._serial.is_open:
                    self._serial.write(data)
                    self._serial.flush()
            except Exception as e:
                logger.error("Robot write error: %s", e)
                self._connected = False
                break

    def _reader_loop(self):
        """Background thread: read ACK/NACK lines from MCU."""
        while self._running:
            try:
                if not self._serial or not self._serial.is_open:
                    break
                line = self._serial.readline().decode(errors="replace").strip()
                if line:
                    with self._lock:
                        self._last_response = line
                    logger.info("Robot ACK: %s", line[:100])
            except Exception as e:
                if self._running:
                    logger.error("Robot read error: %s", e)
                break

    # --- Auto-detection -------------------------------------------------------

    @staticmethod
    def _auto_detect_port() -> Optional[str]:
        """Scan serial ports for known microcontroller boards."""
        try:
            import serial.tools.list_ports
        except ImportError:
            return None

        keywords = ("arduino", "ch340", "ch341", "cp210", "esp32", "mega", "uno", "ftdi")
        for port_info in serial.tools.list_ports.comports():
            desc = (port_info.description or "").lower()
            mfr = (port_info.manufacturer or "").lower()
            if any(kw in desc or kw in mfr for kw in keywords):
                logger.info("Auto-detected robot port: %s (%s)", port_info.device, port_info.description)
                return port_info.device

        return None
