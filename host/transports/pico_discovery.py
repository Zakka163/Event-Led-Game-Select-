"""Cross-platform Raspberry Pi Pico USB Serial discovery (Windows & Linux)."""

from __future__ import annotations

import os
from typing import Any, Callable, Iterable, Optional

RASPBERRY_PI_VID = 0x2E8A
PICO_KEYWORDS = ("pico", "rp2040", "rp2350", "raspberry", "micropython")


def find_pico_port(
    comports_fn: Optional[Callable[[], Iterable[Any]]] = None,
    by_id_dir: str = "/dev/serial/by-id",
) -> Optional[str]:
    """Detect a connected Raspberry Pi Pico port on Windows or Linux."""
    if comports_fn is None:
        try:
            import serial.tools.list_ports as list_ports  # type: ignore[import-not-found]
        except ImportError:
            list_ports = None
        ports = list_ports.comports() if list_ports is not None else []
    else:
        ports = comports_fn()

    for port in ports:
        info = " ".join(
            str(x or "")
            for x in (
                getattr(port, "description", None),
                getattr(port, "manufacturer", None),
                getattr(port, "product", None),
                getattr(port, "interface", None),
            )
        ).lower()
        hwid = str(getattr(port, "hwid", None) or "").lower()
        vid = getattr(port, "vid", None)

        if vid == RASPBERRY_PI_VID or "vid:pid=2e8a" in hwid or any(k in info for k in PICO_KEYWORDS):
            device = getattr(port, "device", None)
            if device:
                return str(device)

    # Linux fallback: check /dev/serial/by-id symlinks when USB metadata is sparse
    if by_id_dir and os.path.isdir(by_id_dir):
        for name in sorted(os.listdir(by_id_dir)):
            lower_name = name.lower()
            if any(k in lower_name for k in PICO_KEYWORDS) or "2e8a" in lower_name:
                return os.path.realpath(os.path.join(by_id_dir, name))

    return None


def resolve_pico_port(
    configured_port: Optional[str] = "auto",
    comports_fn: Optional[Callable[[], Iterable[Any]]] = None,
) -> Optional[str]:
    """Resolve port from explicit setting, PICO_PORT env var, or auto-discovery."""
    env_port = (os.getenv("PICO_PORT") or "").strip()
    if env_port:
        return env_port

    cleaned = (configured_port or "").strip()
    if cleaned and cleaned.lower() != "auto":
        return cleaned

    return find_pico_port(comports_fn=comports_fn)
