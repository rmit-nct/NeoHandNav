"""Exercise camera wiring with fake frames; never open a camera or send keys."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

try:
    import numpy as np
    import main as app
    from backend.hand_tracker import HandTracker
except ImportError:
    app = None

from scripts.replay_gestures import replay
from tests.test_gesture_classifier import copy_hand, two_finger_hand
from tests.test_gesture_classifier import point_hand, fist_hand
from tests.test_pointer_controller import thumb_hand


@unittest.skipIf(app is None, 'Install requirements.txt for MediaPipe/OpenCV integration tests')
class TrackerTests(unittest.TestCase):
    def test_overlay_fits_screen_and_button_hit_targets_remain_aligned(self):
        from ui.feedback_overlay import FeedbackOverlay
        from backend.gesture_classifier import Gesture
        overlay=FeedbackOverlay()
        source=np.zeros((720,1280,3),dtype=np.uint8)
        canvas=overlay.render(source,Gesture.POINT,True,'Point to move',None,
                              help_visible=True,max_height=668,max_width=900)
        self.assertLessEqual(canvas.shape[0],668)
        self.assertLessEqual(canvas.shape[1],900)
        for left,top,right,bottom,action in overlay.buttons:
            self.assertEqual(overlay.hit_test((left+right)//2,(top+bottom)//2),action)
        self.assertIsNone(overlay.hit_test(0,0))
        self.assertFalse(source.any())

    def test_video_configuration_and_strictly_increasing_timestamps(self):
        with patch('backend.hand_tracker.vision.HandLandmarker.create_from_options') as create, \
             patch('backend.hand_tracker.monotonic_ns', return_value=1_000_000), \
             patch('builtins.print'):
            tracker = HandTracker(max_hands=2, detection_con=.65, track_con=.75)
            options = create.call_args.args[0]
            self.assertEqual(options.running_mode.name, 'VIDEO')
            self.assertEqual(options.min_tracking_confidence, .75)
            self.assertEqual(options.min_hand_presence_confidence, .75)
            self.assertEqual(options.min_hand_detection_confidence, .65)
            self.assertEqual(tracker.get_landmarks(np.zeros((10,10,3))), [])
            frame = np.zeros((10,10,3), dtype=np.uint8)
            tracker.process_frame(frame)
            tracker.process_frame(frame)
            self.assertEqual([call.args[1] for call in tracker.detector.detect_for_video.call_args_list], [1,2])
            tracker.detector.detect.assert_not_called()

    def test_landmarks_keep_subpixels_but_drawing_uses_integers(self):
        tracker = HandTracker.__new__(HandTracker)
        tracker.detection_result = SimpleNamespace(hand_landmarks=[
            [SimpleNamespace(x=.1234,y=.2345,z=-.01) for _ in range(21)]
        ])
        with patch('backend.hand_tracker.cv2.circle') as circle, patch('backend.hand_tracker.cv2.line') as line:
            hands = tracker.get_landmarks(np.zeros((480,640,3)), draw=True)
        self.assertAlmostEqual(hands[0][8][1], .1234*640)
        self.assertAlmostEqual(hands[0][8][2], .2345*480)
        self.assertEqual(hands[0][8][3], -.01)
        self.assertTrue(all(isinstance(x,int) for x in circle.call_args.args[1]))
        self.assertTrue(all(isinstance(x,int) for x in line.call_args.args[1]))


@unittest.skipIf(app is None, 'Install requirements.txt for MediaPipe/OpenCV integration tests')
class ApplicationTests(unittest.TestCase):
    def run_app(self, path, executor, mode='navigation', hands=None, keys=None):
        frame = np.zeros((480,640,3), dtype=np.uint8)
        hands = hands or [[copy_hand()]]*15 + [[two_finger_hand()]]*24 + [[]]
        capture = Mock()
        capture.isOpened.return_value = True
        capture.read.side_effect = [(True,frame)]*len(hands) + [(False,None)]
        tracker = Mock()
        tracker.get_landmarks.side_effect = hands
        cursor = [960,540]
        def execute(command):
            executor(command)
            if command.kind == 'move':
                cursor[:] = command.arguments
        with patch.object(app, '_open_camera', return_value=capture), \
             patch.object(app, 'HandTracker', return_value=tracker), \
             patch.object(app, 'load_dotenv'), \
             patch.object(app, '_screen_geometry', return_value=((1920,1080),(960,540))), \
             patch.object(app, '_pointer_position', side_effect=lambda:tuple(cursor)), \
             patch.object(app, '_draw_status') as draw, \
             patch.object(app.time, 'monotonic', side_effect=[i/30 for i in range(len(hands))]), \
             patch.object(app.cv2, 'imshow'), patch.object(app.cv2, 'waitKey', side_effect=keys or [-1]*len(hands)), \
             patch.object(app.cv2, 'getWindowProperty', return_value=1), \
             patch.object(app.cv2, 'destroyAllWindows'), \
             patch.object(app.cv2, 'namedWindow'), patch.object(app.cv2, 'setMouseCallback'), \
             patch.object(app.ActionMapper, '_execute_with_pyautogui', staticmethod(execute)), \
             patch.dict('os.environ', {'ACTIONS_ENABLED':'true','CONTROL_MODE':mode}, clear=True), \
             patch('sys.argv', ['main.py','--trace',str(path)]), patch('builtins.print'):
            self.assertEqual(app.main(), 1)  # simulated capture failure ends the loop
        capture.release.assert_called_once()
        tracker.detector.close.assert_called_once()
        return draw

    def test_live_trace_round_trip_and_cleanup(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)/'trace.jsonl'
            executor = Mock()
            self.run_app(path, executor)
            self.assertGreater(executor.call_count, 1)
            # Replay cannot call the OS executor even though live mode was on.
            with patch('backend.action_mapper.ActionMapper._execute_with_pyautogui') as no_os:
                summary = replay(path)
                no_os.assert_not_called()
            self.assertEqual(summary['frames'], 40)
            self.assertEqual(summary['differences'], 0)
            self.assertEqual(len(summary['actions']), executor.call_count)
            records = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(records[-1]['control_status'], 'SHOW ONE HAND')

    def test_failsafe_disables_live_controls_and_updates_overlay(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)/'trace.jsonl'
            executor = Mock(side_effect=RuntimeError('simulated fail-safe'))
            draw = self.run_app(path, executor)
            executor.assert_called_once()
            self.assertFalse(draw.call_args.args[2])
            self.assertEqual(replay(path)['differences'], 0)

    def test_mouse_live_trace_round_trip_records_moves_and_one_click(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)/'mouse.jsonl'
            executor = Mock()
            hands = [[point_hand()]]*20 + [[thumb_hand()]]*12 + [[point_hand()]]*12
            self.run_app(path, executor, mode='mouse', hands=hands)
            kinds=[call.args[0].kind for call in executor.call_args_list]
            self.assertIn('move',kinds)
            self.assertEqual(kinds.count('click'),1)
            self.assertEqual(replay(path)['differences'],0)

    def test_two_finger_click_and_playback_survive_live_wiring_and_replay(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'two-finger-media.jsonl'
            executor=Mock()
            hands=([[point_hand()]]*30 + [[two_finger_hand()]]*60 +
                   [[copy_hand()]]*15 + [[fist_hand()]]*60)
            self.run_app(path,executor,mode='mouse',hands=hands)
            commands=[call.args[0] for call in executor.call_args_list]
            self.assertEqual([c.arguments[2:] for c in commands if c.kind=='click'],[(1,'left')])
            import sys
            self.assertEqual([c.arguments for c in commands if c.kind=='key'],
                             [('playpause' if sys.platform.startswith('win') else 'space',)])
            self.assertFalse(any(c.kind in ('scroll','hotkey') for c in commands))
            self.assertEqual(replay(path)['differences'],0)

    def test_pause_during_pending_mouse_click_cancels_it_in_live_and_replay(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)/'pause.jsonl'
            executor=Mock()
            hands=[[point_hand()]]*20 + [[thumb_hand()]]*12 + [[point_hand()]]*12
            keys=[-1]*len(hands); keys[29]=ord('p'); keys[32]=ord('p')
            self.run_app(path,executor,mode='mouse',hands=hands,keys=keys)
            self.assertFalse(any(call.args[0].kind=='click' for call in executor.call_args_list))
            self.assertEqual(replay(path)['differences'],0)


if __name__ == '__main__':
    unittest.main()
