from __future__ import annotations

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


def translated(hand, dx=0, dy=0):
    return [
        [landmark_id, x + dx, y + dy, z]
        for landmark_id, x, y, z in hand
    ]


def two_finger_hand():
    hand = copy_hand()
    for pip, dip, tip in ((14, 15, 16), (18, 19, 20)):
        fold_finger(hand, pip, dip, tip)
    return hand


def fist_hand():
    hand = copy_hand()
    for pip, dip, tip in ((6, 7, 8), (10, 11, 12), (14, 15, 16), (18, 19, 20)):
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
    def classifier(self, **overrides):
        settings = {
            "ema_alpha": 1.0,
            "min_stable_frames": 1,
            "swipe_threshold": 0.50,
            "scroll_threshold": 0.50,
            "zoom_threshold": 0.10,
        }
        settings.update(overrides)
        return GestureClassifier(**settings)

    def test_open_palm(self):
        result = self.classifier().classify(copy_hand(), timestamp=0.0)
        self.assertEqual(result.gesture, Gesture.OPEN_PALM)

    def test_fist(self):
        result = self.classifier().classify(fist_hand(), timestamp=0.0)
        self.assertEqual(result.gesture, Gesture.FIST)

    def test_fist_is_not_pinch_when_thumb_and_index_are_close(self):
        hand = fist_hand()
        hand[4][1:] = hand[8][1:]
        result = self.classifier().classify(hand, timestamp=0.0)
        self.assertEqual(result.gesture, Gesture.FIST)

    def test_folded_index_with_misleading_depth_stays_fist(self):
        hand = fist_hand()
        for landmark_id, depth in zip((5, 6, 7, 8), (0.0, -0.1, -0.2, -0.3)):
            hand[landmark_id][3] = depth
        hand[4][1:] = hand[8][1:]

        result = self.classifier().classify(
            hand,
            timestamp=0.0,
            image_width=640,
        )
        self.assertEqual(result.gesture, Gesture.FIST)

    def test_point(self):
        result = self.classifier().classify(point_hand(), timestamp=0.0)
        self.assertEqual(result.gesture, Gesture.POINT)

    def test_pinch(self):
        result = self.classifier().classify(pinch_hand(), timestamp=0.0)
        self.assertEqual(result.gesture, Gesture.PINCH)

    def test_open_palm_is_not_pinch_when_tips_overlap(self):
        hand = copy_hand()
        hand[4][1:] = hand[8][1:]
        result = self.classifier().classify(hand, timestamp=0.0)
        self.assertEqual(result.gesture, Gesture.OPEN_PALM)

    def test_two_finger_is_not_pinch_when_tips_overlap(self):
        hand = two_finger_hand()
        hand[4][1:] = hand[8][1:]
        result = self.classifier().classify(hand, timestamp=0.0)
        self.assertEqual(result.gesture, Gesture.TWO_FINGER)

    def test_point_toward_camera_uses_depth(self):
        hand = copy_hand()
        for pip, dip, tip in ((10, 11, 12), (14, 15, 16), (18, 19, 20)):
            fold_finger(hand, pip, dip, tip)

        # The index finger appears short in x/y but is straight along z.
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

    def test_two_finger_control_pose(self):
        result = self.classifier().classify(two_finger_hand(), timestamp=0.0)
        self.assertEqual(result.gesture, Gesture.TWO_FINGER)

    def test_point_toward_camera_tolerates_small_depth_noise(self):
        hand = copy_hand()
        for pip, dip, tip in ((10, 11, 12), (14, 15, 16), (18, 19, 20)):
            fold_finger(hand, pip, dip, tip)

        # A realistic foreshortened finger has small x/y separation and much
        # smaller z values toward its tip. One slightly noisy step is allowed.
        hand[5][1:] = [75, 160, -0.035]
        hand[6][1:] = [75, 143, -0.060]
        hand[7][1:] = [76, 141, -0.057]
        hand[8][1:] = [75, 139, -0.105]

        result = self.classifier().classify(
            hand,
            timestamp=0.0,
            image_width=640,
        )
        self.assertEqual(result.gesture, Gesture.POINT)

    def test_swipe_left(self):
        classifier = self.classifier()
        hand = two_finger_hand()
        classifier.classify(hand, timestamp=0.0)
        result = classifier.classify(translated(hand, dx=-80), timestamp=0.2)
        self.assertEqual(result.gesture, Gesture.SWIPE_LEFT)

    def test_scroll_up(self):
        classifier = self.classifier()
        hand = two_finger_hand()
        classifier.classify(hand, timestamp=0.0)
        result = classifier.classify(translated(hand, dy=-40), timestamp=0.2)
        self.assertEqual(result.gesture, Gesture.SCROLL_UP)

    def test_swipe_right(self):
        classifier = self.classifier()
        hand = two_finger_hand()
        classifier.classify(hand, timestamp=0.0)
        result = classifier.classify(translated(hand, dx=80), timestamp=0.2)
        self.assertEqual(result.gesture, Gesture.SWIPE_RIGHT)

    def test_scroll_down(self):
        classifier = self.classifier()
        hand = two_finger_hand()
        classifier.classify(hand, timestamp=0.0)
        result = classifier.classify(translated(hand, dy=40), timestamp=0.2)
        self.assertEqual(result.gesture, Gesture.SCROLL_DOWN)

    def test_open_palm_motion_is_neutral(self):
        classifier = self.classifier()
        classifier.classify(copy_hand(), timestamp=0.0)
        result = classifier.classify(translated(OPEN_HAND, dx=-80), timestamp=0.2)
        self.assertEqual(result.gesture, Gesture.OPEN_PALM)

    def test_vertical_jitter_does_not_steal_horizontal_swipe(self):
        classifier = self.classifier()
        hand = two_finger_hand()
        classifier.classify(hand, timestamp=0.0)

        jitter = classifier.classify(
            translated(hand, dx=30, dy=34),
            timestamp=0.1,
        )
        self.assertNotIn(
            jitter.gesture,
            (Gesture.SCROLL_UP, Gesture.SCROLL_DOWN),
        )

        swipe = classifier.classify(
            translated(hand, dx=80, dy=34),
            timestamp=0.2,
        )
        self.assertEqual(swipe.gesture, Gesture.SWIPE_RIGHT)

    def test_pinch_distance_controls_zoom(self):
        hand = pinch_hand()

        classifier = self.classifier()
        classifier.classify(hand, timestamp=0.0)
        spread = copy_hand(hand)
        spread[4][1:3] = [60, 40]
        zoom_in = classifier.classify(spread, timestamp=0.2)
        self.assertEqual(zoom_in.gesture, Gesture.ZOOM_IN)

        classifier.reset()
        classifier.classify(spread, timestamp=1.0)
        zoom_out = classifier.classify(hand, timestamp=1.2)
        self.assertEqual(zoom_out.gesture, Gesture.ZOOM_OUT)

    def test_pinch_mode_does_not_fall_back_to_point(self):
        hand = pinch_hand()

        classifier = self.classifier()
        pinch = classifier.classify(hand, timestamp=0.0)
        self.assertEqual(pinch.gesture, Gesture.PINCH)

        spread = copy_hand(hand)
        spread[4][1:3] = [5, 40]
        zoom = classifier.classify(spread, timestamp=0.2)
        self.assertEqual(zoom.gesture, Gesture.ZOOM_IN)

        held = classifier.classify(spread, timestamp=0.3)
        self.assertEqual(held.gesture, Gesture.PINCH)
        self.assertNotEqual(held.gesture, Gesture.POINT)

        exited = classifier.classify(copy_hand(), timestamp=0.4)
        self.assertEqual(exited.gesture, Gesture.OPEN_PALM)

    def test_fist_exits_active_pinch_mode(self):
        classifier = self.classifier()
        classifier.classify(pinch_hand(), timestamp=0.0)
        result = classifier.classify(fist_hand(), timestamp=0.2)
        self.assertEqual(result.gesture, Gesture.FIST)

    def test_point_cannot_zoom_without_starting_a_pinch(self):
        classifier = self.classifier()
        hand = point_hand()
        classifier.classify(hand, timestamp=0.0)
        moved_thumb = copy_hand(hand)
        moved_thumb[4][1:3] = [20, 100]
        result = classifier.classify(moved_thumb, timestamp=0.2)
        self.assertEqual(result.gesture, Gesture.POINT)

    def test_two_finger_pose_cannot_start_zoom(self):
        classifier = self.classifier()
        hand = two_finger_hand()
        hand[4][1:] = hand[8][1:]
        classifier.classify(hand, timestamp=0.0)
        moved_thumb = copy_hand(hand)
        moved_thumb[4][1:3] = [20, 100]
        result = classifier.classify(moved_thumb, timestamp=0.2)
        self.assertNotIn(result.gesture, (Gesture.ZOOM_IN, Gesture.ZOOM_OUT))

    def test_one_noisy_pinch_frame_does_not_arm_zoom(self):
        classifier = self.classifier(min_stable_frames=2)
        classifier.classify(pinch_hand(), timestamp=0.0)
        result = classifier.classify(point_hand(), timestamp=0.1)
        self.assertNotIn(result.gesture, (Gesture.ZOOM_IN, Gesture.ZOOM_OUT))

    def test_two_finger_motion_waits_for_stable_pose(self):
        classifier = self.classifier(min_stable_frames=2)
        hand = two_finger_hand()
        classifier.classify(hand, timestamp=0.0)
        early = classifier.classify(translated(hand, dx=-80), timestamp=0.1)
        self.assertNotEqual(early.gesture, Gesture.SWIPE_LEFT)

        stable = translated(hand, dx=-80)
        classifier.classify(stable, timestamp=0.2)
        moved = classifier.classify(translated(stable, dx=-80), timestamp=0.3)
        self.assertEqual(moved.gesture, Gesture.SWIPE_LEFT)

    def test_production_stability_requires_three_pinch_frames(self):
        classifier = GestureClassifier(ema_alpha=1.0)
        hand = pinch_hand()
        first = classifier.classify(hand, timestamp=0.0)
        second = classifier.classify(hand, timestamp=0.05)
        third = classifier.classify(hand, timestamp=0.10)
        self.assertEqual(first.gesture, Gesture.NONE)
        self.assertEqual(second.gesture, Gesture.NONE)
        self.assertEqual(third.gesture, Gesture.PINCH)

    def test_production_stability_arms_two_finger_before_motion(self):
        classifier = GestureClassifier(ema_alpha=1.0)
        hand = two_finger_hand()
        first = classifier.classify(hand, timestamp=0.0)
        second = classifier.classify(hand, timestamp=0.05)
        third = classifier.classify(hand, timestamp=0.10)
        self.assertEqual(first.gesture, Gesture.NONE)
        self.assertEqual(second.gesture, Gesture.NONE)
        self.assertEqual(third.gesture, Gesture.TWO_FINGER)

        moved = classifier.classify(
            translated(hand, dx=-100),
            timestamp=0.20,
        )
        self.assertEqual(moved.gesture, Gesture.SWIPE_LEFT)

    def test_open_hand_does_not_start_zoom(self):
        classifier = self.classifier()
        hand = copy_hand()
        classifier.classify(hand, timestamp=0.0)
        hand[4][1:3] = [75, 45]
        result = classifier.classify(hand, timestamp=0.2)
        self.assertNotIn(result.gesture, (Gesture.ZOOM_IN, Gesture.ZOOM_OUT))

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


if __name__ == "__main__":
    unittest.main()
