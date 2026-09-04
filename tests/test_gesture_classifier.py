from __future__ import annotations

import math
import unittest

from backend.gesture_classifier import Gesture, GestureClassifier


OPEN_HAND = [
    [landmark_id, x, y, 0.0]
    for landmark_id, x, y in [
        [0, 100, 220],
        [1, 75, 190],
        [2, 60, 165],
        [3, 50, 140],
        [4, 40, 115],
        [5, 75, 160],
        [6, 75, 120],
        [7, 75, 80],
        [8, 75, 40],
        [9, 95, 150],
        [10, 95, 105],
        [11, 95, 65],
        [12, 95, 25],
        [13, 115, 155],
        [14, 115, 115],
        [15, 115, 80],
        [16, 115, 45],
        [17, 135, 165],
        [18, 135, 130],
        [19, 135, 100],
        [20, 135, 70],
    ]
]


def copy_hand(hand=OPEN_HAND):
    return [landmark.copy() for landmark in hand]


def fold_finger(hand, pip_id: int, dip_id: int, tip_id: int) -> None:
    pip_x, pip_y = hand[pip_id][1], hand[pip_id][2]
    hand[dip_id][1:3] = [pip_x + 8, pip_y + 20]
    hand[tip_id][1:3] = [pip_x + 5, pip_y + 45]


def orient_finger(
    hand,
    mcp_id: int,
    pip_id: int,
    dip_id: int,
    tip_id: int,
    direction: tuple[float, float],
) -> None:
    base_x, base_y = hand[mcp_id][1], hand[mcp_id][2]
    unit_x, unit_y = direction
    for landmark_id, distance in (
        (pip_id, 40),
        (dip_id, 80),
        (tip_id, 120),
    ):
        hand[landmark_id][1:3] = [
            base_x + unit_x * distance,
            base_y + unit_y * distance,
        ]


def translated(hand, dx=0, dy=0):
    return [
        [landmark_id, x + dx, y + dy, z]
        for landmark_id, x, y, z in hand
    ]


def two_finger_hand(direction: tuple[float, float] = (0.0, -1.0)):
    hand = copy_hand()
    orient_finger(hand, 5, 6, 7, 8, direction)
    orient_finger(hand, 9, 10, 11, 12, direction)
    for pip, dip, tip in ((14, 15, 16), (18, 19, 20)):
        fold_finger(hand, pip, dip, tip)
    return hand


def fist_hand():
    hand = copy_hand()
    for pip, dip, tip in (
        (6, 7, 8),
        (10, 11, 12),
        (14, 15, 16),
        (18, 19, 20),
    ):
        fold_finger(hand, pip, dip, tip)
    return hand


def point_hand():
    hand = copy_hand()
    for pip, dip, tip in ((10, 11, 12), (14, 15, 16), (18, 19, 20)):
        fold_finger(hand, pip, dip, tip)
    return hand


def pinch_hand():
    hand = point_hand()
    hand[4][1:3] = [77, 42]
    return hand


