"""USB CDC Serial transport for Raspberry Pi Pico."""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from host.transports.base_transport import (
    BaseTransport,
    TransportDisconnectedError,
    TransportError,
    TransportProtocolError,
    TransportTimeoutError,
)
from host.transports.pico_discovery import resolve_pico_port

DEFAULT_DEVICE_ID = "ARCADELED_V1"
CANONICAL_LEDS = tuple(f"LED{i}" for i in range(1, 7))


def build_wire_commands(payload: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Translate a host command dict into `(wire_line, expected_reply)` pairs."""
    if not isinstance(payload, dict):
        raise TransportProtocolError("Command payload must be a dictionary.")

    cmd = str(payload.get("command") or "").strip().lower()

    if cmd in {"ping", "hello"}:
        return [("HELLO", DEFAULT_DEVICE_ID)]

    if cmd in {"clear_leds", "all_off"}:
        return [("ALL OFF", "OK")]

    if cmd == "all_on":
        return [("ALL ON", "OK")]

    if cmd == "raw":
        line = str(payload.get("line") or "").strip()
        if not line:
            raise TransportProtocolError("Raw command requires a non-empty 'line' field.")
        expected = str(payload.get("expected") or "OK").strip()
        return [(line, expected)]

    if cmd == "set_leds":
        # Prefer explicit pre-computed wire lines if provided
        lines = payload.get("lines")
        if isinstance(lines, list) and lines:
            return [(str(line).strip(), "OK") for line in lines if str(line).strip()]

        leds = payload.get("leds")
        if not isinstance(leds, dict):
            raise TransportProtocolError("Missing or invalid 'leds' mapping in set_leds payload.")

        normalized: Dict[str, bool] = {}
        for led_id, spec in leds.items():
            key = str(led_id).strip().upper()
            if key not in CANONICAL_LEDS:
                continue
            if isinstance(spec, dict):
                raw_state = spec.get("state", False)
            else:
                raw_state = spec
            normalized[key] = bool(raw_state)

        if not normalized:
            return [("ALL OFF", "OK")]

        # If all 4 LEDs share the exact same state, use compact ALL ON / ALL OFF command
        if all(led in normalized for led in CANONICAL_LEDS):
            if all(normalized[led] for led in CANONICAL_LEDS):
                return [("ALL ON", "OK")]
            if not any(normalized[led] for led in CANONICAL_LEDS):
                return [("ALL OFF", "OK")]

        commands: List[Tuple[str, str]] = []
        for led in CANONICAL_LEDS:
            if led in normalized:
                action = "ON" if normalized[led] else "OFF"
                commands.append((f"{led} {action}", "OK"))
        return commands

    raise TransportProtocolError(f"Unsupported host command: {cmd!r}")


class SerialTransport(BaseTransport):
    """Real USB Serial transport communicating with ARCADELED_V1 on Raspberry Pi Pico."""

    def __init__(
        self,
        port: str = "auto",
        baud_rate: int = 115200,
        device_id: str = DEFAULT_DEVICE_ID,
        startup_delay_seconds: float = 2.0,
        timeout_seconds: float = 2.0,
        write_timeout_seconds: float = 2.0,
        reconnect_attempts: int = 3,
        reconnect_delay_seconds: float = 0.5,
        serial_factory: Optional[Callable[..., Any]] = None,
        comports_fn: Optional[Callable[[], Iterable[Any]]] = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.configured_port = port
        self.resolved_port: Optional[str] = None
        self.baud_rate = int(baud_rate)
        self.device_id = str(device_id or DEFAULT_DEVICE_ID).strip()
        self.startup_delay_seconds = max(0.0, float(startup_delay_seconds))
        self.timeout_seconds = float(timeout_seconds)
        self.write_timeout_seconds = float(write_timeout_seconds)
        self.reconnect_attempts = max(1, int(reconnect_attempts))
        self.reconnect_delay_seconds = max(0.0, float(reconnect_delay_seconds))
        self._serial_factory = serial_factory
        self._comports_fn = comports_fn
        self._sleep = sleep_fn
        self._conn: Any = None
        self.reconnect_count: int = 0

    @property
    def port(self) -> str:
        return self.resolved_port or self.configured_port

    def _open_serial(self, port_name: str) -> Any:
        if self._serial_factory is not None:
            return self._serial_factory(
                port=port_name,
                baudrate=self.baud_rate,
                timeout=self.timeout_seconds,
                write_timeout=self.write_timeout_seconds,
            )

        try:
            import serial  # type: ignore[import-not-found]
        except ImportError as exc:
            raise TransportError(
                "pyserial diperlukan untuk SerialTransport. Install dengan 'pip install pyserial' "
                "atau jalankan mode simulasi ('--transport mock')."
            ) from exc

        return serial.Serial(
            port=port_name,
            baudrate=self.baud_rate,
            timeout=self.timeout_seconds,
            write_timeout=self.write_timeout_seconds,
        )

    def _exchange_line(self, line: str) -> str:
        if self._conn is None:
            raise TransportDisconnectedError("Serial port is not open.")

        self._conn.write((line + "\n").encode("utf-8"))
        if hasattr(self._conn, "flush"):
            self._conn.flush()

        raw_reply = self._conn.readline()
        if not raw_reply:
            raise TransportTimeoutError(
                f"Timeout menunggu balasan dari '{self.port}' untuk perintah '{line}'."
            )

        return raw_reply.decode("utf-8", errors="replace").strip()

    def connect(self) -> None:
        self.disconnect()
        port_name = resolve_pico_port(self.configured_port, comports_fn=self._comports_fn)
        if not port_name:
            raise TransportDisconnectedError(
                "Raspberry Pi Pico tidak ditemukan! Pastikan kabel USB terhubung."
            )

        self.resolved_port = port_name
        try:
            self._conn = self._open_serial(port_name)
            if self.startup_delay_seconds > 0:
                self._sleep(self.startup_delay_seconds)
            if hasattr(self._conn, "reset_input_buffer"):
                self._conn.reset_input_buffer()

            reply = self._exchange_line("HELLO")
            if reply != self.device_id:
                self.disconnect()
                raise TransportProtocolError(
                    f"Perangkat pada '{port_name}' bukan ArcadeLED "
                    f"(terima {reply!r}, harap {self.device_id!r})."
                )
        except TransportError:
            self.disconnect()
            raise
        except Exception as exc:
            self.disconnect()
            raise TransportDisconnectedError(
                f"Gagal membuka port serial '{port_name}' ({self.baud_rate} baud): {exc}"
            ) from exc

    def disconnect(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            finally:
                self._conn = None

    def is_connected(self) -> bool:
        if self._conn is None:
            return False
        return bool(getattr(self._conn, "is_open", True))

    def send_command(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        wire_pairs = build_wire_commands(payload)
        last_error: Optional[Exception] = None

        for attempt in range(self.reconnect_attempts):
            try:
                if not self.is_connected():
                    self.connect()
                    if attempt > 0:
                        self.reconnect_count += 1

                exchanges: List[Dict[str, str]] = []
                for line, expected in wire_pairs:
                    target_expected = self.device_id if line == "HELLO" else expected
                    reply = self._exchange_line(line)
                    exchanges.append({"sent": line, "reply": reply})
                    if reply != target_expected:
                        raise TransportProtocolError(
                            f"Balasan Pico tidak sesuai untuk '{line}': "
                            f"terima {reply!r}, harap {target_expected!r}."
                        )

                return {
                    "status": "ok",
                    "port": self.port,
                    "device_id": self.device_id,
                    "exchanges": exchanges,
                }

            except TransportProtocolError:
                raise
            except (TransportDisconnectedError, TransportTimeoutError) as exc:
                last_error = exc
                self.disconnect()
                if attempt + 1 < self.reconnect_attempts:
                    if self.reconnect_delay_seconds > 0:
                        self._sleep(self.reconnect_delay_seconds)
                    self.reconnect_count += 1
            except Exception as exc:
                last_error = TransportDisconnectedError(
                    f"Serial I/O error pada '{self.port}': {exc}"
                )
                self.disconnect()
                if attempt + 1 < self.reconnect_attempts:
                    if self.reconnect_delay_seconds > 0:
                        self._sleep(self.reconnect_delay_seconds)
                    self.reconnect_count += 1

        raise last_error or TransportDisconnectedError(f"Gagal mengirim perintah ke '{self.port}'.")
