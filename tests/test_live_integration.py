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


@unittest.skipIf(app is None, 'Install requirements.txt for MediaPipe/OpenCV integration tests')
class TrackerTests(unittest.TestCase):
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
    def run_app(self, path, executor):
        frame = np.zeros((480,640,3), dtype=np.uint8)
        capture = Mock()
        capture.isOpened.return_value = True
        capture.read.side_effect = [(True,frame)]*40 + [(False,None)]
        tracker = Mock()
        tracker.get_landmarks.side_effect = [[copy_hand()]]*15 + [[two_finger_hand()]]*24 + [[]]
        with patch.object(app, '_open_camera', return_value=capture), \
             patch.object(app, 'HandTracker', return_value=tracker), \
             patch.object(app, 'load_dotenv'), \
             patch.object(app, '_draw_status') as draw, \
             patch.object(app.time, 'monotonic', side_effect=[i/30 for i in range(40)]), \
             patch.object(app.cv2, 'imshow'), patch.object(app.cv2, 'waitKey', return_value=-1), \
             patch.object(app.cv2, 'getWindowProperty', return_value=1), \
             patch.object(app.cv2, 'destroyAllWindows'), \
             patch.object(app.ActionMapper, '_execute_with_pyautogui', executor), \
             patch.dict('os.environ', {'ACTIONS_ENABLED':'true'}, clear=True), \
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
            self.assertEqual(records[-1]['control_status'], 'SHOW OPEN PALM')

    def test_failsafe_disables_live_controls_and_updates_overlay(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)/'trace.jsonl'
            executor = Mock(side_effect=RuntimeError('simulated fail-safe'))
            draw = self.run_app(path, executor)
            executor.assert_called_once()
            self.assertFalse(draw.call_args.args[2])
            self.assertEqual(replay(path)['differences'], 0)


if __name__ == '__main__':
    unittest.main()
