"""Abstract transport interface and exceptions for ArcadeLED host <-> Pico I/O."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class TransportError(Exception):
    """Base exception for all transport failures."""


class TransportDisconnectedError(TransportError):
    """Raised when the transport is disconnected and cannot send data."""


class TransportTimeoutError(TransportError):
    """Raised when the controller does not reply before the configured timeout."""


class TransportProtocolError(TransportError):
    """Raised when an invalid or unexpected response is received from the controller."""


class BaseTransport(ABC):
    """Common interface implemented by SerialTransport and MockTransport."""

    @abstractmethod
    def connect(self) -> None:
        """Open connection to the LED controller and verify device identity."""

    @abstractmethod
    def disconnect(self) -> None:
        """Close connection cleanly."""

    @abstractmethod
    def is_connected(self) -> bool:
        """Return True if transport currently has an active connection."""

    @abstractmethod
    def send_command(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Send a command payload and return a structured result dict."""

    def ping(self) -> Dict[str, Any]:
        """Send a protocol handshake/health-check (`HELLO`) to the controller."""
        return self.send_command({"command": "ping"})
