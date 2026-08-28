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
    """Apply cooldown and optional PyAutoGUI execution to gesture events.

    Actions are disabled by default. In dry-run mode the same command result is
    returned for the overlay, but no keyboard or scroll event is sent.
    """

    def __init__(
        self,
        *,
        actions_enabled: bool = False,
        cooldown_ms: int = 800,
        scroll_amount: int = 4,
        executor: Executor | None = None,
    ) -> None:
        if cooldown_ms < 0:
            raise ValueError("cooldown_ms must be non-negative")
        if scroll_amount < 1:
            raise ValueError("scroll_amount must be at least 1")

        zoom_modifier = "command" if platform.system() == "Darwin" else "ctrl"
        self.actions_enabled = actions_enabled
        self.cooldown_ms = cooldown_ms
        self.commands = {
            Gesture.SWIPE_LEFT: ActionCommand("key", ("left",), "previous page"),
            Gesture.SWIPE_RIGHT: ActionCommand("key", ("right",), "next page"),
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
        self._last_action_at: dict[Gesture, float] = {}
        self._held_static_gesture = Gesture.NONE

    def set_actions_enabled(self, enabled: bool) -> None:
        """Arm or disarm OS control explicitly."""

        self.actions_enabled = enabled

    def handle(
        self,
        result: GestureResult | Gesture,
        timestamp: float | None = None,
    ) -> ActionResult | None:
        """Accept a gesture and return its action when cooldown permits."""

        gesture = result.gesture if isinstance(result, GestureResult) else result
        now = monotonic() if timestamp is None else timestamp

        if gesture is Gesture.NONE:
            self._held_static_gesture = Gesture.NONE
            return None

        command = self.commands.get(gesture)
        if command is None:
            if gesture is not Gesture.FIST:
                self._held_static_gesture = Gesture.NONE
            return None

        # A held fist must not press Space repeatedly. Motion gestures are
        # already discrete events and may repeat after their short cooldown.
        if gesture is Gesture.FIST:
            if self._held_static_gesture is Gesture.FIST:
                return None
            self._held_static_gesture = Gesture.FIST
        else:
            self._held_static_gesture = Gesture.NONE

        previous = self._last_action_at.get(gesture)
        cooldown_seconds = self.cooldown_ms / 1000.0
        if previous is not None and now - previous < cooldown_seconds:
            return None
        self._last_action_at[gesture] = now

        if not self.actions_enabled:
            return ActionResult(command=command, executed=False)

        try:
            self._executor(command)
        except Exception as exc:  # keep the camera loop alive on OS errors
            return ActionResult(command=command, executed=False, error=str(exc))
        return ActionResult(command=command, executed=True)

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
