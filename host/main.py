#!/usr/bin/env python3
"""ArcadeLED Host CLI, Hardware Test Tool, and Local Event Daemon.

Usage examples:
  python host/main.py test-pico
  python host/main.py simulate
  python host/main.py emit --platform batocera --system mame \\
      --rom-path "/userdata/roms/mame/sf2.zip" --game-name "Street Fighter II"
  python host/main.py daemon
  python host/main.py stdin
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import signal
import socket
import socketserver
import sys
import threading
import time
from typing import Any, Dict, Optional

# Ensure project root is importable regardless of invocation directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from host.core.event_logger import EventLogger
from host.core.event_model import EventValidationError, GameEvent
from host.core.event_processor import EventProcessor
from host.core.game_resolver import GameResolver
from host.core.profile_manager import ProfileManager
from host.transports.base_transport import BaseTransport, TransportError
from host.transports.mock_transport import MockTransport
from host.transports.serial_transport import DEFAULT_DEVICE_ID, SerialTransport


DEFAULT_SETTINGS_PATH = PROJECT_ROOT / "host" / "config" / "settings.json"


def _resolve_path(raw_path: Optional[str]) -> Optional[Path]:
    if not raw_path:
        return None
    p = Path(raw_path)
    if p.is_absolute():
        return p
    return PROJECT_ROOT / p


def load_settings(settings_path: Path = DEFAULT_SETTINGS_PATH) -> Dict[str, Any]:
    with Path(settings_path).open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"Settings file {settings_path} must contain a JSON object.")
    return data


def build_transport(
    settings: Dict[str, Any],
    transport_override: Optional[str] = None,
    port_override: Optional[str] = None,
) -> BaseTransport:
    kind = (transport_override or settings.get("transport", "serial")).strip().lower()
    serial_cfg = settings.get("serial", {})

    if kind == "serial":
        return SerialTransport(
            port=str(port_override or serial_cfg.get("port", "auto")),
            baud_rate=int(serial_cfg.get("baud_rate", 115200)),
            device_id=str(serial_cfg.get("device_id", DEFAULT_DEVICE_ID)),
            startup_delay_seconds=float(serial_cfg.get("startup_delay_seconds", 2.0)),
            timeout_seconds=float(serial_cfg.get("timeout_seconds", 2.0)),
            write_timeout_seconds=float(serial_cfg.get("write_timeout_seconds", 2.0)),
            reconnect_attempts=int(serial_cfg.get("reconnect_attempts", 3)),
            reconnect_delay_seconds=float(serial_cfg.get("reconnect_delay_seconds", 0.5)),
        )

    if kind == "mock":
        return MockTransport(
            port="MOCK_SERIAL",
            baud_rate=int(serial_cfg.get("baud_rate", 115200)),
            device_id=str(serial_cfg.get("device_id", DEFAULT_DEVICE_ID)),
            auto_reconnect=True,
            reconnect_attempts=int(serial_cfg.get("reconnect_attempts", 3)),
        )

    raise ValueError(f"Unsupported transport type '{kind}'. Expected 'mock' or 'serial'.")


def build_processor(
    settings: Dict[str, Any],
    transport_override: Optional[str] = None,
    port_override: Optional[str] = None,
    log_only: bool = False,
    console_override: Optional[bool] = None,
) -> EventProcessor:
    paths_cfg = settings.get("paths", {})
    games_path = _resolve_path(paths_cfg.get("games_config", "host/config/games.json"))
    if games_path is None or not games_path.exists():
        raise FileNotFoundError(f"Games config not found: {games_path}")

    log_cfg = settings.get("logging", {})
    event_logger = EventLogger(
        log_file=_resolve_path(log_cfg.get("log_file")),
        jsonl_file=_resolve_path(log_cfg.get("jsonl_file")),
        console=bool(log_cfg.get("console", True)) if console_override is None else console_override,
    )

    resolver = GameResolver.from_file(games_path)
    profile_manager = ProfileManager.from_file(games_path)

    send_enabled = bool(settings.get("send_to_transport", True)) and not log_only
    transport: Optional[BaseTransport] = None
    if send_enabled:
        transport = build_transport(
            settings,
            transport_override=transport_override,
            port_override=port_override,
        )

    hw_buttons = int(settings.get("hardware", {}).get("buttons", 4))
    return EventProcessor(
        game_resolver=resolver,
        profile_manager=profile_manager,
        event_logger=event_logger,
        transport=transport,
        send_to_transport=send_enabled,
        hw_buttons=hw_buttons,
    )


def try_forward_to_daemon(event: GameEvent, host: str, port: int, timeout: float = 0.15) -> bool:
    """Attempt fast non-blocking-style forward to local ArcadeLED daemon."""
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall((event.to_json() + "\n").encode("utf-8"))
            reply = sock.recv(256).decode("utf-8", errors="replace").strip()
            return reply.startswith('{"status":"ok"') or reply.startswith('{"status": "ok"')
    except OSError:
        return False


class _DebouncedEventDispatcher:
    """Coalesces rapid scroll events so only the latest highlighted game executes."""

    def __init__(self, processor: EventProcessor, debounce_ms: int = 100) -> None:
        self._processor = processor
        self._debounce_seconds = max(0.0, debounce_ms / 1000.0)
        self._lock = threading.Lock()
        self._timer: Optional[threading.Timer] = None
        self._pending_event: Optional[GameEvent] = None

    def submit(self, event: GameEvent) -> None:
        if self._debounce_seconds <= 0.0:
            with self._lock:
                self._processor.process(event)
            return

        with self._lock:
            self._pending_event = event
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._debounce_seconds, self._flush)
            self._timer.daemon = True
            self._timer.start()

    def _flush(self) -> None:
        with self._lock:
            event = self._pending_event
            self._pending_event = None
            self._timer = None
            if event is not None:
                self._processor.process(event)

    def shutdown(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            if self._pending_event is not None:
                event = self._pending_event
                self._pending_event = None
                self._processor.process(event)


def run_daemon(
    processor: EventProcessor,
    host: str,
    port: int,
    debounce_ms: int,
) -> int:
    dispatcher = _DebouncedEventDispatcher(processor, debounce_ms=debounce_ms)

    class _EventTCPHandler(socketserver.StreamRequestHandler):
        def handle(self) -> None:
            for raw_line in self.rfile:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    event = GameEvent.from_json(line)
                    dispatcher.submit(event)
                    resp = {"status": "ok", "queued": True, "game_name": event.game_name}
                except EventValidationError as exc:
                    resp = {"status": "error", "message": str(exc)}
                self.wfile.write((json.dumps(resp) + "\n").encode("utf-8"))
                self.wfile.flush()

    class _ReusableTCPServer(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    server = _ReusableTCPServer((host, port), _EventTCPHandler)

    def _handle_signal(_signum: int, _frame: Any) -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, _handle_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_signal)

    print(
        f"[ArcadeLED] Daemon listening on {host}:{port} "
        f"(debounce={debounce_ms}ms, transport={'enabled' if processor.send_to_transport else 'log-only'})",
        flush=True,
    )

    try:
        server.serve_forever()
    finally:
        dispatcher.shutdown()
        server.server_close()
        if processor.transport is not None:
            processor.transport.disconnect()
        print("[ArcadeLED] Daemon stopped cleanly.", flush=True)

    return 0


def run_test_pico(
    settings: Dict[str, Any],
    transport_override: Optional[str] = None,
    port_override: Optional[str] = None,
) -> int:
    """Run the verified hardware LED test sequence against ARCADELED_V1."""
    transport = build_transport(
        settings,
        transport_override=transport_override or "serial",
        port_override=port_override,
    )
    sequence = [
        ("LED1 ON", 1.0),
        ("LED1 OFF", 1.0),
        ("ALL ON", 2.0),
        ("ALL OFF", 0.0),
    ]
    try:
        transport.connect()
        print(f"ArcadeLED terhubung pada {getattr(transport, 'port', 'unknown')}", flush=True)
        for line, delay in sequence:
            resp = transport.send_command({"command": "raw", "line": line, "expected": "OK"})
            reply = resp["exchanges"][0]["reply"] if resp.get("exchanges") else "OK"
            print(f"[PC] {line} -> [PICO] {reply}", flush=True)
            if delay > 0:
                time.sleep(delay)
        return 0
    except TransportError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        if sys.platform.startswith("linux"):
            print("Periksa izin dialout (sudo usermod -aG dialout $USER).", file=sys.stderr)
        else:
            print("Pastikan Serial Monitor Arduino IDE ditutup.", file=sys.stderr)
        return 1
    finally:
        transport.disconnect()
        print("Koneksi ditutup.", flush=True)


def run_simulation(settings: Dict[str, Any], delay_seconds: float = 0.25) -> int:
    """Run a hardware-free end-to-end simulation using ARCADELED_V1 MockTransport."""
    processor = build_processor(settings, transport_override="mock", log_only=False)
    assert isinstance(processor.transport, MockTransport)

    print("=== ArcadeLED Hardware-Free Simulation (ARCADELED_V1) ===\n", flush=True)

    demo_events = [
        (
            "1) Highlight Street Fighter II (Batocera -> ALL ON)",
            {
                "event": "game_selected",
                "platform": "batocera",
                "system": "mame",
                "rom_path": "/userdata/roms/mame/sf2.zip",
                "game_name": "Street Fighter II",
            },
        ),
        (
            "2) Scroll to Metal Slug (Batocera -> A, B, X ON, Y OFF)",
            {
                "event": "game_selected",
                "platform": "batocera",
                "system": "mame",
                "rom_path": "/userdata/roms/mame/mslug.zip",
                "game_name": "Metal Slug",
            },
        ),
        (
            "3) Re-select Metal Slug (should deduplicate serial command)",
            {
                "event": "game_selected",
                "platform": "batocera",
                "system": "mame",
                "rom_path": "/userdata/roms/mame/mslug.zip",
                "game_name": "Metal Slug",
            },
        ),
        (
            "4) Special characters in ROM path + fallback by game name",
            {
                "event": "game_selected",
                "platform": "batocera",
                "system": "mame",
                "rom_path": "/userdata/roms/mame/Street Fighter II' - Champion Edition (USA) [Rev 1].zip",
                "game_name": "Street Fighter II' - Champion Edition",
            },
        ),
        (
            "5) Unmapped game -> fallback to default profile (A, B ON)",
            {
                "event": "game_selected",
                "platform": "emuelec",
                "system": "snes",
                "rom_path": "/storage/roms/snes/Chrono Trigger (USA).sfc",
                "game_name": "Chrono Trigger",
            },
        ),
        (
            "6) Incomplete event (missing system & game_name, inferred from ROM path)",
            {
                "event": "game_selected",
                "platform": "batocera",
                "system": "",
                "rom_path": "/userdata/roms/neogeo/kof98.zip",
                "game_name": "",
            },
        ),
    ]

    for label, payload in demo_events:
        print(f"--- {label} ---", flush=True)
        result = processor.process(payload)
        lines = [ex["sent"] for ex in (result.transport_response or {}).get("exchanges", [])]
        print(
            f"    Resolved: match={result.resolution.match_type}, "
            f"profile={result.profile.profile_name}, "
            f"sent={result.transport_sent}, deduplicated={result.deduplicated}, "
            f"wire={lines}\n",
            flush=True,
        )
        if delay_seconds > 0:
            time.sleep(delay_seconds)

    print("--- 7) Simulated USB Serial Disconnect & Auto-Reconnect ---", flush=True)
    processor.transport.simulate_write_failures(1)
    result = processor.process(
        {
            "event": "game_selected",
            "platform": "batocera",
            "system": "mame",
            "rom_path": "/userdata/roms/mame/galaga.zip",
            "game_name": "Galaga",
        }
    )
    print(
        f"    Recovered after disconnect: sent={result.transport_sent}, "
        f"reconnects={processor.transport.reconnect_count}, "
        f"leds={processor.transport.current_led_state}\n",
        flush=True,
    )

    print(
        f"=== Simulation complete: {len(processor.transport.command_history)} updates "
        f"({len(processor.transport.sent_frames)} serial lines) sent to MockTransport ===",
        flush=True,
    )
    processor.transport.disconnect()
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ArcadeLED Host Controller (ARCADELED_V1)")
    parser.add_argument(
        "--settings",
        type=Path,
        default=DEFAULT_SETTINGS_PATH,
        help="Path to settings.json (default: host/config/settings.json)",
    )
    parser.add_argument(
        "--transport",
        choices=["mock", "serial"],
        default=None,
        help="Override transport configured in settings.json",
    )
    parser.add_argument(
        "--serial-port",
        dest="serial_port",
        default=None,
        help="Override serial port (e.g. COM4, /dev/ttyACM0, or auto)",
    )
    parser.add_argument(
        "--log-only",
        action="store_true",
        help="Only log normalized events without dispatching commands to transport",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # test-pico
    subparsers.add_parser("test-pico", help="Run hardware LED self-test on connected Pico")

    # emit
    emit_p = subparsers.add_parser("emit", help="Emit a single game selection event")
    emit_p.add_argument("--platform", default="unknown", help="Platform name (batocera, emuelec, mock)")
    emit_p.add_argument("--system", default="", help="EmulationStation system shortname")
    emit_p.add_argument("--rom-path", default="", help="Full or relative ROM path")
    emit_p.add_argument("--game-name", default="", help="Display name of the highlighted game")
    emit_p.add_argument("--timestamp", default="", help="Optional ISO-8601 timestamp")
    emit_p.add_argument("--json", dest="raw_json", default="", help="Raw JSON event string instead of flags")
    emit_p.add_argument(
        "--forward-to-daemon",
        action="store_true",
        help="Forward event to running local daemon if reachable; fallback to local processing",
    )

    # daemon
    daemon_p = subparsers.add_parser("daemon", help="Run persistent local event listener daemon")
    daemon_p.add_argument("--host", default=None, help="Bind host (default from settings.json)")
    daemon_p.add_argument("--port", type=int, default=None, help="Bind TCP port (default from settings.json)")
    daemon_p.add_argument("--debounce-ms", type=int, default=None, help="Scroll debounce window in ms")

    # stdin
    subparsers.add_parser("stdin", help="Read newline-delimited JSON events from stdin")

    # simulate
    sim_p = subparsers.add_parser("simulate", help="Run hardware-free mock event simulation")
    sim_p.add_argument("--delay", type=float, default=0.1, help="Delay in seconds between simulated events")

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    settings = load_settings(args.settings)

    if args.command == "test-pico":
        return run_test_pico(
            settings,
            transport_override=args.transport,
            port_override=args.serial_port,
        )

    if args.command == "simulate":
        return run_simulation(settings, delay_seconds=args.delay)

    if args.command == "emit":
        try:
            if args.raw_json:
                event = GameEvent.from_json(args.raw_json)
            else:
                event = GameEvent.from_adapter_args(
                    platform=args.platform,
                    system=args.system,
                    rom_path=args.rom_path,
                    game_name=args.game_name,
                    timestamp=args.timestamp,
                )
        except EventValidationError as exc:
            print(f"[ArcadeLED] Invalid event: {exc}", file=sys.stderr)
            return 2

        daemon_cfg = settings.get("daemon", {})
        if args.forward_to_daemon:
            host = str(daemon_cfg.get("host", "127.0.0.1"))
            port = int(daemon_cfg.get("port", 19876))
            if try_forward_to_daemon(event, host=host, port=port):
                return 0

        processor = build_processor(
            settings,
            transport_override=args.transport,
            port_override=args.serial_port,
            log_only=args.log_only,
        )
        try:
            result = processor.process(event)
            if result.transport_error:
                print(f"[ArcadeLED] Transport warning: {result.transport_error}", file=sys.stderr)
                return 1
            return 0
        finally:
            if processor.transport is not None:
                processor.transport.disconnect()

    if args.command == "daemon":
        daemon_cfg = settings.get("daemon", {})
        host = args.host or str(daemon_cfg.get("host", "127.0.0.1"))
        port = args.port if args.port is not None else int(daemon_cfg.get("port", 19876))
        debounce_ms = (
            args.debounce_ms
            if args.debounce_ms is not None
            else int(daemon_cfg.get("debounce_ms", 100))
        )
        processor = build_processor(
            settings,
            transport_override=args.transport,
            port_override=args.serial_port,
            log_only=args.log_only,
        )
        return run_daemon(processor, host=host, port=port, debounce_ms=debounce_ms)

    if args.command == "stdin":
        processor = build_processor(
            settings,
            transport_override=args.transport,
            port_override=args.serial_port,
            log_only=args.log_only,
        )
        try:
            for raw_line in sys.stdin:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    processor.process(line)
                except EventValidationError as exc:
                    print(f"[ArcadeLED] Skipped invalid line: {exc}", file=sys.stderr)
            return 0
        finally:
            if processor.transport is not None:
                processor.transport.disconnect()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
