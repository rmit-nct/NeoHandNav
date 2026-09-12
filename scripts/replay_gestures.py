"""Replay a --trace recording without a camera or operating-system actions."""

import argparse
import json
from pathlib import Path

from backend.action_mapper import ActionMapper
from backend.gesture_classifier import GestureClassifier
from backend.gesture_controller import GestureController
from backend.pointer_controller import PointerController, PointerSettings


def replay(path: Path) -> dict:
    """Return action events and differences from recorded labels/actions."""
    with path.open(encoding="utf-8") as source:
        session = json.loads(next(source))
        if session.get("type") != "session" or session.get("version") not in (1, 2):
            raise ValueError("Expected a version 1 or 2 gesture trace")
        settings = dict(session["mapper"])
        # Older traces used plain slide arrows; preserve their recorded mapping.
        settings.setdefault("navigation_target", "slides")
        settings["actions_enabled"] = False
        pointer_settings = dict(session.get("pointer", {}))
        pointer_settings.setdefault("point_hold_seconds", .18)
        pointer_settings.setdefault("two_finger_click_seconds", .18)
        # Traces made before motion buffering used immediate filtered movement.
        pointer_settings.setdefault("motion_buffer_seconds", 0.)
        pointer_settings.setdefault("pointer_deadzone_pixels", 0.)
        pointer = PointerController(session.get("screen_size", (1920,1080)),
                                    PointerSettings(**pointer_settings),
                                    session.get("initial_position"))
        controller = GestureController(GestureClassifier(**session["classifier"]), ActionMapper(**settings),
                                       pointer, session.get("mode", "navigation"))
        summary = {"frames": 0, "differences": 0, "actions": []}
        for line in source:
            frame = json.loads(line)
            if frame.get("type") == "control":
                control = frame["control"]
                if control == "mode":
                    controller.set_mode("navigation" if controller.mode == "mouse" else "mouse")
                elif control == "pause":
                    controller.set_paused(not controller.paused)
                elif control in ("enable", "practice"):
                    controller.reset()  # always keep replay output disabled
                pointer.position = tuple(frame["pointer_position"])
                continue
            if frame.get("cursor_position") is not None:
                pointer.physical_pointer_moved(frame["cursor_position"])
            result, action = controller.process(frame["hands"], frame["timestamp"], frame["image_width"],
                                                frame.get("image_height"))
            description = action.command.description if action else None
            summary["frames"] += 1
            arguments = list(action.command.arguments) if action else None
            if (result.gesture.value != frame["gesture"] or description != frame["action"]
                or ("arguments" in frame and arguments != frame["arguments"])):
                summary["differences"] += 1
            if action is not None:
                summary["actions"].append({"timestamp": frame["timestamp"], "action": description})
            # Live execution errors revoke the gate. Reproduce that reset in
            # dry run, without invoking the original failing OS command.
            if frame.get("error"):
                controller.mapper.reset()
                controller.pointer.reset()
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    args = parser.parse_args()
    print(json.dumps(replay(args.trace), indent=2))


if __name__ == "__main__":
    main()
