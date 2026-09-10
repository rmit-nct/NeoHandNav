"""Transition tremor must not move the visible target before a click."""
import math
import unittest

from backend.action_mapper import ActionMapper
from backend.gesture_classifier import Gesture, GestureClassifier
from backend.gesture_controller import GestureController
from backend.pointer_controller import PointerController, PointerSettings
from tests.test_gesture_classifier import point_hand, two_finger_hand, translated


class StabilizationTests(unittest.TestCase):
    def controller(self, buffer=.1):
        return GestureController(GestureClassifier(),ActionMapper(),PointerController(
            settings=PointerSettings(motion_buffer_seconds=buffer,pointer_deadzone_pixels=0)),mode='mouse')

    def test_transition_tremor_is_discarded_before_click_at_all_frame_rates(self):
        for fps in (10,15,30,60):
            for buffer in (0.,.1):
                with self.subTest(fps=fps,buffer=buffer):
                    c=self.controller(buffer)
                    aim=translated(point_hand(),245,200)  # cursor centre
                    i=0
                    for _ in range(fps): c.process([aim],i/fps,640,480);i+=1
                    target=c.pointer.position
                    # One brief involuntary shift while the hand still looks
                    # like Point, followed by the intended click pose.
                    for _ in range(max(1,round(.05*fps))):
                        c.process([translated(aim,18,10)],i/fps,640,480);i+=1
                    clicks=[]
                    for _ in range(fps):
                        _,action=c.process([two_finger_hand()],i/fps,640,480);i+=1
                        if action and action.command.kind=='click': clicks.append(action.command)
                    self.assertEqual(len(clicks),1)
                    if buffer:
                        self.assertEqual(c.pointer.position,target)
                        self.assertEqual(clicks[0].arguments[:2],target)
                    else:
                        # Negative control reproduces movement with buffering off.
                        self.assertGreater(math.dist(clicks[0].arguments[:2],target),1)

    def test_pending_motion_is_dropped_on_uncertainty_and_does_not_replay(self):
        p=PointerController()
        aim=translated(point_hand(),245,200)
        for i in range(30): p.process(Gesture.POINT,aim,i/30,(640,480))
        target=p.position
        p.process(Gesture.POINT,translated(aim,30,0),1.,(640,480))
        p.process(Gesture.NONE,aim,1.03,(640,480))
        for i in range(40): p.process(Gesture.POINT,aim,1.06+i/30,(640,480))
        self.assertEqual(p.position,target)

    def test_intentional_movement_still_reaches_new_target(self):
        p=PointerController()
        aim=translated(point_hand(),345,250)
        for i in range(90): p.process(Gesture.POINT,aim,i/30,(640,480))
        expected=((420/640-.15)/.7*1919,(290/480-.15)/.7*1079)
        self.assertLess(math.dist(p.position,expected),3)

    def test_deadzone_keeps_small_hover_noise_still(self):
        p=PointerController()
        for i in range(120):
            aim=translated(point_hand(),245+.3*math.sin(i),200+.3*math.cos(i))
            p.process(Gesture.POINT,aim,i/30,(640,480))
        self.assertEqual(p.position,(960,540))

    def test_resume_discards_old_velocity_and_waits_for_fresh_motion(self):
        p=PointerController()
        aim=translated(point_hand(),245,200)
        for i in range(30): p.process(Gesture.POINT,aim,i/30,(640,480))
        for i in range(30,50): p.process(Gesture.TWO_FINGER_CLICK,aim,i/30,(640,480))
        target=p.position
        first_move=None
        for i in range(50,80):
            command=p.process(Gesture.POINT,translated(aim,30,0),i/30,(640,480))
            if command and command.kind=='move':
                first_move=(i,command);break
        self.assertIsNotNone(first_move)
        frame,command=first_move
        self.assertGreaterEqual((frame-50)/30,.26)
        self.assertLess(math.dist(command.arguments,target),40)

    def test_buffer_and_deadzone_settings_validate_bounds(self):
        for settings in ({'motion_buffer_seconds':-.1},{'motion_buffer_seconds':.3},
                         {'pointer_deadzone_pixels':11},{'pointer_deadzone_pixels':float('nan')}):
            with self.assertRaises(ValueError): PointerSettings(**settings)
        PointerSettings(motion_buffer_seconds=0,pointer_deadzone_pixels=0)


if __name__=='__main__': unittest.main()
