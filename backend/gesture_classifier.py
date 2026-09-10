"""Rule-based hand gesture recognition for NEO HandNav.

The classifier consumes the landmark format produced by
``HandTracker.get_landmarks``: ``[landmark_id, x, y, z]`` for all 21 landmarks.
It recognizes static hand shapes plus the existing pinch-distance zoom events.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import acos, degrees, hypot, isfinite, sqrt
from time import monotonic
from typing import Sequence


class Gesture(str, Enum):
    """Gesture labels shared by classification, actions, and the overlay."""

    NONE = "none"
    OPEN_PALM = "open_palm"
    FIST = "fist"
    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"
    POINT = "point"
    PINCH = "pinch"
    TWO_FINGER = "two_finger"
    # Interaction label assigned by the controller after active pointing.
    TWO_FINGER_CLICK = "two_finger_click"
    PREVIOUS_PAGE = "previous_page"
    NEXT_PAGE = "next_page"
    # Backward-compatible aliases for code written before page controls became
    # static orientation poses.
    SWIPE_LEFT = "previous_page"
    SWIPE_RIGHT = "next_page"
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
    """Classify hand shapes using MediaPipe landmark geometry.

    Labels require a few consecutive frames. Page and scroll controls depend
    on the static direction of the index/middle pair; zoom continues to use
    the normalized distance between the thumb and index fingertips.
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

    def __init__(
        self,
        *,
        ema_alpha: float = 0.35,
        min_stable_frames: int = 3,
        zoom_threshold: float = 0.12,
        zoom_window_seconds: float = 0.8,
        horizontal_direction_threshold: float = 0.55,
        vertical_direction_threshold: float = 0.72,
        diagonal_page_threshold: float = 0.30,
        finger_alignment_threshold: float = 0.70,
        direction_settle_seconds: float = 0.22,
        direction_stillness_radius: float = 0.10,
        max_frame_gap_seconds: float = 0.5,
        fist_settle_seconds: float = 0.15,
        zoom_enabled: bool = True,
    ) -> None:
        if not 0 < ema_alpha <= 1:
            raise ValueError("ema_alpha must be between 0 and 1")
        if min_stable_frames < 1:
            raise ValueError("min_stable_frames must be at least 1")
        if not isinstance(min_stable_frames, int):
            raise ValueError("min_stable_frames must be an integer")
        for name, value in (
            ("zoom_window_seconds", zoom_window_seconds),
            ("direction_settle_seconds", direction_settle_seconds),
            ("direction_stillness_radius", direction_stillness_radius),
            ("fist_settle_seconds", fist_settle_seconds),
        ):
            if not isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        if not isfinite(zoom_threshold) or zoom_threshold <= 0:
            raise ValueError("zoom_threshold must be positive and finite")
        if not isfinite(max_frame_gap_seconds) or max_frame_gap_seconds <= 0:
            raise ValueError("max_frame_gap_seconds must be positive and finite")
        if zoom_window_seconds <= 0:
            raise ValueError("zoom_window_seconds must be positive")
        if not 0 < horizontal_direction_threshold <= 1:
            raise ValueError(
                "horizontal_direction_threshold must be between 0 and 1"
            )
        if not 0 < vertical_direction_threshold <= 1:
            raise ValueError(
                "vertical_direction_threshold must be between 0 and 1"
            )
        if not 0 < diagonal_page_threshold <= horizontal_direction_threshold:
            raise ValueError(
                "diagonal_page_threshold must be positive and no greater "
                "than horizontal_direction_threshold"
            )
        if not -1 <= finger_alignment_threshold <= 1:
            raise ValueError(
                "finger_alignment_threshold must be between -1 and 1"
            )
        if direction_settle_seconds < 0:
            raise ValueError("direction_settle_seconds must be non-negative")
        if direction_stillness_radius <= 0:
            raise ValueError("direction_stillness_radius must be positive")

        self.ema_alpha = ema_alpha
        self.min_stable_frames = min_stable_frames
        self.zoom_threshold = zoom_threshold
        self.zoom_window_seconds = zoom_window_seconds
        self.horizontal_direction_threshold = horizontal_direction_threshold
        self.vertical_direction_threshold = vertical_direction_threshold
        self.diagonal_page_threshold = diagonal_page_threshold
        self.finger_alignment_threshold = finger_alignment_threshold
        self.direction_settle_seconds = direction_settle_seconds
        self.direction_stillness_radius = direction_stillness_radius
        self.max_frame_gap_seconds = max_frame_gap_seconds
        self.fist_settle_seconds = fist_settle_seconds
        self.zoom_enabled = zoom_enabled
        self.reset()

    def reset(self) -> None:
        """Clear temporal state after the tracked hand disappears."""

        self._filtered_pinch_ratio: float | None = None
        self._filtered_depths: dict[int, float] = {}
        self._pinch_anchor: tuple[float, float] | None = None
        self._pinch_active = False
        self._pinch_start_frames = 0
        self._candidate = Gesture.NONE
        self._candidate_frames = 0
        self._candidate_started_at: float | None = None
        self._direction_candidate = Gesture.NONE
        self._direction_anchor_point: Point2D | None = None
        self._direction_anchor_scale = 1.0
        self._direction_settle_started_at: float | None = None
        self._direction_settled = False
        self._last_timestamp: float | None = None

    def classify(
        self,
        landmarks: Sequence[Landmark],
        timestamp: float | None = None,
        image_width: float | None = None,
        *,
        click_context: bool = False,
    ) -> GestureResult:
        """Return the current stable shape or a pinch-distance zoom event.

        ``image_width`` should be supplied for webcam input. MediaPipe reports
        normalized z but this project stores x/y as pixels, so the width makes
        all three axes comparable. The palm-size estimate remains as a fallback
        for callers that only have the landmark list.
        """

        if image_width is not None and (not isfinite(image_width) or image_width <= 0):
            self.reset()
            raise ValueError("image_width must be positive")

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
        try:
            points = self._to_points(landmarks)
        except (ValueError, TypeError, OverflowError):
            self.reset()
            raise ValueError(
                "Expected 21 unique finite landmarks with id, x, y, and z"
            ) from None
        # A collapsed palm or missing-length finger bone is tracking failure,
        # not evidence that every finger is folded into a fist.
        if (
            self._distance_2d(points[0], points[9]) < 1e-6
            or self._distance_2d(points[5], points[17]) < 1e-6
            or any(
                self._distance_3d(points[a], points[b], image_width or 1) < 1e-6
                for tip, dip, pip, mcp in self._FINGERS
                for a, b in ((mcp, pip), (pip, dip), (dip, tip))
            )
        ):
            self.reset()
            raise ValueError("Collapsed palm or finger landmarks")
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
        observed_pinch_ratio = pinch_ratio
        pinch_ratio = self._ema_value(self._filtered_pinch_ratio, pinch_ratio)
        self._filtered_pinch_ratio = pinch_ratio

        index, middle, ring, pinky = extended
        pinch_start_pose = (
            index_extended_in_image and not middle and not ring and not pinky
        )
        pinch_continue_pose = index and not middle and not ring and not pinky
        two_finger_pose = self._two_finger_pose(extended_in_image, extended)
        # Directional controls need positive evidence of folded ring/pinky,
        # rather than treating any uncertain projection as a closed finger.
        two_finger_pose = two_finger_pose and all(
            self._angle_2d(points[mcp], points[pip], points[tip]) < 120
            for tip, _, pip, mcp in self._FINGERS[2:]
        )
        if click_context and self._click_pose(points, extended, depth_scale):
            # Click intent was established by pointing. It does not require
            # parallel fingers, a screen direction, or 2D-only extension.
            # PointerController owns the time-based click confirmation; do not
            # add a second consecutive-frame debounce that resets on jitter.
            self._reset_direction_settle()
            self._pinch_active = False
            self._pinch_anchor = None
            self._pinch_start_frames = 0
            self._candidate = Gesture.NONE
            self._candidate_frames = 0
            return GestureResult(Gesture.TWO_FINGER_CLICK, .85)
        raw_gesture, confidence = self._static_shape(
            extended,
            pinch_ratio,
            pinch_start_pose,
            two_finger_pose,
        )
        if raw_gesture is Gesture.POINT and pinch_start_pose and observed_pinch_ratio <= self._PINCH_START_THRESHOLD:
            # Smoothing may take several frames to catch a newly closed pinch.
            # Do not move the cursor or consume the navigation gate meanwhile.
            raw_gesture, confidence = Gesture.NONE, 0.0
        if raw_gesture is Gesture.FIST and not all(
            self._angle_2d(points[mcp], points[pip], points[tip]) < 120
            for tip, _, pip, mcp in self._FINGERS
        ):
            raw_gesture, confidence = Gesture.NONE, 0.0
        if raw_gesture is Gesture.FIST:
            # A thumb was previously ignored completely, so thumbs-up sent
            # Space. Distinguish it from a closed thumb using palm-relative
            # reach and the thumb's IP joint, for either hand.
            thumb_straight = self._angle_3d(
                points[2], points[3], points[4], depth_scale
            ) >= 145
            thumb_outside_palm = (
                self._distance_3d(points[4], points[5], depth_scale) / palm_scale > .65
                and self._distance_3d(points[0], points[4], depth_scale)
                > self._distance_3d(points[0], points[2], depth_scale) * 1.15
            )
            if thumb_straight and thumb_outside_palm:
                dx, dy = points[4][0] - points[2][0], points[4][1] - points[2][1]
                length = hypot(dx, dy)
                if length >= palm_scale * .35 and dy / length <= -.65:
                    raw_gesture = Gesture.THUMBS_UP
                elif length >= palm_scale * .35 and dy / length >= .65:
                    raw_gesture = Gesture.THUMBS_DOWN
                else:
                    raw_gesture, confidence = Gesture.NONE, 0.0
        direction_is_settled = False
        if raw_gesture is Gesture.TWO_FINGER:
            directed_gesture, direction_confidence = self._two_finger_direction(
                points
            )
            if directed_gesture is not None:
                confidence = direction_confidence
                control_point = (
                    (points[8][0] + points[12][0]) / 2.0,
                    (points[8][1] + points[12][1]) / 2.0,
                )
                direction_is_settled = self._direction_pose_is_settled(
                    directed_gesture,
                    control_point,
                    palm_scale,
                    now,
                )
                if direction_is_settled:
                    raw_gesture = directed_gesture
            else:
                self._reset_direction_settle()
        else:
            self._reset_direction_settle()

        zoom = self._zoom_event(
            raw_gesture=raw_gesture,
            pinch_ratio=pinch_ratio,
            pinch_start_pose=pinch_start_pose,
            pinch_continue_pose=pinch_continue_pose,
            timestamp=now,
        ) if self.zoom_enabled else None
        if zoom is not None:
            self._candidate = Gesture.NONE
            self._candidate_frames = 0
            return GestureResult(zoom, 1.0)

        # Directional poses already pass a time-based stillness check, so they
        # do not need another frame-count delay. This behaves consistently at
        # different webcam frame rates.
        if direction_is_settled:
            self._candidate = raw_gesture
            self._candidate_frames = self.min_stable_frames
            return GestureResult(raw_gesture, confidence)

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
            self._candidate_started_at = now

        if raw_gesture is Gesture.NONE:
            return GestureResult(Gesture.NONE, 0.0)
        if self._candidate_frames < self.min_stable_frames:
            return GestureResult(Gesture.NONE, confidence)
        if (
            raw_gesture is Gesture.FIST and self._candidate_started_at is not None
            and now - self._candidate_started_at < self.fist_settle_seconds
        ):
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

    def _zoom_event(
        self,
        *,
        raw_gesture: Gesture,
        pinch_ratio: float,
        pinch_start_pose: bool,
        pinch_continue_pose: bool,
        timestamp: float,
    ) -> Gesture | None:
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
            if timestamp - started_at > self.zoom_window_seconds:
                self._pinch_anchor = (pinch_ratio, timestamp)
            else:
                delta = pinch_ratio - anchor_ratio
                if abs(delta) >= self.zoom_threshold:
                    self._pinch_anchor = (pinch_ratio, timestamp)
                    return Gesture.ZOOM_IN if delta > 0 else Gesture.ZOOM_OUT
        return None

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
        distal_angle_3d = cls._angle_3d(
            points[pip], points[dip], points[tip], depth_scale
        )
        tip_distance_3d = cls._distance_3d(points[0], points[tip], depth_scale)
        pip_distance_3d = cls._distance_3d(points[0], points[pip], depth_scale)
        extended_in_3d = (
            joint_angle_3d >= 135.0
            and distal_angle_3d >= 135.0
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
            and distal_angle_3d >= 135.0
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
        distal_angle = cls._angle_2d(points[pip], points[tip - 1], points[tip])
        return (
            joint_angle >= 145.0 and distal_angle >= 135.0
            and tip_distance > pip_distance * 1.08
        )

    @staticmethod
    def _two_finger_pose(
        extended_in_image: Sequence[bool],
        extended: Sequence[bool],
    ) -> bool:
        index, middle, ring, pinky = extended_in_image
        return index and middle and not ring and not pinky and not any(extended[2:])

    @classmethod
    def _click_pose(cls, points, extended, depth_scale):
        """A deliberate V after pointing, allowing perspective and mild bends.

        Require both raised fingers and positive curled evidence for the other
        pair. Depth helps oblique hands; distal bends still reject hooked fingers.
        This rule is never used to initiate scrolling or browser navigation.
        """
        for index, (tip, dip, pip, mcp) in enumerate(cls._FINGERS):
            bend = cls._angle_3d(points[mcp], points[pip], points[tip], depth_scale)
            distal = cls._angle_3d(points[pip], points[dip], points[tip], depth_scale)
            bones = sum(cls._distance_3d(points[a], points[b], depth_scale)
                        for a,b in ((mcp,pip),(pip,dip),(dip,tip)))
            straightness = cls._distance_3d(points[mcp], points[tip], depth_scale)/max(bones,1e-6)
            if index < 2:
                raised = (bend >= 125 and distal >= 120 and straightness >= .82
                          and cls._distance_3d(points[0], points[tip], depth_scale)
                          > cls._distance_3d(points[0], points[pip], depth_scale)*1.03)
                if not (extended[index] or raised):
                    return False
            elif (extended[index] or not (
                bend < 120 or cls._angle_2d(points[mcp], points[pip], points[tip]) < 120
                or straightness < .65
            )):
                return False
        return True

    def _two_finger_direction(
        self,
        points: dict[int, Point3D],
    ) -> tuple[Gesture | None, float]:
        """Map the static direction of the index/middle pair to a control.

        Each direction uses the finger's MCP-to-tip vector, so moving the whole
        hand around the frame does not change the command. Both fingers must be
        sufficiently parallel before a direction is accepted.
        """

        directions: list[Point2D] = []
        palm_scale = max(
            self._distance_2d(points[0], points[9]),
            self._distance_2d(points[5], points[17]),
        )
        for mcp_id, tip_id in ((5, 8), (9, 12)):
            dx = points[tip_id][0] - points[mcp_id][0]
            dy = points[tip_id][1] - points[mcp_id][1]
            length = hypot(dx, dy)
            if length < palm_scale * 0.5:
                return None, 0.0
            directions.append((dx / length, dy / length))

        alignment = (
            directions[0][0] * directions[1][0]
            + directions[0][1] * directions[1][1]
        )
        if alignment < self.finger_alignment_threshold:
            return None, 0.0

        average_x = directions[0][0] + directions[1][0]
        average_y = directions[0][1] + directions[1][1]
        average_length = hypot(average_x, average_y)
        if average_length == 0:
            return None, 0.0
        direction_x = average_x / average_length
        direction_y = average_y / average_length

        # Check ordinary horizontal poses first. A right hand often cannot
        # rotate far enough for a perfectly horizontal Next Page pose, so an
        # upper diagonal is also treated as a page direction. Scroll Up keeps
        # a narrow vertical lane, preventing that ergonomic pose from becoming
        # an accidental upward scroll. The same rule supports left hands too.
        if (
            direction_x >= self.horizontal_direction_threshold
            and abs(direction_y) <= self.vertical_direction_threshold
        ):
            return Gesture.NEXT_PAGE, direction_x
        if (
            direction_x <= -self.horizontal_direction_threshold
            and abs(direction_y) <= self.vertical_direction_threshold
        ):
            return Gesture.PREVIOUS_PAGE, -direction_x
        if direction_y <= -self.vertical_direction_threshold:
            if direction_x >= self.diagonal_page_threshold:
                return Gesture.NEXT_PAGE, direction_x
            if direction_x <= -self.diagonal_page_threshold:
                return Gesture.PREVIOUS_PAGE, -direction_x
        if direction_y <= -self.vertical_direction_threshold:
            return Gesture.SCROLL_UP, -direction_y
        if direction_y >= self.vertical_direction_threshold:
            return Gesture.SCROLL_DOWN, direction_y
        return None, 0.0

    def _direction_pose_is_settled(
        self,
        gesture: Gesture,
        control_point: Point2D,
        palm_scale: float,
        timestamp: float,
    ) -> bool:
        """Require a directional pose to stop moving before it is accepted."""

        if (
            gesture is not self._direction_candidate
            or self._direction_anchor_point is None
            or self._direction_settle_started_at is None
        ):
            self._direction_candidate = gesture
            self._direction_anchor_point = control_point
            self._direction_anchor_scale = palm_scale
            self._direction_settle_started_at = timestamp
            self._direction_settled = self.direction_settle_seconds == 0
            return self.direction_settle_seconds == 0

        # Stillness is an entry check. Once accepted, translating the same
        # pose must not periodically stop/restart a held scroll.
        if self._direction_settled:
            return True

        scale = max(palm_scale, self._direction_anchor_scale, 1.0)
        displacement = (
            hypot(
                control_point[0] - self._direction_anchor_point[0],
                control_point[1] - self._direction_anchor_point[1],
            )
            / scale
        )
        if displacement > self.direction_stillness_radius:
            self._direction_anchor_point = control_point
            self._direction_anchor_scale = palm_scale
            self._direction_settle_started_at = timestamp
            return self.direction_settle_seconds == 0

        self._direction_settled = (
            timestamp - self._direction_settle_started_at
            >= self.direction_settle_seconds
        )
        return self._direction_settled

    def _reset_direction_settle(self) -> None:
        self._direction_candidate = Gesture.NONE
        self._direction_anchor_point = None
        self._direction_anchor_scale = 1.0
        self._direction_settle_started_at = None
        self._direction_settled = False

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
            if (
                landmark_id != landmark[0]
                or landmark_id not in range(21)
                or landmark_id in points
            ):
                raise ValueError("Landmark ids must be unique integers from 0 to 20")
            points[landmark_id] = (
                float(landmark[1]),
                float(landmark[2]),
                float(landmark[3]),
            )
            if not all(isfinite(value) for value in points[landmark_id]):
                raise ValueError("Landmark coordinates must be finite")
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
