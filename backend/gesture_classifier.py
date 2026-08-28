"""Rule-based hand gesture recognition for NEO HandNav.

The classifier consumes the pixel-coordinate landmark format produced by
``HandTracker.get_landmarks``: ``[landmark_id, x, y]`` for all 21 landmarks.
It recognizes static hand shapes and turns deliberate hand motion into events.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import acos, degrees, hypot
from time import monotonic
from typing import Iterable, Sequence


class Gesture(str, Enum):
    """Gesture labels shared by classification, actions, and the overlay."""

    NONE = "none"
    OPEN_PALM = "open_palm"
    FIST = "fist"
    POINT = "point"
    PINCH = "pinch"
    SWIPE_LEFT = "swipe_left"
    SWIPE_RIGHT = "swipe_right"
    SCROLL_UP = "scroll_up"
    SCROLL_DOWN = "scroll_down"
    ZOOM_IN = "zoom_in"
    ZOOM_OUT = "zoom_out"

    @property
    def display_name(self) -> str:
        return self.value.replace("_", " ").title()


@dataclass(frozen=True, slots=True)
class GestureResult:
    """One classifier result for the application loop."""

    gesture: Gesture
    confidence: float = 0.0


Point = tuple[float, float]
Landmark = Sequence[int | float]


class GestureClassifier:
    """Classify hand shapes and motion using MediaPipe landmark geometry.

    Static labels require a few consecutive frames. Swipe, scroll, and zoom
    are emitted as short motion events. Coordinates are normalized by palm
    size so thresholds remain useful when the hand moves closer to the camera.
    """

    _FINGERS = (
        (8, 6, 5),
        (12, 10, 9),
        (16, 14, 13),
        (20, 18, 17),
    )

    def __init__(
        self,
        *,
        ema_alpha: float = 0.35,
        min_stable_frames: int = 3,
        swipe_threshold: float = 0.85,
        scroll_threshold: float = 0.35,
        zoom_threshold: float = 0.12,
        motion_window_seconds: float = 0.8,
    ) -> None:
        if not 0 < ema_alpha <= 1:
            raise ValueError("ema_alpha must be between 0 and 1")
        if min_stable_frames < 1:
            raise ValueError("min_stable_frames must be at least 1")

        self.ema_alpha = ema_alpha
        self.min_stable_frames = min_stable_frames
        self.swipe_threshold = swipe_threshold
        self.scroll_threshold = scroll_threshold
        self.zoom_threshold = zoom_threshold
        self.motion_window_seconds = motion_window_seconds
        self.reset()

    def reset(self) -> None:
        """Clear temporal state after the tracked hand disappears."""

        self._filtered_center: Point | None = None
        self._filtered_pinch_ratio: float | None = None
        self._motion_anchor: tuple[Point, float] | None = None
        self._pinch_anchor: tuple[float, float] | None = None
        self._candidate = Gesture.NONE
        self._candidate_frames = 0

    def classify(
        self,
        landmarks: Sequence[Landmark],
        timestamp: float | None = None,
    ) -> GestureResult:
        """Return the current stable shape or a deliberate motion event."""

        now = monotonic() if timestamp is None else timestamp
        points = self._to_points(landmarks)
        palm_scale = max(
            self._distance(points[0], points[9]),
            self._distance(points[5], points[17]),
            1.0,
        )
        center = self._average(points[index] for index in (0, 5, 9, 13, 17))
        center = self._ema_point(self._filtered_center, center)
        self._filtered_center = center

        extended = [
            self._finger_extended(points, tip, pip, mcp)
            for tip, pip, mcp in self._FINGERS
        ]
        pinch_ratio = self._distance(points[4], points[8]) / palm_scale
        pinch_ratio = self._ema_value(self._filtered_pinch_ratio, pinch_ratio)
        self._filtered_pinch_ratio = pinch_ratio

        raw_gesture, confidence = self._static_shape(extended, pinch_ratio)
        motion = self._motion_event(
            raw_gesture=raw_gesture,
            center=center,
            palm_scale=palm_scale,
            pinch_ratio=pinch_ratio,
            timestamp=now,
        )
        if motion is not None:
            self._candidate = Gesture.NONE
            self._candidate_frames = 0
            return GestureResult(motion, 1.0)

        if raw_gesture == self._candidate:
            self._candidate_frames += 1
        else:
            self._candidate = raw_gesture
            self._candidate_frames = 1

        if raw_gesture is Gesture.NONE:
            return GestureResult(Gesture.NONE, 0.0)
        if self._candidate_frames < self.min_stable_frames:
            return GestureResult(Gesture.NONE, confidence)
        return GestureResult(raw_gesture, confidence)

    @staticmethod
    def _static_shape(
        extended: Sequence[bool], pinch_ratio: float
    ) -> tuple[Gesture, float]:
        extended_count = sum(extended)
        index, middle, ring, pinky = extended

        if extended_count == 0:
            return Gesture.FIST, 1.0
        if pinch_ratio <= 0.35:
            confidence = max(0.5, min(1.0, 1.0 - pinch_ratio / 0.7))
            return Gesture.PINCH, confidence
        if index and not middle and not ring and not pinky:
            return Gesture.POINT, 1.0
        if extended_count >= 3:
            return Gesture.OPEN_PALM, extended_count / 4.0
        return Gesture.NONE, 0.0

    def _motion_event(
        self,
        *,
        raw_gesture: Gesture,
        center: Point,
        palm_scale: float,
        pinch_ratio: float,
        timestamp: float,
    ) -> Gesture | None:
        if raw_gesture is Gesture.OPEN_PALM:
            if self._motion_anchor is None:
                self._motion_anchor = (center, timestamp)
            else:
                anchor, started_at = self._motion_anchor
                elapsed = timestamp - started_at
                if elapsed > self.motion_window_seconds:
                    self._motion_anchor = (center, timestamp)
                else:
                    dx = (center[0] - anchor[0]) / palm_scale
                    dy = (center[1] - anchor[1]) / palm_scale
                    if abs(dx) >= self.swipe_threshold and abs(dx) > abs(dy) * 1.3:
                        self._motion_anchor = (center, timestamp)
                        return Gesture.SWIPE_RIGHT if dx > 0 else Gesture.SWIPE_LEFT
                    if abs(dy) >= self.scroll_threshold and abs(dy) > abs(dx) * 1.15:
                        self._motion_anchor = (center, timestamp)
                        return Gesture.SCROLL_DOWN if dy > 0 else Gesture.SCROLL_UP
        else:
            self._motion_anchor = None

        # Track thumb-index distance while the fingers are reasonably close.
        # Increasing distance means zoom in; decreasing distance means zoom out.
        if pinch_ratio <= 0.85 and raw_gesture is not Gesture.FIST:
            if self._pinch_anchor is None:
                self._pinch_anchor = (pinch_ratio, timestamp)
            else:
                anchor_ratio, started_at = self._pinch_anchor
                if timestamp - started_at > self.motion_window_seconds:
                    self._pinch_anchor = (pinch_ratio, timestamp)
                else:
                    delta = pinch_ratio - anchor_ratio
                    if abs(delta) >= self.zoom_threshold:
                        self._pinch_anchor = (pinch_ratio, timestamp)
                        return Gesture.ZOOM_IN if delta > 0 else Gesture.ZOOM_OUT
        else:
            self._pinch_anchor = None
        return None

    def _ema_point(self, previous: Point | None, current: Point) -> Point:
        if previous is None:
            return current
        alpha = self.ema_alpha
        return (
            alpha * current[0] + (1 - alpha) * previous[0],
            alpha * current[1] + (1 - alpha) * previous[1],
        )

    def _ema_value(self, previous: float | None, current: float) -> float:
        if previous is None:
            return current
        return self.ema_alpha * current + (1 - self.ema_alpha) * previous

    @classmethod
    def _finger_extended(
        cls, points: dict[int, Point], tip: int, pip: int, mcp: int
    ) -> bool:
        joint_angle = cls._angle(points[mcp], points[pip], points[tip])
        tip_distance = cls._distance(points[0], points[tip])
        pip_distance = cls._distance(points[0], points[pip])
        return joint_angle >= 145.0 and tip_distance > pip_distance * 1.08

    @staticmethod
    def _to_points(landmarks: Sequence[Landmark]) -> dict[int, Point]:
        points: dict[int, Point] = {}
        for landmark in landmarks:
            if len(landmark) < 3:
                raise ValueError("Each landmark must contain id, x, and y")
            landmark_id = int(landmark[0])
            points[landmark_id] = (float(landmark[1]), float(landmark[2]))
        missing = set(range(21)) - points.keys()
        if missing:
            raise ValueError(f"Expected 21 landmarks; missing ids: {sorted(missing)}")
        return points

    @staticmethod
    def _distance(first: Point, second: Point) -> float:
        return hypot(first[0] - second[0], first[1] - second[1])

    @staticmethod
    def _average(points: Iterable[Point]) -> Point:
        values = list(points)
        return (
            sum(point[0] for point in values) / len(values),
            sum(point[1] for point in values) / len(values),
        )

    @classmethod
    def _angle(cls, first: Point, vertex: Point, third: Point) -> float:
        vector_a = (first[0] - vertex[0], first[1] - vertex[1])
        vector_b = (third[0] - vertex[0], third[1] - vertex[1])
        magnitude = hypot(*vector_a) * hypot(*vector_b)
        if magnitude == 0:
            return 0.0
        cosine = (vector_a[0] * vector_b[0] + vector_a[1] * vector_b[1]) / magnitude
        return degrees(acos(max(-1.0, min(1.0, cosine))))
