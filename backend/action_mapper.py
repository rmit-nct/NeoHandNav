"""Safe mapping from gesture events to operating-system actions."""

from __future__ import annotations

import platform
from dataclasses import dataclass
from math import isfinite
from time import monotonic
from typing import Callable

from backend.gesture_classifier import Gesture, GestureResult


@dataclass(frozen=True, slots=True)
class ActionCommand:
    """An OS action independent from the PyAutoGUI implementation."""

    kind: str
    arguments: tuple[str | int | float, ...]
    description: str


@dataclass(frozen=True, slots=True)
class ActionResult:
    """The result shown by the application after an action is accepted."""

    command: ActionCommand
    executed: bool
    error: str | None = None


Executor = Callable[[ActionCommand], None]


class ActionMapper:
    """Gate gestures, apply cooldown, and optionally execute OS actions.

    Actions are disabled by default. In dry-run mode the same command result is
    returned for the overlay, but no keyboard or scroll event is sent. When the
    open-palm gate is enabled, a stable open palm must be shown before every new
    interaction. A held scroll pose repeats; a pinch session accepts zoom in
    and out events. Switching to another control requires a new open palm.
    """

    def __init__(
        self,
        *,
        actions_enabled: bool = False,
        cooldown_ms: int = 800,
        scroll_amount: int = 4,
        scroll_cooldown_ms: int | None = None,
        require_open_palm: bool = True,
        open_palm_hold_ms: int = 120,
        fist_release_ms: int = 250,
        unknown_grace_ms: int = 350,
        max_frame_gap_seconds: float = 0.5,
        play_pause_key: str = "space",
        navigation_target: str = "browser",
        executor: Executor | None = None,
    ) -> None:
        if cooldown_ms < 0:
            raise ValueError("cooldown_ms must be non-negative")
        if scroll_amount < 1:
            raise ValueError("scroll_amount must be at least 1")
        if scroll_cooldown_ms is not None and scroll_cooldown_ms < 0:
            raise ValueError("scroll_cooldown_ms must be non-negative")
        if open_palm_hold_ms < 0:
            raise ValueError("open_palm_hold_ms must be non-negative")
        if fist_release_ms < 0:
            raise ValueError("fist_release_ms must be non-negative")
        if unknown_grace_ms < 0:
            raise ValueError("unknown_grace_ms must be non-negative")
        if not isfinite(max_frame_gap_seconds) or max_frame_gap_seconds <= 0:
            raise ValueError("max_frame_gap_seconds must be positive and finite")
        if play_pause_key not in ("playpause", "space", "k"):
            raise ValueError("play_pause_key must be playpause, space or k")
        if navigation_target not in ("browser", "slides"):
            raise ValueError("navigation_target must be browser or slides")

        zoom_modifier = "command" if platform.system() == "Darwin" else "ctrl"
        self.actions_enabled = actions_enabled
        self.cooldown_ms = cooldown_ms
        self.scroll_cooldown_ms = (
            cooldown_ms if scroll_cooldown_ms is None else scroll_cooldown_ms
        )
        self.require_open_palm = require_open_palm
        self.open_palm_hold_ms = open_palm_hold_ms
        self.fist_release_ms = fist_release_ms
        self.unknown_grace_ms = unknown_grace_ms
        self.max_frame_gap_seconds = max_frame_gap_seconds
        self.commands = {
            Gesture.PREVIOUS_PAGE: ActionCommand(
                "key", ("left",), "previous page"
            ),
            Gesture.NEXT_PAGE: ActionCommand("key", ("right",), "next page"),
            Gesture.SCROLL_UP: ActionCommand("scroll", (scroll_amount,), "scroll up"),
            Gesture.SCROLL_DOWN: ActionCommand("scroll", (-scroll_amount,), "scroll down"),
            Gesture.ZOOM_IN: ActionCommand(
                "hotkey", (zoom_modifier, "+"), "zoom in"
            ),
            Gesture.ZOOM_OUT: ActionCommand(
                "hotkey", (zoom_modifier, "-"), "zoom out"
            ),
            Gesture.FIST: ActionCommand("key", (play_pause_key,), "play or pause"),
        }
        if navigation_target == "browser":
            modifier = "command" if platform.system() == "Darwin" else "alt"
            self.commands[Gesture.PREVIOUS_PAGE] = ActionCommand("hotkey", (modifier,"left"), "browser back")
            self.commands[Gesture.NEXT_PAGE] = ActionCommand("hotkey", (modifier,"right"), "browser forward")
        self._executor = executor or self._execute_with_pyautogui
        self.reset()

    def reset(self) -> None:
        """Discard all authorization and timing state after tracking is lost."""
        self._last_action_at: dict[str, float] = {}
        self._held_static_gesture = Gesture.NONE
        self._fist_release_started_at: float | None = None
        self._ready_for_action = not self.require_open_palm
        self._active_control = Gesture.NONE
        self._open_palm_started_at: float | None = None
        self._unknown_started_at: float | None = None
        self._last_timestamp: float | None = None

    @property
    def control_status(self) -> str:
        """Short state label suitable for the camera overlay."""

        if not self.require_open_palm:
            return "READY"
        if self._active_control in (Gesture.SCROLL_UP, Gesture.SCROLL_DOWN):
            if self._unknown_started_at is not None:
                return "PAUSED: hold scroll pose"
            return f"ACTIVE: {self._active_control.display_name}"
        if self._active_control is Gesture.PINCH:
            return "ACTIVE: Pinch zoom"
        if self._ready_for_action:
            return "READY"
        return "SHOW OPEN PALM"

    def set_actions_enabled(self, enabled: bool) -> None:
        """Arm or disarm OS control explicitly."""

        if enabled != self.actions_enabled:
            self.reset()
        self.actions_enabled = enabled

    def handle(
        self,
        result: GestureResult | Gesture,
        timestamp: float | None = None,
    ) -> ActionResult | None:
        """Accept a gesture when the palm gate and cooldown both permit it."""

        gesture = result.gesture if isinstance(result, GestureResult) else result
        now = monotonic() if timestamp is None else timestamp
        if not isfinite(now):
            self.reset()
            raise ValueError("timestamp must be finite")
        if self._last_timestamp is not None and (
            now <= self._last_timestamp
            or now - self._last_timestamp > self.max_frame_gap_seconds
        ):
            self.reset()
        self._last_timestamp = now

        if gesture is Gesture.OPEN_PALM:
            # One recognized palm frame immediately stops a held control. The
            # palm must then remain recognized for a short time before the next
            # action is armed, preventing a noisy transition from triggering it.
            self._active_control = Gesture.NONE
            self._held_static_gesture = Gesture.NONE
            self._fist_release_started_at = None
            self._unknown_started_at = None
            if self._open_palm_started_at is None:
                self._open_palm_started_at = now
            if self.require_open_palm:
                self._ready_for_action = False
            if (
                not self.require_open_palm
                or now - self._open_palm_started_at
                >= self.open_palm_hold_ms / 1000.0
            ):
                if not self._ready_for_action:
                    self._last_action_at.clear()
                self._ready_for_action = True
            return None

        self._open_palm_started_at = None

        if gesture in (Gesture.NONE, Gesture.TWO_FINGER):
            if self._unknown_started_at is None:
                self._unknown_started_at = now
            if now - self._unknown_started_at >= self.unknown_grace_ms / 1000.0:
                self._end_control()
            if self._held_static_gesture is Gesture.FIST:
                if self._fist_release_started_at is None:
                    self._fist_release_started_at = now
                elif (
                    now - self._fist_release_started_at
                    >= self.fist_release_ms / 1000.0
                ):
                    self._held_static_gesture = Gesture.NONE
                    self._fist_release_started_at = None
            return None

        if (
            self._unknown_started_at is not None
            and now - self._unknown_started_at >= self.unknown_grace_ms / 1000.0
        ):
            self._end_control()
        self._unknown_started_at = None
        self._fist_release_started_at = None

        command = self.commands.get(gesture)
        if command is None:
            if self._active_control is not Gesture.NONE:
                if not (
                    self._active_control is Gesture.PINCH and gesture is Gesture.PINCH
                ):
                    self._end_control()
            if gesture is not Gesture.FIST:
                self._held_static_gesture = Gesture.NONE
            return None

        if self.require_open_palm:
            if not self._ready_for_action:
                return None
            if self._active_control is not Gesture.NONE:
                # Scroll keeps one direction; a pinch session may zoom either
                # way. Other controls require a deliberate open-palm reset.
                continuing_zoom = self._active_control is Gesture.PINCH and gesture in (
                    Gesture.ZOOM_IN, Gesture.ZOOM_OUT
                )
                if gesture is not self._active_control and not continuing_zoom:
                    self._end_control()
                    return None
                if (
                    gesture not in (Gesture.SCROLL_UP, Gesture.SCROLL_DOWN)
                    and not continuing_zoom
                ):
                    return None

        # Keep a held fist one-shot in compatibility mode too. With the palm
        # gate enabled, page and fist controls are already one-shot.
        if gesture is Gesture.FIST:
            if self._held_static_gesture is Gesture.FIST:
                return None

        action_family = self._action_family(gesture)
        previous = self._last_action_at.get(action_family)
        if action_family == "scroll":
            cooldown_ms = self.scroll_cooldown_ms
        else:
            cooldown_ms = self.cooldown_ms
        cooldown_seconds = cooldown_ms / 1000.0
        if previous is not None and now - previous < cooldown_seconds:
            return None
        self._last_action_at[action_family] = now
        # Commit interaction state only after cooldown accepts the command.
        self._held_static_gesture = gesture if gesture is Gesture.FIST else Gesture.NONE
        if self.require_open_palm:
            self._active_control = Gesture.PINCH if action_family == "zoom" else gesture
            if action_family not in ("scroll", "zoom"):
                self._ready_for_action = False

        return self.execute(command)

    def execute(self, command: ActionCommand) -> ActionResult:
        """Execute an already gated command from navigation or mouse control."""
        if not self.actions_enabled:
            return ActionResult(command=command, executed=False)

        try:
            self._executor(command)
        except Exception as exc:  # keep the camera loop alive on OS errors
            # In particular, never auto-resume after PyAutoGUI's fail-safe.
            self.set_actions_enabled(False)
            return ActionResult(command=command, executed=False, error=str(exc))
        return ActionResult(command=command, executed=True)

    def _end_control(self) -> None:
        """End a consumed interaction; preserve readiness while forming a pose."""
        if self._active_control is not Gesture.NONE:
            self._active_control = Gesture.NONE
            self._ready_for_action = not self.require_open_palm

    @staticmethod
    def _action_family(gesture: Gesture) -> str:
        if gesture in (Gesture.PREVIOUS_PAGE, Gesture.NEXT_PAGE):
            return "page"
        if gesture in (Gesture.SCROLL_UP, Gesture.SCROLL_DOWN):
            return "scroll"
        if gesture in (Gesture.ZOOM_IN, Gesture.ZOOM_OUT):
            return "zoom"
        return gesture.value

    @staticmethod
    def _double_click_interval() -> float:
        """Keep generated clicks inside the user's Windows double-click time."""
        if platform.system() == "Windows":
            import ctypes
            milliseconds = ctypes.windll.user32.GetDoubleClickTime()
            if milliseconds > 0:
                return min(.10, milliseconds / 3000.0)
        return .10

    @staticmethod
    def _execute_with_pyautogui(command: ActionCommand) -> None:
        import pyautogui

        pyautogui.FAILSAFE = True
        # Cooldowns above pace commands. The default 100 ms post-call sleep
        # would freeze camera capture on every action; bypass only that sleep.
        if command.kind == "key":
            pyautogui.press(str(command.arguments[0]), _pause=False)
        elif command.kind == "scroll":
            pyautogui.scroll(int(command.arguments[0]), _pause=False)
        elif command.kind == "hotkey":
            pyautogui.hotkey(*(str(value) for value in command.arguments), _pause=False)
        elif command.kind == "move":
            pyautogui.moveTo(int(command.arguments[0]), int(command.arguments[1]), _pause=False)
        elif command.kind == "click":
            x, y, clicks, button = command.arguments
            pyautogui.click(
                int(x), int(y), clicks=int(clicks), button=str(button),
                interval=ActionMapper._double_click_interval() if clicks == 2 else 0, _pause=False,
            )
        else:
            raise ValueError(f"Unsupported action kind: {command.kind}")
