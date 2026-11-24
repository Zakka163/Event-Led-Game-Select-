"""Real-time event logger for Phase 1 observation and diagnostics.

Writes both the human-readable Phase 1 block log format and optional
newline-delimited JSON (JSONL) records for machine inspection.
"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Optional, TextIO

from host.core.event_model import GameEvent


class EventLogger:
    """Logs normalized game selection events in real time."""

    def __init__(
        self,
        log_file: Optional[Path] = None,
        jsonl_file: Optional[Path] = None,
        console: bool = True,
        stream: Optional[TextIO] = None,
    ) -> None:
        self.log_file = Path(log_file) if log_file else None
        self.jsonl_file = Path(jsonl_file) if jsonl_file else None
        self.console = console
        self.stream = stream or sys.stdout

        if self.log_file:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
        if self.jsonl_file:
            self.jsonl_file.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def format_event_lines(event: GameEvent) -> str:
        """Format a GameEvent in a clean, readable multi-line log block."""
        ts = event.formatted_log_timestamp
        lines = [
            f"[{ts}] ----------------------------------------",
            f"  Platform : {event.platform.upper()} | System: {event.system.upper()} | Event: {event.event.upper()}",
            f"  Game     : {event.game_name}",
            f"  ROM      : {event.rom_path or '(not provided)'}",
        ]
        return "\n".join(lines) + "\n"

    def log_event(self, event: GameEvent, note: Optional[str] = None) -> str:
        """Write formatted event output to configured sinks and return formatted text."""
        block = self.format_event_lines(event)
        if note:
            for line in note.splitlines():
                block += f"  {line}\n"

        if self.console:
            self.stream.write(block + "\n")
            self.stream.flush()

        if self.log_file:
            with self.log_file.open("a", encoding="utf-8") as fh:
                fh.write(block + "\n")

        if self.jsonl_file:
            with self.jsonl_file.open("a", encoding="utf-8") as fh:
                fh.write(event.to_json() + "\n")

        return block
