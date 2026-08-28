"""NEO HandNav application integration loop."""

from __future__ import annotations

import os
import sys
import time

import cv2
from dotenv import load_dotenv

from backend.action_mapper import ActionMapper, ActionResult
from backend.gesture_classifier import Gesture, GestureClassifier, GestureResult
from backend.hand_tracker import HandTracker


WINDOW_NAME = "NEO HandNav - press Q to quit"


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
    last_action: ActionResult | None,
) -> None:
    height, width = frame.shape[:2]
    cv2.rectangle(frame, (0, 0), (width, 94), (20, 20, 20), -1)

    gesture_text = result.gesture.display_name
    if result.gesture is Gesture.NONE:
        gesture_text = "No stable gesture"
    cv2.putText(
        frame,
        f"Gesture: {gesture_text}  Confidence: {result.confidence:.0%}",
        (16, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (80, 230, 120),
        2,
        cv2.LINE_AA,
    )

    mode = "ARMED" if actions_enabled else "DRY RUN"
    mode_color = (70, 70, 255) if actions_enabled else (0, 210, 255)
    cv2.putText(
        frame,
        f"Actions: {mode}",
        (16, 59),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        mode_color,
        2,
        cv2.LINE_AA,
    )

    if last_action is not None:
        prefix = "DONE" if last_action.executed else "DRY RUN"
        if last_action.error:
            prefix = "ERROR"
        cv2.putText(
            frame,
            f"{prefix}: {last_action.command.description}",
            (16, 86),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (235, 235, 235),
            1,
            cv2.LINE_AA,
        )

    cv2.putText(
        frame,
        "Q: quit",
        (width - 95, height - 14),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (235, 235, 235),
        1,
        cv2.LINE_AA,
    )


def main() -> int:
    load_dotenv()
    camera_index = int(os.getenv("CAMERA_INDEX", "0"))
    detection_confidence = float(
        os.getenv("MIN_HAND_DETECTION_CONFIDENCE", "0.60")
    )
    tracking_confidence = float(os.getenv("MIN_TRACKING_CONFIDENCE", "0.60"))
    cooldown_ms = int(os.getenv("GESTURE_COOLDOWN_MS", "800"))
    actions_enabled = _env_bool("ACTIONS_ENABLED", False)

    capture = _open_camera(camera_index)
    if not capture.isOpened():
        print(
            "Could not open the webcam. Close other camera apps or change "
            "CAMERA_INDEX in .env."
        )
        capture.release()
        return 1

    tracker = HandTracker(
        max_hands=1,
        detection_con=detection_confidence,
        track_con=tracking_confidence,
    )
    if tracker.detector is None:
        print("Could not initialize MediaPipe HandLandmarker.")
        capture.release()
        return 1

    classifier = GestureClassifier()
    mapper = ActionMapper(
        actions_enabled=actions_enabled,
        cooldown_ms=cooldown_ms,
    )

    last_action: ActionResult | None = None
    last_action_at = 0.0
    print(f"NEO HandNav started. Actions are {'ARMED' if actions_enabled else 'DRY RUN'}.")
    print("Press Q in the camera window to quit.")

    try:
        while True:
            success, frame = capture.read()
            if not success:
                print("The webcam opened but no frame could be read.")
                return 1

            frame = cv2.flip(frame, 1)
            tracker.process_frame(frame)
            hands = tracker.get_landmarks(frame, draw=True)

            now = time.monotonic()
            if hands:
                result = classifier.classify(hands[0], timestamp=now)
            else:
                classifier.reset()
                result = GestureResult(Gesture.NONE, 0.0)

            action = mapper.handle(result, timestamp=now)
            if action is not None:
                last_action = action
                last_action_at = now
                state = "executed" if action.executed else "dry run"
                if action.error:
                    state = f"error: {action.error}"
                print(f"{action.command.description}: {state}")
            elif now - last_action_at > 1.2:
                last_action = None

            _draw_status(frame, result, actions_enabled, last_action)
            cv2.imshow(WINDOW_NAME, frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                break
    finally:
        capture.release()
        cv2.destroyAllWindows()
        tracker.detector.close()

    print("NEO HandNav stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
