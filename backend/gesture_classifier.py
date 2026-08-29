"""Rule-based hand gesture recognition for NEO HandNav.

The classifier consumes the landmark format produced by
``HandTracker.get_landmarks``: ``[landmark_id, x, y, z]`` for all 21 landmarks.
It recognizes static hand shapes and turns deliberate hand motion into events.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import acos, degrees, hypot, sqrt
from time import monotonic
from typing import Iterable, Sequence


class Gesture(str, Enum):
    """Gesture labels shared by classification, actions, and the overlay."""

    NONE = "none"
    OPEN_PALM = "open_palm"
    FIST = "fist"
    POINT = "point"
    PINCH = "pinch"
    TWO_FINGER = "two_finger"
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


Point2D = tuple[float, float]
Point3D = tuple[float, float, float]
Landmark = Sequence[int | float]


class GestureClassifier:
    """Classify hand shapes and motion using MediaPipe landmark geometry.

    Static labels require a few consecutive frames. Swipe, scroll, and zoom
    are emitted as short motion events. Coordinates are normalized by palm
    size so thresholds remain useful when the hand moves closer to the camera.
    """

    _FINGERS = (
        (8, 7, 6, 5),
        (12, 11, 10, 9),
        (16, 15, 14, 13),
        (20, 19, 18, 17),
    )
    # MediaPipe z is normalized while Thinh's x/y output is in pixels. Scaling
    # z relative to palm size gives depth enough weight for fingers directed
    # toward the camera without requiring the original frame dimensions.
    _DEPTH_GAIN = 5.0
    _FORWARD_DEPTH_THRESHOLD = 0.28
    _FORWARD_TIP_THRESHOLD = 0.10
    _DEPTH_BACKTRACK_TOLERANCE = 0.10
    _MIN_PROJECTED_ANGLE_FOR_DEPTH = 75.0
    _PINCH_START_THRESHOLD = 0.35
    _FOLDED_TIP_RATIO = 0.82

    def __init__(
        self,
        *,
        ema_alpha: float = 0.35,
        min_stable_frames: int = 3,
        swipe_threshold: float = 0.55,
        scroll_threshold: float = 0.55,
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

        self._filtered_motion_point: Point2D | None = None
        self._filtered_pinch_ratio: float | None = None
        self._filtered_depths: dict[int, float] = {}
        self._motion_anchor: tuple[Point2D, float] | None = None
        self._two_finger_frames = 0
        self._pinch_anchor: tuple[float, float] | None = None
        self._pinch_active = False
        self._pinch_start_frames = 0
        self._candidate = Gesture.NONE
        self._candidate_frames = 0

    def classify(
        self,
        landmarks: Sequence[Landmark],
        timestamp: float | None = None,
        image_width: float | None = None,
    ) -> GestureResult:
        """Return the current stable shape or a deliberate motion event.

        ``image_width`` should be supplied for webcam input. MediaPipe reports
        normalized z but this project stores x/y as pixels, so the width makes
        all three axes comparable. The palm-size estimate remains as a fallback
        for callers that only have the landmark list.
        """

        if image_width is not None and image_width <= 0:
            raise ValueError("image_width must be positive")

        now = monotonic() if timestamp is None else timestamp
        points = self._to_points(landmarks)
        points = self._smooth_depths(points)
        palm_scale = max(
            self._distance_2d(points[0], points[9]),
            self._distance_2d(points[5], points[17]),
            1.0,
        )
        depth_scale = (
            float(image_width)
            if image_width is not None
            else palm_scale * self._DEPTH_GAIN
        )
        extended = [
            self._finger_extended(
                points,
                tip,
                dip,
                pip,
                mcp,
                palm_scale,
                depth_scale,
            )
            for tip, dip, pip, mcp in self._FINGERS
        ]
        extended_in_image = [
            self._finger_extended_in_image(points, tip, pip, mcp)
            for tip, _, pip, mcp in self._FINGERS
        ]
        index_extended_in_image = extended_in_image[0]
        pinch_ratio = (
            self._distance_3d(points[4], points[8], depth_scale) / palm_scale
        )
        pinch_ratio = self._ema_value(self._filtered_pinch_ratio, pinch_ratio)
        self._filtered_pinch_ratio = pinch_ratio

        index, middle, ring, pinky = extended
        pinch_start_pose = (
            index_extended_in_image and not middle and not ring and not pinky
        )
        pinch_continue_pose = index and not middle and not ring and not pinky
        two_finger_pose = self._two_finger_pose(points, extended_in_image)
        raw_gesture, confidence = self._static_shape(
            extended,
            pinch_ratio,
            pinch_start_pose,
            two_finger_pose,
        )
        control_point_3d = self._average(points[index] for index in (8, 12))
        control_point = (control_point_3d[0], control_point_3d[1])
        motion = self._motion_event(
            raw_gesture=raw_gesture,
            control_point=control_point,
            palm_scale=palm_scale,
            pinch_ratio=pinch_ratio,
            pinch_start_pose=pinch_start_pose,
            pinch_continue_pose=pinch_continue_pose,
            timestamp=now,
        )
        if motion is not None:
            self._candidate = Gesture.NONE
            self._candidate_frames = 0
            return GestureResult(motion, 1.0)

        # Pinch is a persistent interaction mode, while zoom is a momentary
        # event inside that mode. Once armed, do not expose the underlying
        # index-only shape as Point between zoom events; that is confusing to
        # the user and can make downstream cursor logic activate by mistake.
        if self._pinch_active:
            self._candidate = Gesture.PINCH
            self._candidate_frames = self.min_stable_frames
            pinch_confidence = max(
                0.5,
                min(1.0, 1.15 - pinch_ratio * 0.5),
            )
            return GestureResult(Gesture.PINCH, pinch_confidence)

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

    @classmethod
    def _static_shape(
        cls,
        extended: Sequence[bool],
        pinch_ratio: float,
        pinch_start_pose: bool,
        two_finger_pose: bool,
    ) -> tuple[Gesture, float]:
        extended_count = sum(extended)
        index, middle, ring, pinky = extended

        # Keep pose rules mutually exclusive. A closed fist often places the
        # thumb and index tips close together, but that alone is not a pinch.
        if extended_count == 0:
            return Gesture.FIST, 1.0
        if pinch_start_pose and pinch_ratio <= cls._PINCH_START_THRESHOLD:
            confidence = max(0.5, min(1.0, 1.0 - pinch_ratio / 0.7))
            return Gesture.PINCH, confidence
        if two_finger_pose:
            return Gesture.TWO_FINGER, 1.0
        if index and not middle and not ring and not pinky:
            return Gesture.POINT, 1.0
        if extended_count >= 3:
            return Gesture.OPEN_PALM, extended_count / 4.0
        return Gesture.NONE, 0.0

    def _motion_event(
        self,
        *,
        raw_gesture: Gesture,
        control_point: Point2D,
        palm_scale: float,
        pinch_ratio: float,
        pinch_start_pose: bool,
        pinch_continue_pose: bool,
        timestamp: float,
    ) -> Gesture | None:
        # Swipe and scroll use the midpoint of the index and middle fingertips.
        # The ring and pinky must stay folded so an ordinary open hand remains
        # a neutral pose instead of accidentally moving the page.
        if raw_gesture is Gesture.TWO_FINGER:
            self._two_finger_frames += 1
            if self._two_finger_frames >= self.min_stable_frames:
                control_point = self._ema_point(
                    self._filtered_motion_point, control_point
                )
                self._filtered_motion_point = control_point
                if self._motion_anchor is None:
                    self._motion_anchor = (control_point, timestamp)
                else:
                    anchor, started_at = self._motion_anchor
                    elapsed = timestamp - started_at
                    if elapsed > self.motion_window_seconds:
                        self._motion_anchor = (control_point, timestamp)
                    else:
                        dx = (control_point[0] - anchor[0]) / palm_scale
                        dy = (control_point[1] - anchor[1]) / palm_scale
                        if (
                            abs(dx) >= self.swipe_threshold
                            and abs(dx) > abs(dy) * 1.3
                        ):
                            self._motion_anchor = (control_point, timestamp)
                            return (
                                Gesture.SWIPE_RIGHT
                                if dx > 0
                                else Gesture.SWIPE_LEFT
                            )
                        if (
                            abs(dy) >= self.scroll_threshold
                            and abs(dy) > abs(dx) * 1.15
                        ):
                            self._motion_anchor = (control_point, timestamp)
                            return (
                                Gesture.SCROLL_DOWN
                                if dy > 0
                                else Gesture.SCROLL_UP
                            )
            else:
                self._motion_anchor = None
                self._filtered_motion_point = None
        else:
            self._two_finger_frames = 0
            self._motion_anchor = None
            self._filtered_motion_point = None

        # Pinch starts only when the thumb and index tips are close. Once armed,
        # opening that distance zooms in and closing it zooms out. Extending the
        # middle, ring, or pinky immediately cancels pinch mode.
        if not self._pinch_active:
            if (
                pinch_start_pose
                and pinch_ratio <= self._PINCH_START_THRESHOLD
            ):
                self._pinch_start_frames += 1
                if self._pinch_start_frames >= self.min_stable_frames:
                    self._pinch_active = True
                    self._pinch_anchor = (pinch_ratio, timestamp)
            else:
                self._pinch_start_frames = 0
        elif not pinch_continue_pose or raw_gesture is Gesture.FIST:
            self._pinch_active = False
            self._pinch_start_frames = 0
            self._pinch_anchor = None
        elif self._pinch_anchor is None:
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
        return None

    def _ema_point(self, previous: Point2D | None, current: Point2D) -> Point2D:
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
        cls,
        points: dict[int, Point3D],
        tip: int,
        dip: int,
        pip: int,
        mcp: int,
        palm_scale: float,
        depth_scale: float,
    ) -> bool:
        extended_in_image = cls._finger_extended_in_image(
            points, tip, pip, mcp
        )
        joint_angle_2d = cls._angle_2d(
            points[mcp], points[pip], points[tip]
        )

        joint_angle_3d = cls._angle_3d(
            points[mcp], points[pip], points[tip], depth_scale
        )
        tip_distance_3d = cls._distance_3d(points[0], points[tip], depth_scale)
        pip_distance_3d = cls._distance_3d(points[0], points[pip], depth_scale)
        extended_in_3d = (
            joint_angle_3d >= 135.0
            and joint_angle_2d >= cls._MIN_PROJECTED_ANGLE_FOR_DEPTH
            and tip_distance_3d > pip_distance_3d * 1.05
        )

        # A finger aimed at the camera is heavily foreshortened: its x/y
        # joints overlap even though MediaPipe's z values still move steadily
        # toward the camera (smaller z). Permit a little backtracking because
        # monocular depth estimates naturally jitter between frames.
        depth_steps = (
            (points[mcp][2] - points[pip][2]) * depth_scale / palm_scale,
            (points[pip][2] - points[dip][2]) * depth_scale / palm_scale,
            (points[dip][2] - points[tip][2]) * depth_scale / palm_scale,
        )
        total_forward_depth = sum(depth_steps)
        tip_forward_depth = (
            (points[pip][2] - points[tip][2]) * depth_scale / palm_scale
        )
        depth_is_consistent = min(depth_steps) >= -cls._DEPTH_BACKTRACK_TOLERANCE
        extended_toward_camera = (
            total_forward_depth >= cls._FORWARD_DEPTH_THRESHOLD
            and tip_forward_depth >= cls._FORWARD_TIP_THRESHOLD
            and depth_is_consistent
            and joint_angle_3d >= 115.0
            and joint_angle_2d >= cls._MIN_PROJECTED_ANGLE_FOR_DEPTH
            and tip_distance_3d > pip_distance_3d * 1.02
        )
        return extended_in_image or extended_in_3d or extended_toward_camera

    @classmethod
    def _finger_extended_in_image(
        cls,
        points: dict[int, Point3D],
        tip: int,
        pip: int,
        mcp: int,
    ) -> bool:
        joint_angle = cls._angle_2d(points[mcp], points[pip], points[tip])
        tip_distance = cls._distance_2d(points[0], points[tip])
        pip_distance = cls._distance_2d(points[0], points[pip])
        return joint_angle >= 145.0 and tip_distance > pip_distance * 1.08

    @classmethod
    def _two_finger_pose(
        cls,
        points: dict[int, Point3D],
        extended_in_image: Sequence[bool],
    ) -> bool:
        index, middle, _, _ = extended_in_image
        if not index or not middle:
            return False

        control_length = min(
            cls._distance_2d(points[0], points[8]),
            cls._distance_2d(points[0], points[12]),
        )
        folded_limit = control_length * cls._FOLDED_TIP_RATIO
        return (
            cls._distance_2d(points[0], points[16]) < folded_limit
            and cls._distance_2d(points[0], points[20]) < folded_limit
        )

    def _smooth_depths(
        self, points: dict[int, Point3D]
    ) -> dict[int, Point3D]:
        smoothed: dict[int, Point3D] = {}
        for landmark_id, (x, y, z) in points.items():
            previous = self._filtered_depths.get(landmark_id)
            filtered_z = self._ema_value(previous, z)
            self._filtered_depths[landmark_id] = filtered_z
            smoothed[landmark_id] = (x, y, filtered_z)
        return smoothed

    @staticmethod
    def _to_points(landmarks: Sequence[Landmark]) -> dict[int, Point3D]:
        points: dict[int, Point3D] = {}
        for landmark in landmarks:
            if len(landmark) < 4:
                raise ValueError("Each landmark must contain id, x, y, and z")
            landmark_id = int(landmark[0])
            points[landmark_id] = (
                float(landmark[1]),
                float(landmark[2]),
                float(landmark[3]),
            )
        missing = set(range(21)) - points.keys()
        if missing:
            raise ValueError(f"Expected 21 landmarks; missing ids: {sorted(missing)}")
        return points

    @staticmethod
    def _distance_2d(first: Point3D, second: Point3D) -> float:
        return hypot(first[0] - second[0], first[1] - second[1])

    @classmethod
    def _distance_3d(
        cls, first: Point3D, second: Point3D, depth_scale: float
    ) -> float:
        dx = first[0] - second[0]
        dy = first[1] - second[1]
        dz = (first[2] - second[2]) * depth_scale
        return sqrt(dx * dx + dy * dy + dz * dz)

    @staticmethod
    def _average(points: Iterable[Point3D]) -> Point3D:
        values = list(points)
        return (
            sum(point[0] for point in values) / len(values),
            sum(point[1] for point in values) / len(values),
            sum(point[2] for point in values) / len(values),
        )

    @classmethod
    def _angle_2d(cls, first: Point3D, vertex: Point3D, third: Point3D) -> float:
        vector_a = (first[0] - vertex[0], first[1] - vertex[1])
        vector_b = (third[0] - vertex[0], third[1] - vertex[1])
        magnitude = hypot(*vector_a) * hypot(*vector_b)
        if magnitude == 0:
            return 0.0
        cosine = (vector_a[0] * vector_b[0] + vector_a[1] * vector_b[1]) / magnitude
        return degrees(acos(max(-1.0, min(1.0, cosine))))

    @classmethod
    def _angle_3d(
        cls,
        first: Point3D,
        vertex: Point3D,
        third: Point3D,
        depth_scale: float,
    ) -> float:
        vector_a = (
            first[0] - vertex[0],
            first[1] - vertex[1],
            (first[2] - vertex[2]) * depth_scale,
        )
        vector_b = (
            third[0] - vertex[0],
            third[1] - vertex[1],
            (third[2] - vertex[2]) * depth_scale,
        )
        magnitude_a = sqrt(sum(value * value for value in vector_a))
        magnitude_b = sqrt(sum(value * value for value in vector_b))
        magnitude = magnitude_a * magnitude_b
        if magnitude == 0:
            return 0.0
        dot_product = sum(a * b for a, b in zip(vector_a, vector_b))
        cosine = dot_product / magnitude
        return degrees(acos(max(-1.0, min(1.0, cosine))))
