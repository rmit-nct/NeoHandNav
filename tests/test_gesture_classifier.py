from __future__ import annotations

import unittest

from backend.gesture_classifier import Gesture, GestureClassifier


OPEN_HAND = [
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


def copy_hand(hand=OPEN_HAND):
    return [landmark.copy() for landmark in hand]


def fold_finger(hand, pip_id: int, dip_id: int, tip_id: int) -> None:
    pip_x, pip_y = hand[pip_id][1], hand[pip_id][2]
    hand[dip_id][1:] = [pip_x + 8, pip_y + 20]
    hand[tip_id][1:] = [pip_x + 5, pip_y + 45]


def translated(hand, dx=0, dy=0):
    return [[landmark_id, x + dx, y + dy] for landmark_id, x, y in hand]


class GestureClassifierTests(unittest.TestCase):
    def classifier(self, **overrides):
        settings = {
            "ema_alpha": 1.0,
            "min_stable_frames": 1,
            "swipe_threshold": 0.65,
            "scroll_threshold": 0.30,
            "zoom_threshold": 0.10,
        }
        settings.update(overrides)
        return GestureClassifier(**settings)

    def test_open_palm(self):
        result = self.classifier().classify(copy_hand(), timestamp=0.0)
        self.assertEqual(result.gesture, Gesture.OPEN_PALM)

    def test_fist(self):
        hand = copy_hand()
        for pip, dip, tip in ((6, 7, 8), (10, 11, 12), (14, 15, 16), (18, 19, 20)):
            fold_finger(hand, pip, dip, tip)
        result = self.classifier().classify(hand, timestamp=0.0)
        self.assertEqual(result.gesture, Gesture.FIST)

    def test_point(self):
        hand = copy_hand()
        for pip, dip, tip in ((10, 11, 12), (14, 15, 16), (18, 19, 20)):
            fold_finger(hand, pip, dip, tip)
        result = self.classifier().classify(hand, timestamp=0.0)
        self.assertEqual(result.gesture, Gesture.POINT)

    def test_pinch(self):
        hand = copy_hand()
        for pip, dip, tip in ((10, 11, 12), (14, 15, 16), (18, 19, 20)):
            fold_finger(hand, pip, dip, tip)
        hand[4][1:] = [77, 42]
        result = self.classifier().classify(hand, timestamp=0.0)
        self.assertEqual(result.gesture, Gesture.PINCH)

    def test_swipe_left(self):
        classifier = self.classifier()
        classifier.classify(copy_hand(), timestamp=0.0)
        result = classifier.classify(translated(OPEN_HAND, dx=-80), timestamp=0.2)
        self.assertEqual(result.gesture, Gesture.SWIPE_LEFT)

    def test_scroll_up(self):
        classifier = self.classifier()
        classifier.classify(copy_hand(), timestamp=0.0)
        result = classifier.classify(translated(OPEN_HAND, dy=-40), timestamp=0.2)
        self.assertEqual(result.gesture, Gesture.SCROLL_UP)

    def test_pinch_distance_controls_zoom(self):
        hand = copy_hand()
        for pip, dip, tip in ((10, 11, 12), (14, 15, 16), (18, 19, 20)):
            fold_finger(hand, pip, dip, tip)
        hand[4][1:] = [77, 42]

        classifier = self.classifier()
        classifier.classify(hand, timestamp=0.0)
        spread = copy_hand(hand)
        spread[4][1:] = [60, 40]
        zoom_in = classifier.classify(spread, timestamp=0.2)
        self.assertEqual(zoom_in.gesture, Gesture.ZOOM_IN)

        classifier.reset()
        classifier.classify(spread, timestamp=1.0)
        zoom_out = classifier.classify(hand, timestamp=1.2)
        self.assertEqual(zoom_out.gesture, Gesture.ZOOM_OUT)

    def test_requires_all_landmarks(self):
        with self.assertRaises(ValueError):
            self.classifier().classify(OPEN_HAND[:20])


if __name__ == "__main__":
    unittest.main()
