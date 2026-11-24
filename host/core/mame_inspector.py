"""Lightweight game control requirements inspector for ArcadeLED logs.

Determines how many buttons and what control type a game *actually* requires
(independent of physical cabinet LED limits), using:
1. Local cache / overrides (`host/config/mame_controls_cache.json`)
2. Live `mame -listxml <rom_stem>` (when MAME binary is available, cached to disk)
3. System-level defaults for non-arcade console systems
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import subprocess
from typing import Dict, Optional
import xml.etree.ElementTree as ET

ARCADE_SYSTEMS = frozenset({"mame", "fbneo", "neogeo", "cps1", "cps2", "cps3", "arcade"})

SYSTEM_DEFAULT_CONTROLS: Dict[str, tuple[int, str, int]] = {
    # system: (buttons, control_summary, players)
    "nes": (2, "dpad", 2),
    "snes": (6, "dpad", 2),
    "megadrive": (3, "dpad", 2),
    "genesis": (3, "dpad", 2),
    "gba": (4, "dpad", 1),
    "gb": (2, "dpad", 1),
    "gbc": (2, "dpad", 1),
    "psx": (8, "dpad/analog", 2),
    "ps2": (10, "analog", 2),
    "psp": (6, "analog/dpad", 1),
    "dreamcast": (6, "analog", 4),
    "n64": (8, "analog", 4),
}

DEFAULT_MAME_BINARIES = ("/usr/bin/mame/mame", "mame", "mame64")


@dataclass(frozen=True)
class GameControlRequirement:
    """Actual control requirements of a game (independent of cabinet hardware)."""

    buttons: Optional[int]
    control_summary: str
    players: Optional[int]
    source: str


def _find_mame_binary() -> Optional[str]:
    for candidate in DEFAULT_MAME_BINARIES:
        if Path(candidate).is_file():
            return candidate
        found = shutil.which(candidate)
        if found:
            return found
    return None


class GameControlInspector:
    """Resolves actual game button & control requirements with disk caching."""

    def __init__(self, cache_path: Optional[Path] = None) -> None:
        self.cache_path = cache_path or (
            Path(__file__).resolve().parents[1] / "config" / "mame_controls_cache.json"
        )
        self._cache: Dict[str, Dict[str, object]] = self._load_cache()
        self._mame_bin: Optional[str] = _find_mame_binary()

    def _load_cache(self) -> Dict[str, Dict[str, object]]:
        if not self.cache_path.exists():
            return {}
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_cache(self) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(
                json.dumps(self._cache, indent=2, sort_keys=True), encoding="utf-8"
            )
        except OSError:
            pass

    def inspect(
        self, system: str, rom_path: str, allow_live_query: bool = True
    ) -> GameControlRequirement:
        """Return actual button/control requirements for the given system & ROM."""
        sys_key = (system or "").strip().lower()
        rom_stem = Path(rom_path.replace("\\", "/")).stem.lower() if rom_path else ""

        if rom_stem and rom_stem in self._cache:
            entry = self._cache[rom_stem]
            return GameControlRequirement(
                buttons=int(entry["buttons"]) if entry.get("buttons") is not None else None,
                control_summary=str(entry.get("control", "unknown")),
                players=int(entry["players"]) if entry.get("players") is not None else None,
                source=str(entry.get("source", "cache")),
            )

        if allow_live_query and sys_key in ARCADE_SYSTEMS and rom_stem and self._mame_bin:
            req = self._query_mame_xml(rom_stem)
            if req is not None:
                self._cache[rom_stem] = {
                    "buttons": req.buttons,
                    "control": req.control_summary,
                    "players": req.players,
                    "source": req.source,
                }
                self._save_cache()
                return req

        if sys_key in SYSTEM_DEFAULT_CONTROLS:
            btns, ctrl, players = SYSTEM_DEFAULT_CONTROLS[sys_key]
            return GameControlRequirement(
                buttons=btns,
                control_summary=ctrl,
                players=players,
                source="system_default",
            )

        return GameControlRequirement(
            buttons=None,
            control_summary="unknown",
            players=None,
            source="unknown",
        )

    def _query_mame_xml(self, rom_stem: str) -> Optional[GameControlRequirement]:
        if not self._mame_bin:
            return None
        try:
            out = subprocess.check_output(
                [self._mame_bin, "-listxml", rom_stem],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=4.0,
            )
            root = ET.fromstring(out)
        except (subprocess.SubprocessError, OSError, ET.ParseError):
            return None

        for machine in root.findall("machine"):
            if machine.get("name") != rom_stem:
                continue
            inp = machine.find("input")
            if inp is None:
                return None

            players = int(inp.get("players", "1"))
            controls = inp.findall("control")
            if not controls:
                return GameControlRequirement(
                    buttons=0,
                    control_summary="none",
                    players=players,
                    source="mame_xml",
                )

            p1 = controls[0]
            ctype = p1.get("type", "unknown")
            ways = p1.get("ways")
            ctrl_str = f"{ctype}({ways}w)" if ways else ctype
            buttons = max(int(c.get("buttons", "0")) for c in controls)
            return GameControlRequirement(
                buttons=buttons,
                control_summary=ctrl_str,
                players=players,
                source="mame_xml",
            )

        return None

