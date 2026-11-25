"""LED profile loader and serial command builder."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from host.core.game_resolver import ResolutionResult

VALID_LED_IDS = tuple(f"LED{i}" for i in range(1, 7))


@dataclass(frozen=True)
class LedState:
    """Normalized digital state for a single arcade button LED."""

    state: bool

    def to_action(self) -> str:
        return "ON" if self.state else "OFF"


@dataclass(frozen=True)
class ResolvedProfile:
    """Final merged 4-LED profile ready to be dispatched to ARCADELED_V1."""

    profile_name: str
    leds: Dict[str, LedState]
    signature: str
    used_default_fallback: bool = False

    def to_serial_commands(self) -> List[str]:
        """Generate compact ARCADELED_V1 ASCII lines for the resolved 4-LED state."""
        ordered = {led_id: self.leds.get(led_id, LedState(False)).state for led_id in VALID_LED_IDS}
        if all(ordered.values()):
            return ["ALL ON"]
        if not any(ordered.values()):
            return ["ALL OFF"]
        return [
            f"{led_id} {'ON' if ordered[led_id] else 'OFF'}"
            for led_id in VALID_LED_IDS
        ]

    def to_serial_command(self) -> Dict[str, Any]:
        """Build structured transport payload carrying both LED map and ASCII wire lines."""
        return {
            "command": "set_leds",
            "profile": self.profile_name,
            "leds": {
                led_id: self.leds.get(led_id, LedState(False)).state
                for led_id in VALID_LED_IDS
            },
            "lines": self.to_serial_commands(),
        }


def _normalize_led_id(raw_id: str) -> Optional[str]:
    cleaned = raw_id.strip().upper().replace("_", "").replace(" ", "")
    if cleaned in VALID_LED_IDS:
        return cleaned
    if cleaned.isdigit() and 1 <= int(cleaned) <= len(VALID_LED_IDS):
        return f"LED{int(cleaned)}"
    return None


def _parse_led_state(raw_state: Any) -> bool:
    if isinstance(raw_state, bool):
        return raw_state
    if isinstance(raw_state, (int, float)):
        return raw_state != 0
    if isinstance(raw_state, str):
        normalized = raw_state.strip().lower()
        if normalized in {"on", "true", "1", "yes", "enabled"}:
            return True
        if normalized in {"off", "false", "0", "no", "disabled", ""}:
            return False
    return False


def normalize_led_map(raw_leds: Mapping[str, Any], *, complete: bool = False) -> Dict[str, LedState]:
    """Convert raw JSON LED definitions into validated `LED1..LED4` states."""
    normalized: Dict[str, LedState] = {}
    if complete:
        for led_id in VALID_LED_IDS:
            normalized[led_id] = LedState(state=False)

    for raw_id, spec in raw_leds.items():
        if not isinstance(raw_id, str) or not raw_id.strip():
            continue
        led_id = _normalize_led_id(raw_id)
        if led_id is None:
            continue

        if isinstance(spec, Mapping):
            state = _parse_led_state(spec.get("state", False))
            normalized[led_id] = LedState(state=state)
        else:
            normalized[led_id] = LedState(state=_parse_led_state(spec))

    return normalized


def compute_led_signature(leds: Mapping[str, LedState]) -> str:
    """Compute a deterministic hash of the 4-LED map for command deduplication."""
    canonical = {
        led_id: leds.get(led_id, LedState(False)).state
        for led_id in VALID_LED_IDS
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


class ProfileManager:
    """Manages reusable 4-LED profiles and builds normalized ARCADELED_V1 states."""

    def __init__(self, config: Mapping[str, Any]) -> None:
        self._default_profile_name: str = str(config.get("default_profile", "default")).strip() or "default"
        self._profiles: Dict[str, Dict[str, LedState]] = {}

        raw_profiles = config.get("profiles", {})
        if isinstance(raw_profiles, Mapping):
            for name, profile_def in raw_profiles.items():
                if not isinstance(name, str) or not isinstance(profile_def, Mapping):
                    continue
                raw_leds = profile_def.get("leds", {})
                if isinstance(raw_leds, Mapping):
                    self._profiles[name.strip()] = normalize_led_map(raw_leds, complete=True)

        if self._default_profile_name not in self._profiles:
            self._profiles[self._default_profile_name] = normalize_led_map({}, complete=True)

    @classmethod
    def from_file(cls, config_path: Path) -> "ProfileManager":
        with Path(config_path).open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise ValueError(f"Invalid games config root in {config_path}: expected JSON object.")
        return cls(data)

    @property
    def default_profile_name(self) -> str:
        return self._default_profile_name

    def list_profiles(self) -> list[str]:
        return sorted(self._profiles.keys())

    def get_profile_leds(self, profile_name: str) -> tuple[str, Dict[str, LedState], bool]:
        """Return `(effective_profile_name, led_map, used_default_fallback)`."""
        if profile_name in self._profiles:
            return profile_name, dict(self._profiles[profile_name]), False
        return (
            self._default_profile_name,
            dict(self._profiles[self._default_profile_name]),
            True,
        )

    def resolve_profile(self, resolution: ResolutionResult) -> ResolvedProfile:
        """Merge base profile with any game-specific LED overrides."""
        effective_name, merged_leds, used_fallback = self.get_profile_leds(resolution.profile_name)

        if resolution.led_overrides:
            override_map = normalize_led_map(resolution.led_overrides, complete=False)
            merged_leds.update(override_map)

        signature = compute_led_signature(merged_leds)
        return ResolvedProfile(
            profile_name=effective_name,
            leds=merged_leds,
            signature=signature,
            used_default_fallback=used_fallback,
        )
