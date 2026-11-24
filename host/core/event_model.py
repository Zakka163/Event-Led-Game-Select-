"""Standardized event model, validation, and normalization for ArcadeLED.

All platform adapters (Batocera, EmuELEC, Mock/CLI) must emit events normalized
into `GameEvent` so the core engine remains platform-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import PurePosixPath
import re
from typing import Any, Dict, Mapping, Optional


SUPPORTED_EVENTS = frozenset({"game_selected"})
KNOWN_PLATFORMS = frozenset({"batocera", "emuelec", "mock", "unknown"})
_ISO_FORMAT = "%Y-%m-%dT%H:%M:%S"
_ROM_SYSTEM_RE = re.compile(r"(?:^|/)roms/([^/]+)/", re.IGNORECASE)


class EventValidationError(ValueError):
    """Raised when an incoming event payload is malformed or unusable."""


def _clean_text(value: Any) -> str:
    """Convert raw field into a trimmed string without control characters."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    # Strip leading/trailing whitespace and embedded CR/LF to preserve single-line safety.
    return value.replace("\r", " ").replace("\n", " ").strip()


def _normalize_event_name(raw_event: Any) -> str:
    cleaned = _clean_text(raw_event).lower().replace("-", "_").replace(" ", "_")
    if not cleaned:
        return "game_selected"
    if cleaned not in SUPPORTED_EVENTS:
        raise EventValidationError(
            f"Unsupported event type '{raw_event}'. Supported: {sorted(SUPPORTED_EVENTS)}"
        )
    return cleaned


def _normalize_platform(raw_platform: Any) -> str:
    cleaned = _clean_text(raw_platform).lower()
    if not cleaned:
        return "unknown"
    return cleaned


def _normalize_rom_path(raw_path: Any) -> str:
    cleaned = _clean_text(raw_path)
    if not cleaned:
        return ""
    # Normalize Windows separators only if the path clearly looks like a Windows path
    # (drive letter or backslashes without forward slashes), keeping POSIX filenames intact.
    if "\\" in cleaned and "/" not in cleaned:
        cleaned = cleaned.replace("\\", "/")
    return cleaned


def _extract_rom_filename(rom_path: str) -> str:
    if not rom_path:
        return ""
    return PurePosixPath(rom_path).name


def _extract_rom_stem(rom_path: str) -> str:
    filename = _extract_rom_filename(rom_path)
    if not filename:
        return ""
    return PurePosixPath(filename).stem


def _infer_system_from_rom_path(rom_path: str) -> str:
    if not rom_path:
        return ""
    match = _ROM_SYSTEM_RE.search(rom_path)
    if match:
        return match.group(1).strip().lower()
    return ""


def _normalize_timestamp(raw_timestamp: Any) -> str:
    cleaned = _clean_text(raw_timestamp)
    if not cleaned:
        return datetime.now().strftime(_ISO_FORMAT)

    candidate = cleaned.replace(" ", "T")
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(candidate)
        return parsed.strftime(_ISO_FORMAT)
    except ValueError:
        return datetime.now().strftime(_ISO_FORMAT)


@dataclass(frozen=True)
class GameEvent:
    """Normalized representation of a frontend game selection event."""

    event: str
    platform: str
    system: str
    rom_path: str
    game_name: str
    timestamp: str

    @property
    def rom_filename(self) -> str:
        """Return the base ROM filename (e.g., 'sf2.zip')."""
        return _extract_rom_filename(self.rom_path)

    @property
    def rom_stem(self) -> str:
        """Return the ROM filename without its final extension (e.g., 'sf2')."""
        return _extract_rom_stem(self.rom_path)

    @property
    def system_rom_key(self) -> str:
        """Return normalized '<system>/<rom_filename>' lookup key."""
        if self.system and self.rom_filename:
            return f"{self.system}/{self.rom_filename}".lower()
        return ""

    @property
    def formatted_log_timestamp(self) -> str:
        """Return timestamp formatted for Phase 1 human-readable logs."""
        return self.timestamp.replace("T", " ")

    def to_dict(self) -> Dict[str, str]:
        return {
            "event": self.event,
            "platform": self.platform,
            "system": self.system,
            "rom_path": self.rom_path,
            "game_name": self.game_name,
            "timestamp": self.timestamp,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "GameEvent":
        """Validate and normalize a raw dictionary payload into a GameEvent."""
        if not isinstance(payload, Mapping):
            raise EventValidationError("Event payload must be a JSON object / mapping.")

        event = _normalize_event_name(payload.get("event"))
        platform = _normalize_platform(payload.get("platform"))
        rom_path = _normalize_rom_path(payload.get("rom_path"))
        game_name = _clean_text(payload.get("game_name"))
        system = _clean_text(payload.get("system")).lower()

        if not rom_path and not game_name:
            raise EventValidationError(
                "Incomplete event: at least one of 'rom_path' or 'game_name' is required."
            )

        if not system:
            system = _infer_system_from_rom_path(rom_path) or "unknown"

        if not game_name:
            game_name = _extract_rom_stem(rom_path) or _extract_rom_filename(rom_path) or "Unknown Game"

        timestamp = _normalize_timestamp(payload.get("timestamp"))

        return cls(
            event=event,
            platform=platform,
            system=system,
            rom_path=rom_path,
            game_name=game_name,
            timestamp=timestamp,
        )

    @classmethod
    def from_json(cls, raw_json: str) -> "GameEvent":
        """Parse a JSON string and normalize into a GameEvent."""
        if not isinstance(raw_json, str) or not raw_json.strip():
            raise EventValidationError("Event JSON input is empty.")
        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise EventValidationError(f"Invalid event JSON: {exc}") from exc
        return cls.from_dict(parsed)

    @classmethod
    def from_adapter_args(
        cls,
        platform: str,
        system: str = "",
        rom_path: str = "",
        game_name: str = "",
        event: str = "game_selected",
        timestamp: Optional[str] = None,
    ) -> "GameEvent":
        """Construct a normalized GameEvent from platform adapter arguments."""
        return cls.from_dict(
            {
                "event": event,
                "platform": platform,
                "system": system,
                "rom_path": rom_path,
                "game_name": game_name,
                "timestamp": timestamp or "",
            }
        )
