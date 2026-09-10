"""Mouse stabilization must not suppress or redirect an armed wheel action."""
import unittest

from backend.action_mapper import ActionMapper
from backend.gesture_classifier import GestureClassifier
from backend.gesture_controller import GestureController
from backend.pointer_controller import PointerController, PointerSettings
from tests.test_gesture_classifier import copy_hand, point_hand, two_finger_hand


class ScrollStabilizationTests(unittest.TestCase):
    def test_up_and_down_keep_same_wheel_output_with_buffer_enabled(self):
        for fps in (10,15,30,60):
            for direction,sign in (((0,1),-1),((0,-1),1)):
                runs=[]
                for buffer in (0.,.1):
                    commands=[]
                    c=GestureController(GestureClassifier(),ActionMapper(actions_enabled=True,
                        executor=commands.append,scroll_amount=1,scroll_cooldown_ms=60),
                        PointerController(settings=PointerSettings(motion_buffer_seconds=buffer)),mode='mouse')
                    i=0
                    for hand,seconds in ((point_hand(),1.5),(copy_hand(),.5),(two_finger_hand(direction),2.)):
                        for _ in range(round(fps*seconds)):
                            c.process([hand],i/fps,640,480);i+=1
                    wheel=[command.arguments for command in commands if command.kind=='scroll']
                    self.assertGreater(len(wheel),5)
                    self.assertTrue(all(args==(sign,) for args in wheel))
                    self.assertFalse(any(command.kind in ('click','hotkey') for command in commands))
                    runs.append(wheel)
                self.assertEqual(runs[0],runs[1])


if __name__=='__main__': unittest.main()
