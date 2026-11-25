"""Event processing pipeline."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Dict, Mapping, Optional, Union

from host.core.event_logger import EventLogger
from host.core.event_model import GameEvent
from host.core.game_resolver import GameResolver, ResolutionResult
from host.core.mame_inspector import GameControlInspector, GameControlRequirement
from host.core.profile_manager import ProfileManager, ResolvedProfile
from host.transports.base_transport import BaseTransport, TransportError


BUTTON_LABELS = ("A", "B", "X", "Y", "L", "R")
LED_TO_BUTTON_LABEL = {f"LED{idx}": label for idx, label in enumerate(BUTTON_LABELS, start=1)}


def _format_button_names(count: Optional[int]) -> str:
    if count is None:
        return "unknown"
    if count <= 0:
        return "0 (none)"
    names = list(BUTTON_LABELS[:count])
    if count > len(BUTTON_LABELS):
        extra = [f"B{i}" for i in range(len(BUTTON_LABELS) + 1, count + 1)]
        names.extend(extra)
    return f"{count} ({', '.join(names)})"


@dataclass
class ProcessingResult:
    """Detailed result returned after processing a single game selection event."""

    event: GameEvent
    resolution: ResolutionResult
    profile: ResolvedProfile
    transport_sent: bool
    deduplicated: bool
    transport_response: Optional[Dict[str, Any]] = None
    transport_error: Optional[str] = None


class EventProcessor:
    """Orchestrates incoming game selection events end-to-end."""

    def __init__(
        self,
        game_resolver: GameResolver,
        profile_manager: ProfileManager,
        event_logger: Optional[EventLogger] = None,
        transport: Optional[BaseTransport] = None,
        send_to_transport: bool = True,
        control_inspector: Optional[GameControlInspector] = None,
        hw_buttons: int = 6,
    ) -> None:
        self.game_resolver = game_resolver
        self.profile_manager = profile_manager
        self.event_logger = event_logger
        self.transport = transport
        self.send_to_transport = send_to_transport
        self.control_inspector = control_inspector or GameControlInspector()
        self.hw_buttons = max(1, int(hw_buttons))

        self._last_sent_signature: Optional[str] = None
        self._last_event: Optional[GameEvent] = None

    @property
    def last_event(self) -> Optional[GameEvent]:
        return self._last_event

    @property
    def last_sent_signature(self) -> Optional[str]:
        return self._last_sent_signature

    def reset_dedup_state(self) -> None:
        """Clear cached LED state so the next event is always transmitted."""
        self._last_sent_signature = None

    def process(self, incoming: Union[GameEvent, Mapping[str, Any], str]) -> ProcessingResult:
        """Process a GameEvent, dict payload, or raw JSON string."""
        if isinstance(incoming, GameEvent):
            event = incoming
        elif isinstance(incoming, str):
            event = GameEvent.from_json(incoming)
        else:
            event = GameEvent.from_dict(incoming)

        self._last_event = event
        resolution = self.game_resolver.resolve(event)
        game_req = self.control_inspector.inspect(
            event.system,
            event.rom_path,
            allow_live_query=(resolution.match_type == "default"),
        )
        if resolution.match_type == "default" and game_req.buttons is not None:
            auto_profile = self._profile_name_for_button_count(game_req.buttons)
            resolution = replace(
                resolution,
                match_type="auto_controls",
                game_key=game_req.source,
                profile_name=auto_profile,
            )
        profile = self.profile_manager.resolve_profile(resolution)

        transport_sent = False
        deduplicated = False
        transport_response: Optional[Dict[str, Any]] = None
        transport_error: Optional[str] = None

        if self.send_to_transport and self.transport is not None:
            if profile.signature == self._last_sent_signature:
                deduplicated = True
            else:
                payload = profile.to_serial_command()
                try:
                    if not self.transport.is_connected():
                        self.transport.connect()
                    transport_response = self.transport.send_command(payload)
                    transport_sent = True
                    self._last_sent_signature = profile.signature
                except TransportError as exc:
                    transport_error = str(exc)

        if self.event_logger is not None:
            status_note = self._build_log_note(
                resolution,
                profile,
                game_req,
                self.hw_buttons,
                transport_sent,
                deduplicated,
                transport_error,
            )
            self.event_logger.log_event(event, note=status_note)

        return ProcessingResult(
            event=event,
            resolution=resolution,
            profile=profile,
            transport_sent=transport_sent,
            deduplicated=deduplicated,
            transport_response=transport_response,
            transport_error=transport_error,
        )

    @staticmethod
    def _profile_name_for_button_count(buttons: int) -> str:
        if buttons <= 0:
            return "all_off"
        mapping = {
            1: "one_btn",
            2: "two_btn",
            3: "three_btn",
            4: "four_btn",
            5: "five_btn",
        }
        return mapping.get(buttons, "all_on")

    @staticmethod
    def _build_log_note(
        resolution: ResolutionResult,
        profile: ResolvedProfile,
        game_req: GameControlRequirement,
        hw_buttons: int,
        transport_sent: bool,
        deduplicated: bool,
        transport_error: Optional[str],
    ) -> str:
        if transport_error:
            tx_state = f"TRANSPORT_ERROR({transport_error})"
        elif deduplicated:
            tx_state = "SKIPPED_UNCHANGED"
        elif transport_sent:
            tx_state = "SENT_TO_TRANSPORT"
        else:
            tx_state = "LOG_ONLY"

        active_channels = {f"LED{i}" for i in range(1, hw_buttons + 1)}
        leds_on = [
            LED_TO_BUTTON_LABEL.get(led_id, led_id)
            for led_id, led_state in profile.leds.items()
            if led_state.state and led_id in active_channels
        ]
        leds_on_str = ", ".join(leds_on) if leds_on else "NONE"
        game_btns = _format_button_names(game_req.buttons)
        hw_btns_str = _format_button_names(hw_buttons)
        players_tag = f"{game_req.players}P" if game_req.players is not None else "unknown"

        return "\n".join(
            [
                f"Control  : {game_req.control_summary} | Players: {players_tag} | Game Buttons: {game_btns}",
                f"Hardware : {hw_btns_str} | LEDs ON ({len(leds_on)}): {leds_on_str}",
                f"Status   : match={resolution.match_type} | profile={profile.profile_name} | tx={tx_state}",
            ]
        )
