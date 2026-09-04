"""Safe mapping from gesture events to operating-system actions."""

from __future__ import annotations

import platform
from dataclasses import dataclass
from time import monotonic
from typing import Callable

from backend.gesture_classifier import Gesture, GestureResult


@dataclass(frozen=True, slots=True)
class ActionCommand:
    """An OS action independent from the PyAutoGUI implementation."""

    kind: str
    arguments: tuple[str | int, ...]
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
    action. A held scroll pose may repeat, but another action cannot replace it
    until an open palm resets the control state.
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

        zoom_modifier = "command" if platform.system() == "Darwin" else "ctrl"
        self.actions_enabled = actions_enabled
        self.cooldown_ms = cooldown_ms
        self.scroll_cooldown_ms = (
            cooldown_ms if scroll_cooldown_ms is None else scroll_cooldown_ms
        )
        self.require_open_palm = require_open_palm
        self.open_palm_hold_ms = open_palm_hold_ms
        self.fist_release_ms = fist_release_ms
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
            Gesture.FIST: ActionCommand("key", ("space",), "play or pause"),
        }
        self._executor = executor or self._execute_with_pyautogui
        self._last_action_at: dict[str, float] = {}
        self._held_static_gesture = Gesture.NONE
        self._fist_release_started_at: float | None = None
        self._ready_for_action = not require_open_palm
        self._active_control = Gesture.NONE
        self._open_palm_started_at: float | None = None

    @property
    def control_status(self) -> str:
        """Short state label suitable for the camera overlay."""

        if not self.require_open_palm:
            return "READY"
        if self._active_control in (Gesture.SCROLL_UP, Gesture.SCROLL_DOWN):
            return f"ACTIVE: {self._active_control.display_name}"
        if self._ready_for_action:
            return "READY"
        return "SHOW OPEN PALM"

    def set_actions_enabled(self, enabled: bool) -> None:
        """Arm or disarm OS control explicitly."""

        self.actions_enabled = enabled

    def handle(
        self,
        result: GestureResult | Gesture,
        timestamp: float | None = None,
    ) -> ActionResult | None:
        """Accept a gesture when the palm gate and cooldown both permit it."""

        gesture = result.gesture if isinstance(result, GestureResult) else result
        now = monotonic() if timestamp is None else timestamp

        if gesture is Gesture.OPEN_PALM:
            # One recognized palm frame immediately stops a held control. The
            # palm must then remain recognized for a short time before the next
            # action is armed, preventing a noisy transition from triggering it.
            self._active_control = Gesture.NONE
            self._held_static_gesture = Gesture.NONE
            self._fist_release_started_at = None
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

        if gesture is Gesture.NONE:
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

        self._fist_release_started_at = None

        command = self.commands.get(gesture)
        if command is None:
            if gesture is not Gesture.FIST:
                self._held_static_gesture = Gesture.NONE
            return None

        if self.require_open_palm:
            if not self._ready_for_action:
                return None
            if self._active_control is not Gesture.NONE:
                # A held scroll pose can repeat. Any different pose is ignored
                # until the user deliberately shows an open palm.
                if gesture is not self._active_control:
                    self._active_control = Gesture.NONE
                    self._ready_for_action = False
                    return None
                if gesture not in (Gesture.SCROLL_UP, Gesture.SCROLL_DOWN):
                    return None
            else:
                self._active_control = gesture
                if gesture not in (Gesture.SCROLL_UP, Gesture.SCROLL_DOWN):
                    self._ready_for_action = False

        # Keep a held fist one-shot in compatibility mode too. With the palm
        # gate enabled, page, fist, and zoom controls are already one-shot.
        if gesture is Gesture.FIST:
            if self._held_static_gesture is Gesture.FIST:
                return None
            self._held_static_gesture = Gesture.FIST
        else:
            self._held_static_gesture = Gesture.NONE

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

        if not self.actions_enabled:
            return ActionResult(command=command, executed=False)

        try:
            self._executor(command)
        except Exception as exc:  # keep the camera loop alive on OS errors
            return ActionResult(command=command, executed=False, error=str(exc))
        return ActionResult(command=command, executed=True)

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
    def _execute_with_pyautogui(command: ActionCommand) -> None:
        import pyautogui

        pyautogui.FAILSAFE = True
        if command.kind == "key":
            pyautogui.press(str(command.arguments[0]))
        elif command.kind == "scroll":
            pyautogui.scroll(int(command.arguments[0]))
        elif command.kind == "hotkey":
            pyautogui.hotkey(*(str(value) for value in command.arguments))
        else:
            raise ValueError(f"Unsupported action kind: {command.kind}")
