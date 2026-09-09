"""Replay a --trace recording without a camera or operating-system actions."""

import argparse
import json
from pathlib import Path

from backend.action_mapper import ActionMapper
from backend.gesture_classifier import GestureClassifier
from backend.gesture_controller import GestureController


def replay(path: Path) -> dict:
    """Return action events and differences from recorded labels/actions."""
    with path.open(encoding="utf-8") as source:
        session = json.loads(next(source))
        if session.get("type") != "session" or session.get("version") != 1:
            raise ValueError("Expected a version 1 gesture trace")
        settings = dict(session["mapper"])
        settings["actions_enabled"] = False
        controller = GestureController(GestureClassifier(**session["classifier"]), ActionMapper(**settings))
        summary = {"frames": 0, "differences": 0, "actions": []}
        for line in source:
            frame = json.loads(line)
            result, action = controller.process(frame["hands"], frame["timestamp"], frame["image_width"])
            description = action.command.description if action else None
            summary["frames"] += 1
            if result.gesture.value != frame["gesture"] or description != frame["action"]:
                summary["differences"] += 1
            if action is not None:
                summary["actions"].append({"timestamp": frame["timestamp"], "action": description})
            # Live execution errors revoke the gate. Reproduce that reset in
            # dry run, without invoking the original failing OS command.
            if frame.get("error"):
                controller.mapper.reset()
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    args = parser.parse_args()
    print(json.dumps(replay(args.trace), indent=2))


if __name__ == "__main__":
    main()
