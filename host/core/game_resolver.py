"""Game matching against games.json."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Dict, Mapping, Optional

from host.core.event_model import GameEvent


_NORMALIZE_NAME_RE = re.compile(r"[^a-z0-9]+")


def _normalize_title(title: str) -> str:
    """Normalize a game title for case- and punctuation-insensitive fallback matching."""
    return _NORMALIZE_NAME_RE.sub(" ", title.lower()).strip()


def _normalize_game_key(raw_key: str) -> str:
    """Normalize configured game keys like 'mame/sf2.zip' or full paths."""
    cleaned = raw_key.replace("\\", "/").strip().lower()
    return cleaned


@dataclass(frozen=True)
class ResolutionResult:
    """Outcome of resolving a GameEvent against games.json."""

    matched: bool
    match_type: str  # exact_rom | stem_rom | game_name | system_fallback | default
    profile_name: str
    game_key: Optional[str] = None
    resolved_game_name: str = ""
    led_overrides: Dict[str, Any] = field(default_factory=dict)


class GameResolver:
    """Resolves a GameEvent to a game configuration entry or fallback profile."""

    def __init__(self, config: Mapping[str, Any]) -> None:
        self._default_profile: str = str(config.get("default_profile", "default")).strip() or "default"
        self._systems: Dict[str, str] = {}
        self._by_exact_key: Dict[str, tuple[str, Mapping[str, Any]]] = {}
        self._by_stem_key: Dict[str, tuple[str, Mapping[str, Any]]] = {}
        self._by_rom_filename: Dict[str, tuple[str, Mapping[str, Any]]] = {}
        self._by_game_name: Dict[str, tuple[str, Mapping[str, Any]]] = {}
        self._load_indexes(config)

    @classmethod
    def from_file(cls, config_path: Path) -> "GameResolver":
        with Path(config_path).open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise ValueError(f"Invalid games config root in {config_path}: expected JSON object.")
        return cls(data)

    def _load_indexes(self, config: Mapping[str, Any]) -> None:
        raw_systems = config.get("systems", {})
        if isinstance(raw_systems, Mapping):
            for sys_name, profile_name in raw_systems.items():
                if isinstance(sys_name, str) and isinstance(profile_name, str):
                    self._systems[sys_name.strip().lower()] = profile_name.strip()

        raw_games = config.get("games", {})
        if not isinstance(raw_games, Mapping):
            return

        for raw_key, entry in raw_games.items():
            if not isinstance(raw_key, str) or not isinstance(entry, Mapping):
                continue

            norm_key = _normalize_game_key(raw_key)
            self._by_exact_key[norm_key] = (raw_key, entry)

            # Index "<system>/<rom_stem>" so extension differences (e.g. .zip vs .7z) can still match.
            key_path = PurePosixPath(norm_key)
            if len(key_path.parts) >= 2:
                sys_part = key_path.parts[0]
                rom_file = key_path.name
                rom_stem = key_path.stem
                self._by_stem_key.setdefault(f"{sys_part}/{rom_stem}", (raw_key, entry))
                self._by_rom_filename.setdefault(rom_file, (raw_key, entry))
            else:
                self._by_rom_filename.setdefault(key_path.name, (raw_key, entry))

            primary_name = entry.get("name")
            if isinstance(primary_name, str) and primary_name.strip():
                self._by_game_name.setdefault(_normalize_title(primary_name), (raw_key, entry))

            aliases = entry.get("aliases", [])
            if isinstance(aliases, list):
                for alias in aliases:
                    if isinstance(alias, str) and alias.strip():
                        self._by_game_name.setdefault(_normalize_title(alias), (raw_key, entry))

    def _build_match_result(
        self,
        match_type: str,
        game_key: str,
        entry: Mapping[str, Any],
        fallback_name: str,
    ) -> ResolutionResult:
        profile_name = str(entry.get("profile") or self._default_profile).strip()
        raw_leds = entry.get("leds", {})
        led_overrides: Dict[str, Any] = {}
        if isinstance(raw_leds, Mapping):
            for led_name, spec in raw_leds.items():
                if not isinstance(led_name, str) or not led_name.strip():
                    continue
                if isinstance(spec, Mapping):
                    led_overrides[led_name.strip()] = dict(spec)
                elif isinstance(spec, (bool, str, int, float)):
                    led_overrides[led_name.strip()] = spec

        resolved_name = str(entry.get("name") or fallback_name).strip()
        return ResolutionResult(
            matched=True,
            match_type=match_type,
            profile_name=profile_name,
            game_key=game_key,
            resolved_game_name=resolved_name,
            led_overrides=led_overrides,
        )

    def resolve(self, event: GameEvent) -> ResolutionResult:
        """Resolve an event using prioritized matching with graceful fallback."""
        # 1. Exact "<system>/<rom_filename>" match
        if event.system_rom_key and event.system_rom_key in self._by_exact_key:
            game_key, entry = self._by_exact_key[event.system_rom_key]
            return self._build_match_result("exact_rom", game_key, entry, event.game_name)

        # 1b. Exact full ROM path match (in case user mapped full paths in games.json)
        norm_rom_path = _normalize_game_key(event.rom_path)
        if norm_rom_path and norm_rom_path in self._by_exact_key:
            game_key, entry = self._by_exact_key[norm_rom_path]
            return self._build_match_result("exact_rom", game_key, entry, event.game_name)

        # 2. "<system>/<rom_stem>" match (ignoring archive/rom extension)
        if event.system and event.rom_stem:
            stem_key = f"{event.system}/{event.rom_stem}".lower()
            if stem_key in self._by_stem_key:
                game_key, entry = self._by_stem_key[stem_key]
                return self._build_match_result("stem_rom", game_key, entry, event.game_name)

        # 3. Fallback by normalized game display name (or alias)
        norm_title = _normalize_title(event.game_name)
        if norm_title and norm_title in self._by_game_name:
            game_key, entry = self._by_game_name[norm_title]
            return self._build_match_result("game_name", game_key, entry, event.game_name)

        # 4. Fallback by ROM filename alone when system is unknown
        if event.system == "unknown" and event.rom_filename:
            rom_lower = event.rom_filename.lower()
            if rom_lower in self._by_rom_filename:
                game_key, entry = self._by_rom_filename[rom_lower]
                return self._build_match_result("stem_rom", game_key, entry, event.game_name)

        # 5. System-level default profile fallback
        if event.system in self._systems:
            return ResolutionResult(
                matched=False,
                match_type="system_fallback",
                profile_name=self._systems[event.system],
                game_key=None,
                resolved_game_name=event.game_name,
                led_overrides={},
            )

        # 6. Global default profile fallback
        return ResolutionResult(
            matched=False,
            match_type="default",
            profile_name=self._default_profile,
            game_key=None,
            resolved_game_name=event.game_name,
            led_overrides={},
        )
