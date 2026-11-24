"""In-memory mock serial transport emulating ARCADELED_V1 Pico firmware.

Emulates the exact ASCII serial protocol verified in
`pico/arcadeled_pico/arcadeled_pico.ino`:
  - `HELLO`        -> `ARCADELED_V1`
  - `ALL ON`       -> `OK`
  - `ALL OFF`      -> `OK`
  - `LED<1-4> ON`  -> `OK`
  - `LED<1-4> OFF` -> `OK`
  - invalid line   -> `ERROR`

Includes fault injection (disconnects, timeouts, corrupted replies) for unit tests.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from host.transports.base_transport import (
    BaseTransport,
    TransportDisconnectedError,
    TransportProtocolError,
    TransportTimeoutError,
)
from host.transports.serial_transport import (
    CANONICAL_LEDS,
    DEFAULT_DEVICE_ID,
    build_wire_commands,
)


class MockTransport(BaseTransport):
    """Simulated USB Serial transport mimicking ARCADELED_V1 firmware."""

    def __init__(
        self,
        port: str = "MOCK_SERIAL",
        baud_rate: int = 115200,
        device_id: str = DEFAULT_DEVICE_ID,
        auto_reconnect: bool = True,
        reconnect_attempts: int = 3,
    ) -> None:
        self.port = port
        self.baud_rate = baud_rate
        self.device_id = device_id
        self.auto_reconnect = auto_reconnect
        self.reconnect_attempts = max(1, reconnect_attempts)

        self._connected: bool = False
        self._led_state: Dict[str, bool] = {led: False for led in CANONICAL_LEDS}
        self.sent_frames: List[str] = []
        self.command_history: List[Dict[str, Any]] = []
        self.reconnect_count: int = 0

        # Fault-injection controls for deterministic unit testing
        self._fail_connect_remaining: int = 0
        self._fail_write_remaining: int = 0
        self._force_timeout_remaining: int = 0
        self._next_raw_response: Optional[str] = None

    @property
    def current_led_state(self) -> Dict[str, bool]:
        return dict(self._led_state)

    def connect(self) -> None:
        if self._fail_connect_remaining > 0:
            self._fail_connect_remaining -= 1
            self._connected = False
            raise TransportDisconnectedError(f"Mock failed to connect to {self.port}")
        self._connected = True
        reply = self._emulate_firmware_line("HELLO")
        if reply != self.device_id:
            self._connected = False
            raise TransportProtocolError(
                f"Mock handshake mismatch: got {reply!r}, expected {self.device_id!r}"
            )

    def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    # --- Fault injection helpers for testing ---
    def simulate_disconnect(self, fail_next_connects: int = 0) -> None:
        """Drop the simulated serial connection."""
        self._connected = False
        self._fail_connect_remaining = max(0, fail_next_connects)

    def simulate_write_failures(self, count: int) -> None:
        """Cause the next `count` write attempts to drop the connection."""
        self._fail_write_remaining = max(0, count)

    def simulate_timeout(self, count: int = 1) -> None:
        """Cause the next `count` commands to raise TransportTimeoutError."""
        self._force_timeout_remaining = max(0, count)

    def inject_raw_response(self, raw_line: str) -> None:
        """Force the next firmware response line to a custom raw string."""
        self._next_raw_response = raw_line

    def send_command(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        wire_pairs = build_wire_commands(payload)
        attempts = self.reconnect_attempts if self.auto_reconnect else 1
        last_error: Optional[Exception] = None

        for attempt in range(attempts):
            try:
                if not self._connected:
                    if attempt == 0 and not self.auto_reconnect:
                        raise TransportDisconnectedError("Mock transport is disconnected.")
                    self.connect()
                    self.reconnect_count += 1

                if self._fail_write_remaining > 0:
                    self._fail_write_remaining -= 1
                    self._connected = False
                    raise TransportDisconnectedError("Simulated USB serial disconnect during write.")

                if self._force_timeout_remaining > 0:
                    self._force_timeout_remaining -= 1
                    raise TransportTimeoutError("Simulated timeout waiting for Pico response.")

                exchanges: List[Dict[str, str]] = []
                for line, expected in wire_pairs:
                    target_expected = self.device_id if line == "HELLO" else expected
                    reply = self._emulate_firmware_line(line)
                    self.sent_frames.append(line + "\n")
                    exchanges.append({"sent": line, "reply": reply})
                    if reply != target_expected:
                        raise TransportProtocolError(
                            f"Unexpected mock Pico reply for '{line}': "
                            f"got {reply!r}, expected {target_expected!r}"
                        )

                self.command_history.append(payload)
                return {
                    "status": "ok",
                    "port": self.port,
                    "device_id": self.device_id,
                    "exchanges": exchanges,
                }

            except (TransportDisconnectedError, TransportTimeoutError) as exc:
                last_error = exc
                if not self.auto_reconnect or attempt + 1 >= attempts:
                    raise

        raise last_error or TransportDisconnectedError("Mock transport send failed.")

    def _emulate_firmware_line(self, raw_line: str) -> str:
        """Mirror `processCommand()` in `pico/arcadeled_pico/arcadeled_pico.ino`."""
        if self._next_raw_response is not None:
            reply = self._next_raw_response.strip()
            self._next_raw_response = None
            return reply

        command = raw_line.strip().upper()
        if command == "HELLO":
            return self.device_id

        if command in {"ALL ON", "ALL OFF"}:
            on = command == "ALL ON"
            for led in CANONICAL_LEDS:
                self._led_state[led] = on
            return "OK"

        if command.startswith("LED") and len(command) >= 6:
            space_idx = command.find(" ")
            if space_idx > 3:
                try:
                    led_num = int(command[3:space_idx])
                except ValueError:
                    led_num = 0
                action = command[space_idx + 1 :].strip()
                if 1 <= led_num <= 16 and action in {"ON", "OFF"}:
                    led_key = f"LED{led_num}"
                    if led_key in self._led_state:
                        self._led_state[led_key] = action == "ON"
                    return "OK"

        return "ERROR"
