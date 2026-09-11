"""Replay hand sequences through the same boundary used by the webcam loop."""

import math
import random
import unittest
from unittest.mock import Mock, patch

from backend.action_mapper import ActionCommand, ActionMapper
from backend.gesture_classifier import Gesture, GestureClassifier
from backend.gesture_controller import GestureController
from tests.test_gesture_classifier import copy_hand, fist_hand, pinch_hand, point_hand, two_finger_hand


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.commands = []
        self.controller = GestureController(
            GestureClassifier(),
            ActionMapper(actions_enabled=True, scroll_cooldown_ms=60, executor=self.commands.append),
        )
        self.time = 0.0

    def hold(self, hand, duration=.5, fps=30):
        results = []
        for _ in range(round(duration * fps)):
            hands = [] if hand is None else [hand]
            results.append(self.controller.process(hands, self.time, 640))
            self.time += 1 / fps
        return results

    def test_fist_open_and_point_transitions_at_multiple_frame_rates(self):
        for fps in (10, 15, 30, 60):
            for start, end in ((fist_hand(), copy_hand()), (copy_hand(), fist_hand()),
                               (copy_hand(), point_hand()), (point_hand(), copy_hand())):
                with self.subTest(fps=fps, start=start[8], end=end[8]):
                    self.setUp()
                    self.hold(copy_hand(), fps=fps)
                    self.hold(start, fps=fps)
                    for step in range(1, fps + 1):
                        fraction = step / fps
                        hand = [[a[0], *[x + (y-x)*fraction for x,y in zip(a[1:], b[1:])]]
                                for a,b in zip(start,end)]
                        self.hold(hand, duration=1/fps, fps=fps)
                    self.hold(end, fps=fps)
                    self.assertFalse(any(c.kind == 'scroll' for c in self.commands))
                    self.assertFalse(any(c.kind == 'hotkey' for c in self.commands))
                    self.assertLessEqual(len(self.commands), 1)

    def test_point_with_seeded_landmark_noise_never_scrolls(self):
        for mirror in (False, True):
            for scale in (.5, 1, 2):
                self.setUp()
                self.hold(copy_hand())
                rng = random.Random(42)
                for _ in range(180):
                    hand = point_hand()
                    for lm in hand:
                        lm[1] = (640-lm[1] if mirror else lm[1]) * scale + rng.uniform(-1,1)*scale
                        lm[2] = lm[2]*scale + rng.uniform(-1,1)*scale
                        lm[3] += rng.uniform(-.001,.001)
                    self.hold(hand, 1/30)
                self.assertEqual(self.commands, [])

    def test_hand_loss_requires_new_palm(self):
        self.hold(copy_hand())
        self.hold(two_finger_hand())
        self.assertGreater(len(self.commands), 0)
        self.hold(None, 1/30)
        count = len(self.commands)
        self.hold(two_finger_hand())
        self.assertEqual(len(self.commands), count)
        self.hold(copy_hand())
        self.hold(two_finger_hand())
        self.assertGreater(len(self.commands), count)

    def test_second_hand_revokes_ready_state(self):
        self.hold(copy_hand())
        result, action = self.controller.process([copy_hand(), copy_hand()], self.time, 640)
        self.time += 1/30
        self.assertEqual(result.gesture, Gesture.NONE)
        self.assertIsNone(action)
        self.hold(fist_hand())
        self.assertEqual(self.commands, [])

    def test_invalid_landmarks_revoke_ready_state(self):
        for invalid in ('nan', 'inf', 'duplicate', 'missing', 'fractional', 'collapsed'):
            with self.subTest(invalid=invalid):
                self.setUp()
                self.hold(copy_hand())
                hand = copy_hand()
                if invalid in ('nan', 'inf'):
                    hand[8][1] = float(invalid)
                elif invalid == 'duplicate':
                    hand.append(hand[0].copy())
                elif invalid == 'missing':
                    hand.pop()
                elif invalid == 'fractional':
                    hand[0][0] = .5
                else:
                    hand = [[i,100,100,0] for i in range(21)]
                result, action = self.controller.process([hand], self.time, 640)
                self.time += 1/30
                self.assertEqual(result.gesture, Gesture.NONE)
                self.assertIsNone(action)
                self.hold(fist_hand())
                self.assertEqual(self.commands, [])

    def test_page_and_fist_are_one_shot_at_production_settings(self):
        import platform
        modifier = 'command' if platform.system() == 'Darwin' else 'alt'
        for hand, expected in ((two_finger_hand((1,0)), (modifier,'right')), (fist_hand(), ('space',))):
            with self.subTest(expected=expected):
                self.setUp()
                self.hold(copy_hand())
                self.hold(hand, 2)
                self.assertEqual([c.arguments for c in self.commands], [expected])

    def test_short_fist_glitch_does_not_send_space(self):
        self.hold(copy_hand())
        self.hold(fist_hand(), .1, fps=60)
        self.hold(point_hand())
        self.assertEqual(self.commands, [])

    def test_held_scroll_small_motion_and_one_bad_frame_resume(self):
        self.hold(copy_hand())
        self.hold(two_finger_hand())
        count = len(self.commands)
        self.hold(point_hand(), 1/30)
        self.hold(two_finger_hand(), .6)
        self.assertGreater(len(self.commands), count)

    def test_pinch_zoom_can_reverse_without_new_palm(self):
        self.hold(copy_hand())
        self.hold(pinch_hand())
        spread = pinch_hand()
        spread[4][1] = 30
        self.hold(spread, 1.1)
        self.hold(pinch_hand(), 1.1)
        self.assertEqual([c.description for c in self.commands], ['zoom in', 'zoom out'])

    def test_mirrored_and_rotated_poses_follow_screen_direction(self):
        for angle in (0, math.pi/2, math.pi, -math.pi/2):
            for mirror in (False, True):
                with self.subTest(angle=angle, mirror=mirror):
                    hand = two_finger_hand()
                    for lm in hand:
                        x,y = lm[1]-100, lm[2]-220
                        x,y = x*math.cos(angle)-y*math.sin(angle), x*math.sin(angle)+y*math.cos(angle)
                        lm[1],lm[2] = 320+(-x if mirror else x), 240+y
                    classifier = GestureClassifier()
                    for i in range(20):
                        result = classifier.classify(hand, i/30, 640)
                    dx = math.sin(angle) * (-1 if mirror else 1)
                    dy = -math.cos(angle)
                    expected = (Gesture.SCROLL_UP if dy < -.5 else Gesture.SCROLL_DOWN if dy > .5
                                else Gesture.NEXT_PAGE if dx > 0 else Gesture.PREVIOUS_PAGE)
                    self.assertEqual(result.gesture, expected)


class ExecutorTests(unittest.TestCase):
    def test_all_commands_keep_failsafe_and_skip_post_call_sleep(self):
        fake = Mock(FAILSAFE=False)
        with patch.dict('sys.modules', {'pyautogui': fake}), patch('backend.scroll_target.prepare_scroll_target'), patch('backend.action_mapper.platform.system', return_value='Linux'):
            for command in (ActionCommand('key',('space',),'play'),
                            ActionCommand('scroll',(1,),'scroll'),
                            ActionCommand('hotkey',('ctrl','+'),'zoom')):
                ActionMapper._execute_with_pyautogui(command)
        self.assertTrue(fake.FAILSAFE)
        fake.press.assert_called_once_with('space', _pause=False)
        fake.scroll.assert_called_once_with(1, _pause=False)
        fake.hotkey.assert_called_once_with('ctrl','+', _pause=False)


if __name__ == '__main__':
    unittest.main()
