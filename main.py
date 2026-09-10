"""NEO HandNav application integration loop."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
import time
import webbrowser

import cv2
from dotenv import load_dotenv

from backend.action_mapper import ActionMapper, ActionResult
from backend.gesture_classifier import Gesture, GestureClassifier, GestureResult
from backend.gesture_controller import GestureController
from backend.hand_tracker import HandTracker
from backend.pointer_controller import PointerController, PointerSettings
from ui.feedback_overlay import FeedbackOverlay


WINDOW_NAME = "NEO HandNav - press Q to quit"
OVERLAY = FeedbackOverlay()


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _open_camera(camera_index: int):
    if sys.platform.startswith("win"):
        return cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
    return cv2.VideoCapture(camera_index)


def _draw_status(
    frame,
    result: GestureResult,
    actions_enabled: bool,
    control_status: str,
    last_action: ActionResult | None,
    **options,
):
    return OVERLAY.render(frame, result.gesture, actions_enabled, control_status, last_action, **options)


def _screen_geometry():
    import pyautogui
    return tuple(pyautogui.size()), tuple(pyautogui.position())


def _pointer_position():
    import pyautogui
    return tuple(pyautogui.position())


def _open_practice():
    return webbrowser.open((Path(__file__).resolve().parent / "tests/fixtures/browser_input.html").as_uri())


def main() -> int:
    parser = argparse.ArgumentParser(description="Webcam gesture controls")
    parser.add_argument(
        "--trace", type=Path,
        help="Write landmarks and actions to a new local JSONL file",
    )
    parser.add_argument("--mode", choices=("mouse", "navigation"), help="Override CONTROL_MODE")
    parser.add_argument("--dry-run", action="store_true", help="Preview gestures without OS input")
    parser.add_argument("--practice", action="store_true", help="Open the local browser input test")
    args = parser.parse_args()
    load_dotenv()
    camera_index = int(os.getenv("CAMERA_INDEX", "0"))
    detection_confidence = float(
        os.getenv("MIN_HAND_DETECTION_CONFIDENCE", "0.60")
    )
    tracking_confidence = float(os.getenv("MIN_TRACKING_CONFIDENCE", "0.60"))
    cooldown_ms = int(os.getenv("GESTURE_COOLDOWN_MS", "800"))
    scroll_cooldown_ms = int(os.getenv("SCROLL_COOLDOWN_MS", "60"))
    scroll_amount = int(os.getenv("SCROLL_AMOUNT", "1"))
    open_palm_hold_ms = int(os.getenv("OPEN_PALM_HOLD_MS", "120"))
    direction_settle_ms = int(os.getenv("DIRECTION_SETTLE_MS", "220"))
    direction_stillness_radius = float(
        os.getenv("DIRECTION_STILLNESS_RADIUS", "0.10")
    )
    actions_enabled = _env_bool("ACTIONS_ENABLED", False) and not args.dry_run
    mode = args.mode or os.getenv("CONTROL_MODE", "mouse").strip().lower()
    pointer_settings = PointerSettings(
        margin=float(os.getenv("POINTER_MARGIN", ".15")),
        min_cutoff=float(os.getenv("POINTER_MIN_CUTOFF", "1.5")),
        speed_coefficient=float(os.getenv("POINTER_SPEED_COEFFICIENT", "6")),
        motion_buffer_seconds=float(os.getenv("POINTER_BUFFER_MS", "100"))/1000,
        pointer_deadzone_pixels=float(os.getenv("POINTER_DEADZONE_PX", "2")),
        double_click_hold_seconds=float(os.getenv("DOUBLE_CLICK_HOLD_MS", "900"))/1000,
        fist_hold_seconds=float(os.getenv("FIST_HOLD_MS", "600"))/1000,
        scroll_interval_seconds=scroll_cooldown_ms/1000,
        scroll_amount=scroll_amount,
    )

    classifier_settings = {
        "direction_settle_seconds": direction_settle_ms / 1000.0,
        "direction_stillness_radius": direction_stillness_radius,
    }
    mapper_settings = {
        "cooldown_ms": cooldown_ms,
        "scroll_cooldown_ms": scroll_cooldown_ms,
        "scroll_amount": scroll_amount,
        "require_open_palm": True,
        "open_palm_hold_ms": open_palm_hold_ms,
        "play_pause_key": os.getenv("PLAY_PAUSE_KEY", "playpause" if sys.platform.startswith("win") else "space").strip().lower(),
        "navigation_target": os.getenv("NAVIGATION_TARGET", "browser").strip().lower(),
    }
    # Validate configuration before acquiring the camera or model resources.
    classifier = GestureClassifier(**classifier_settings)
    mapper = ActionMapper(actions_enabled=actions_enabled, **mapper_settings)
    screen_size, initial_position = _screen_geometry()
    pointer = PointerController(screen_size, pointer_settings, initial_position)
    controller = GestureController(classifier, mapper, pointer, mode)

    capture = _open_camera(camera_index)
    if not capture.isOpened():
        print(
            "Could not open the webcam. Close other camera apps or change "
            "CAMERA_INDEX in .env."
        )
        capture.release()
        return 1

    tracker = HandTracker(
        max_hands=2,
        detection_con=detection_confidence,
        track_con=tracking_confidence,
    )
    if tracker.detector is None:
        print("Could not initialize MediaPipe HandLandmarker.")
        capture.release()
        return 1

    last_action: ActionResult | None = None
    last_action_at = 0.0
    print(f"NEO HandNav started in {mode} mode. Input is {'LIVE' if actions_enabled else 'DRY RUN'}.")
    if mode == "mouse":
        print("Point -> add middle finger: single click | Palm -> two fingers: scroll/navigation | Held fist: play/pause")
    print(f"Left/right target: {mapper_settings['navigation_target']}. Keep the target browser/app focused.")
    print("E: enable input | P: pause | M: mode | H: help | T: browser practice | Q/Esc: quit")

    trace = None
    pending_controls = []
    help_visible = False
    fps = 0.
    previous_frame_at = None
    try:
        cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_AUTOSIZE)
        def on_mouse(event, x, y, flags, param):
            if event == cv2.EVENT_LBUTTONUP:
                action = OVERLAY.hit_test(x, y)
                if action:
                    pending_controls.append(action)
        cv2.setMouseCallback(WINDOW_NAME, on_mouse)
        if args.practice:
            _open_practice()
        if args.trace is not None:
            args.trace.parent.mkdir(parents=True, exist_ok=True)
            trace = args.trace.open("x", encoding="utf-8")
            trace.write(json.dumps({
                "type": "session", "version": 2,
                "classifier": classifier_settings,
                "mapper": mapper_settings,
                "mode": mode, "pointer": asdict(pointer_settings),
                "screen_size": screen_size, "initial_position": initial_position,
            }) + "\n")
        while True:
            success, frame = capture.read()
            if not success:
                print("The webcam opened but no frame could be read.")
                return 1

            frame = cv2.flip(frame, 1)
            tracker.process_frame(frame)
            hands = tracker.get_landmarks(frame, draw=True)

            now = time.monotonic()
            if previous_frame_at is not None and now > previous_frame_at:
                fps = .9*fps + .1/(now-previous_frame_at) if fps else 1/(now-previous_frame_at)
            previous_frame_at = now
            observed_cursor = None
            if mapper.actions_enabled and controller.mode == "mouse" and not controller.paused:
                observed_cursor = _pointer_position()
                pointer.physical_pointer_moved(observed_cursor)
            result, action = controller.process(hands, now, frame.shape[1], frame.shape[0])
            if trace is not None:
                trace.write(json.dumps({
                    "type": "frame", "timestamp": now, "image_width": frame.shape[1],
                    "image_height": frame.shape[0], "cursor_position": observed_cursor,
                    "hands": hands, "gesture": result.gesture.value,
                    "control_status": controller.control_status,
                    "tracking_status": controller.tracking_status,
                    "action": action.command.description if action else None,
                    "arguments": action.command.arguments if action else None,
                    "executed": action.executed if action else False,
                    "error": action.error if action else None,
                }) + "\n")
            if action is not None and (action.command.kind != "move" or action.error):
                last_action = action
                last_action_at = now
                state = "executed" if action.executed else "dry run"
                if action.error:
                    state = f"error: {action.error}"
                print(f"{action.command.description}: {state}")
            elif now - last_action_at > 3 and not (last_action and last_action.error):
                last_action = None

            display = _draw_status(
                frame,
                result,
                mapper.actions_enabled,
                controller.control_status,
                last_action,
                mode=controller.mode, paused=controller.paused,
                progress=pointer.progress if controller.mode == "mouse" else 0,
                help_visible=help_visible, fps=fps, margin=pointer.settings.margin,
                max_width=min(960,screen_size[0]-80), max_height=screen_size[1]-100,
                navigation_target=mapper_settings['navigation_target'],
            )
            cv2.imshow(WINDOW_NAME, display)
            key = cv2.waitKey(1) & 0xFF
            keyboard_control = {ord('q'): 'quit', 27: 'quit', ord('e'): 'enable',
                                ord('p'): 'pause', ord('m'): 'mode', ord('h'): 'help', ord('t'): 'practice'}.get(key)
            if keyboard_control:
                pending_controls.append(keyboard_control)
            quit_requested = False
            for control in dict.fromkeys(pending_controls):
                if control == "quit":
                    quit_requested = True
                elif control == "enable":
                    controller.set_actions_enabled(not mapper.actions_enabled)
                    pointer.position = _pointer_position()
                    last_action = None
                elif control == "pause":
                    controller.set_paused(not controller.paused)
                    pointer.position = _pointer_position()
                elif control == "mode":
                    controller.set_mode("navigation" if controller.mode == "mouse" else "mouse")
                    pointer.position = _pointer_position()
                    last_action = None
                elif control == "help":
                    help_visible = not help_visible
                elif control == "practice":
                    controller.reset()
                    _open_practice()
                if trace is not None:
                    trace.write(json.dumps({"type":"control", "control":control,
                                            "pointer_position":pointer.position}) + "\n")
            pending_controls.clear()
            if quit_requested:
                break
            if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                break
    finally:
        if trace is not None:
            trace.close()
        capture.release()
        cv2.destroyAllWindows()
        tracker.detector.close()

    print("NEO HandNav stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