class GestureClassifierTests(unittest.TestCase):
    @staticmethod
    def classifier(**overrides):
        settings = {
            "ema_alpha": 1.0,
            "min_stable_frames": 1,
            "zoom_threshold": 0.10,
            "direction_settle_seconds": 0.0,
        }
        settings.update(overrides)
        return GestureClassifier(**settings)

    def test_open_palm(self):
        result = self.classifier().classify(copy_hand(), timestamp=0.0)
        self.assertEqual(result.gesture, Gesture.OPEN_PALM)

    def test_fist(self):
        result = self.classifier().classify(fist_hand(), timestamp=0.0)
        self.assertEqual(result.gesture, Gesture.FIST)

    def test_point(self):
        result = self.classifier().classify(point_hand(), timestamp=0.0)
        self.assertEqual(result.gesture, Gesture.POINT)

    def test_pinch(self):
        result = self.classifier().classify(pinch_hand(), timestamp=0.0)
        self.assertEqual(result.gesture, Gesture.PINCH)

    def test_fist_is_not_pinch_when_thumb_and_index_are_close(self):
        hand = fist_hand()
        hand[4][1:] = hand[8][1:]

        result = self.classifier().classify(hand, timestamp=0.0)

        self.assertEqual(result.gesture, Gesture.FIST)

    def test_open_palm_is_not_pinch_when_tips_overlap(self):
        hand = copy_hand()
        hand[4][1:] = hand[8][1:]

        result = self.classifier().classify(hand, timestamp=0.0)

        self.assertEqual(result.gesture, Gesture.OPEN_PALM)

    def test_static_two_finger_up_means_scroll_up(self):
        result = self.classifier().classify(
            two_finger_hand((0.0, -1.0)), timestamp=0.0
        )
        self.assertEqual(result.gesture, Gesture.SCROLL_UP)

    def test_static_two_finger_down_means_scroll_down(self):
        result = self.classifier().classify(
            two_finger_hand((0.0, 1.0)), timestamp=0.0
        )
        self.assertEqual(result.gesture, Gesture.SCROLL_DOWN)

    def test_static_two_finger_left_means_previous_page(self):
        result = self.classifier().classify(
            two_finger_hand((-1.0, 0.0)), timestamp=0.0
        )
        self.assertEqual(result.gesture, Gesture.PREVIOUS_PAGE)

    def test_static_two_finger_right_means_next_page(self):
        result = self.classifier().classify(
            two_finger_hand((1.0, 0.0)), timestamp=0.0
        )
        self.assertEqual(result.gesture, Gesture.NEXT_PAGE)

    def test_upper_right_figure_six_also_means_next_page(self):
        diagonal = math.sqrt(0.5)
        result = self.classifier().classify(
            two_finger_hand((diagonal, -diagonal)), timestamp=0.0
        )
        self.assertEqual(result.gesture, Gesture.NEXT_PAGE)

    def test_ergonomic_steep_upper_right_pose_means_next_page(self):
        direction = (0.40, -math.sqrt(1.0 - 0.40**2))
        result = self.classifier().classify(
            two_finger_hand(direction), timestamp=0.0
        )
        self.assertEqual(result.gesture, Gesture.NEXT_PAGE)

    def test_slightly_tilted_vertical_pose_still_means_scroll_up(self):
        direction = (0.20, -math.sqrt(1.0 - 0.20**2))
        result = self.classifier().classify(
            two_finger_hand(direction), timestamp=0.0
        )
        self.assertEqual(result.gesture, Gesture.SCROLL_UP)

    def test_lower_right_diagonal_prefers_scroll_down(self):
        direction = (0.40, math.sqrt(1.0 - 0.40**2))
        result = self.classifier().classify(
            two_finger_hand(direction), timestamp=0.0
        )
        self.assertEqual(result.gesture, Gesture.SCROLL_DOWN)

    def test_direction_depends_on_pose_not_position_in_frame(self):
        classifier = self.classifier()
        hand = two_finger_hand((-1.0, 0.0))

        first = classifier.classify(hand, timestamp=0.0)
        moved = classifier.classify(
            translated(hand, dx=250, dy=-80), timestamp=0.1
        )

        self.assertEqual(first.gesture, Gesture.PREVIOUS_PAGE)
        self.assertEqual(moved.gesture, Gesture.PREVIOUS_PAGE)

    def test_nonparallel_control_fingers_do_not_trigger_direction(self):
        hand = two_finger_hand((0.0, -1.0))
        orient_finger(hand, 9, 10, 11, 12, (1.0, 0.0))

        result = self.classifier().classify(hand, timestamp=0.0)

        self.assertEqual(result.gesture, Gesture.TWO_FINGER)

    def test_direction_pose_waits_for_time_based_settle(self):
        classifier = GestureClassifier(
            ema_alpha=1.0,
            min_stable_frames=3,
            direction_settle_seconds=0.22,
        )
        hand = two_finger_hand((1.0, 0.0))

        first = classifier.classify(hand, timestamp=0.0)
        second = classifier.classify(hand, timestamp=0.10)
        almost = classifier.classify(hand, timestamp=0.21)
        settled = classifier.classify(hand, timestamp=0.23)

        self.assertEqual(first.gesture, Gesture.NONE)
        self.assertEqual(second.gesture, Gesture.NONE)
        self.assertNotEqual(almost.gesture, Gesture.NEXT_PAGE)
        self.assertEqual(settled.gesture, Gesture.NEXT_PAGE)

    def test_changing_direction_restarts_pose_debounce(self):
        classifier = GestureClassifier(ema_alpha=1.0, min_stable_frames=3)
        right = two_finger_hand((1.0, 0.0))
        left = two_finger_hand((-1.0, 0.0))

        classifier.classify(right, timestamp=0.0)
        classifier.classify(right, timestamp=0.05)
        changed = classifier.classify(left, timestamp=0.10)

        self.assertNotIn(
            changed.gesture,
            (Gesture.NEXT_PAGE, Gesture.PREVIOUS_PAGE),
        )

    def test_hand_motion_restarts_direction_settle_timer(self):
        classifier = GestureClassifier(
            ema_alpha=1.0,
            min_stable_frames=1,
            direction_settle_seconds=0.22,
            direction_stillness_radius=0.10,
        )
        hand = two_finger_hand((1.0, 0.0))
        moved = translated(hand, dx=20)

        classifier.classify(hand, timestamp=0.0)
        classifier.classify(moved, timestamp=0.15)
        too_soon = classifier.classify(moved, timestamp=0.30)
        settled = classifier.classify(moved, timestamp=0.38)

        self.assertNotEqual(too_soon.gesture, Gesture.NEXT_PAGE)
        self.assertEqual(settled.gesture, Gesture.NEXT_PAGE)

    def test_small_webcam_jitter_does_not_restart_settle_timer(self):
        classifier = GestureClassifier(
            ema_alpha=1.0,
            min_stable_frames=1,
            direction_settle_seconds=0.22,
            direction_stillness_radius=0.10,
        )
        hand = two_finger_hand((1.0, 0.0))

        classifier.classify(hand, timestamp=0.0)
        settled = classifier.classify(
            translated(hand, dx=5), timestamp=0.23
        )

        self.assertEqual(settled.gesture, Gesture.NEXT_PAGE)

    def test_point_toward_camera_uses_depth(self):
        hand = point_hand()
        hand[5][1:] = [75, 160, -0.02]
        hand[6][1:] = [75, 135, -0.10]
        hand[7][1:] = [75, 133, -0.20]
        hand[8][1:] = [75, 131, -0.30]

        result = self.classifier().classify(
            hand,
            timestamp=0.0,
            image_width=640,
        )

        self.assertEqual(result.gesture, Gesture.POINT)

    def test_folded_index_with_misleading_depth_stays_fist(self):
        hand = fist_hand()
        for landmark_id, depth in zip(
            (5, 6, 7, 8), (0.0, -0.1, -0.2, -0.3)
        ):
            hand[landmark_id][3] = depth
        hand[4][1:] = hand[8][1:]

        result = self.classifier().classify(
            hand,
            timestamp=0.0,
            image_width=640,
        )

        self.assertEqual(result.gesture, Gesture.FIST)

    def test_pinch_distance_controls_zoom(self):
        hand = pinch_hand()
        classifier = self.classifier()
        classifier.classify(hand, timestamp=0.0)

        spread = copy_hand(hand)
        spread[4][1:3] = [60, 40]
        zoom_in = classifier.classify(spread, timestamp=0.2)

        classifier.reset()
        classifier.classify(spread, timestamp=1.0)
        zoom_out = classifier.classify(hand, timestamp=1.2)

        self.assertEqual(zoom_in.gesture, Gesture.ZOOM_IN)
        self.assertEqual(zoom_out.gesture, Gesture.ZOOM_OUT)

    def test_pinch_mode_does_not_fall_back_to_point(self):
        hand = pinch_hand()
        classifier = self.classifier()
        self.assertEqual(
            classifier.classify(hand, timestamp=0.0).gesture,
            Gesture.PINCH,
        )

        spread = copy_hand(hand)
        spread[4][1:3] = [5, 40]
        self.assertEqual(
            classifier.classify(spread, timestamp=0.2).gesture,
            Gesture.ZOOM_IN,
        )
        self.assertEqual(
            classifier.classify(spread, timestamp=0.3).gesture,
            Gesture.PINCH,
        )

    def test_open_hand_exits_pinch_mode(self):
        classifier = self.classifier()
        classifier.classify(pinch_hand(), timestamp=0.0)

        result = classifier.classify(copy_hand(), timestamp=0.2)

        self.assertEqual(result.gesture, Gesture.OPEN_PALM)

    def test_production_stability_requires_three_pinch_frames(self):
        classifier = GestureClassifier(ema_alpha=1.0)
        hand = pinch_hand()

        first = classifier.classify(hand, timestamp=0.0)
        second = classifier.classify(hand, timestamp=0.05)
        third = classifier.classify(hand, timestamp=0.10)

        self.assertEqual(first.gesture, Gesture.NONE)
        self.assertEqual(second.gesture, Gesture.NONE)
        self.assertEqual(third.gesture, Gesture.PINCH)

    def test_requires_all_landmarks(self):
        with self.assertRaises(ValueError):
            self.classifier().classify(OPEN_HAND[:20])

    def test_requires_depth_value(self):
        hand = copy_hand()
        hand[8] = hand[8][:-1]
        with self.assertRaisesRegex(ValueError, "id, x, y, and z"):
            self.classifier().classify(hand, timestamp=0.0)

    def test_rejects_invalid_image_width(self):
        with self.assertRaisesRegex(ValueError, "image_width must be positive"):
            self.classifier().classify(
                copy_hand(),
                timestamp=0.0,
                image_width=0,
            )

    def test_rejects_invalid_direction_threshold(self):
        with self.assertRaisesRegex(ValueError, "horizontal_direction_threshold"):
            GestureClassifier(horizontal_direction_threshold=0.0)


if __name__ == "__main__":
    unittest.main()
