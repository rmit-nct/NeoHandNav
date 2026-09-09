"""Regressions for geometry and complete, timed control sequences."""

import unittest

from backend.action_mapper import ActionMapper
from backend.gesture_classifier import Gesture, GestureClassifier
from tests.test_gesture_classifier import (
    copy_hand, fist_hand, point_hand, two_finger_hand, translated,
)


class GeometryRegressions(unittest.TestCase):
    def test_curled_middle_tip_is_not_a_scroll_pose(self):
        hand = point_hand()
        hand[10][1:3] = [95, 105]
        hand[11][1:3] = [95, 35]
        hand[12][1:3] = [95, 65]
        classifier = GestureClassifier()
        results = [classifier.classify(hand, i / 30, 640).gesture for i in range(30)]
        self.assertEqual(results[-1], Gesture.POINT)
        self.assertNotIn(Gesture.SCROLL_UP, results)

    def test_depth_extended_ring_and_pinky_cannot_be_scroll(self):
        hand = two_finger_hand()
        for mcp, pip, dip, tip in ((13, 14, 15, 16), (17, 18, 19, 20)):
            x, y = hand[mcp][1:3]
            for joint, dy, z in ((pip, -25, -.1), (dip, -27, -.2), (tip, -29, -.3)):
                hand[joint][1:] = [x, y + dy, z]
        classifier = GestureClassifier()
        results = [classifier.classify(hand, i / 30, 640).gesture for i in range(30)]
        self.assertEqual(results[-1], Gesture.OPEN_PALM)
        self.assertNotIn(Gesture.SCROLL_UP, results)

    def test_collapsed_landmarks_are_not_a_fist(self):
        classifier = GestureClassifier()
        for i in range(10):
            with self.assertRaises(ValueError):
                classifier.classify([[j, 100, 100, 0] for j in range(21)], i / 30, 640)

    def test_held_direction_does_not_restart_for_hand_translation(self):
        classifier = GestureClassifier()
        hand = two_finger_hand()
        for i in range(15):
            classifier.classify(hand, i / 30, 640)
        result = classifier.classify(translated(hand, dx=20), .5, 640)
        self.assertEqual(result.gesture, Gesture.SCROLL_UP)

    def test_long_frame_gap_requires_new_direction_settle(self):
        classifier = GestureClassifier()
        hand = two_finger_hand()
        classifier.classify(hand, 0, 640)
        self.assertNotEqual(classifier.classify(hand, 10, 640).gesture, Gesture.SCROLL_UP)


class MapperRegressions(unittest.TestCase):
    def setUp(self):
        self.mapper = ActionMapper(cooldown_ms=0, scroll_cooldown_ms=0)
        self.mapper.handle(Gesture.OPEN_PALM, 0)
        self.mapper.handle(Gesture.OPEN_PALM, .13)

    def test_point_ends_scroll_session(self):
        self.assertIsNotNone(self.mapper.handle(Gesture.SCROLL_UP, .2))
        self.assertIsNone(self.mapper.handle(Gesture.POINT, .3))
        self.assertIsNone(self.mapper.handle(Gesture.SCROLL_UP, .4))
        self.assertEqual(self.mapper.control_status, 'SHOW OPEN PALM')

    def test_long_unknown_pose_ends_scroll_session(self):
        self.mapper.handle(Gesture.SCROLL_UP, .2)
        self.mapper.handle(Gesture.NONE, .3)
        self.mapper.handle(Gesture.NONE, .6)
        self.assertIsNone(self.mapper.handle(Gesture.SCROLL_UP, .7))

    def test_short_unknown_pose_never_executes_but_can_resume(self):
        self.mapper.handle(Gesture.SCROLL_UP, .2)
        self.assertIsNone(self.mapper.handle(Gesture.NONE, .25))
        self.assertIsNotNone(self.mapper.handle(Gesture.SCROLL_UP, .3))

    def test_gap_cannot_preserve_armed_state(self):
        self.assertIsNone(self.mapper.handle(Gesture.FIST, 10))

    def test_pinch_session_allows_multiple_zoom_steps(self):
        self.assertIsNotNone(self.mapper.handle(Gesture.ZOOM_IN, .2))
        self.mapper.handle(Gesture.PINCH, .3)
        self.assertIsNotNone(self.mapper.handle(Gesture.ZOOM_IN, .4))
        self.mapper.handle(Gesture.PINCH, .5)
        self.assertIsNotNone(self.mapper.handle(Gesture.ZOOM_OUT, .6))

    def test_execution_error_disables_os_control(self):
        def fail(command):
            raise RuntimeError('simulated fail-safe')
        self.mapper.set_actions_enabled(True)
        self.mapper._executor = fail
        self.mapper.handle(Gesture.OPEN_PALM, .14)
        self.mapper.handle(Gesture.OPEN_PALM, .28)
        result = self.mapper.handle(Gesture.SCROLL_UP, .3)
        self.assertIsNotNone(result.error)
        self.assertFalse(self.mapper.actions_enabled)


if __name__ == '__main__':
    unittest.main()
