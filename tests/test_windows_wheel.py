import ctypes
import unittest
from unittest.mock import Mock, patch

from backend.action_mapper import ActionCommand, ActionMapper
from backend.windows_wheel import Input, send_wheel


class WindowsWheelTests(unittest.TestCase):
    def test_full_signed_notches_without_cursor_motion(self):
        for notches in (-4, -1, 1, 4):
            api = Mock()
            def send(count, pointer, size):
                event = pointer._obj
                self.assertEqual(count, 1)
                self.assertEqual(size, ctypes.sizeof(Input))
                self.assertEqual(event.type, 0)
                self.assertEqual(event.data.mi.mouseData, (120 * notches) & 0xffffffff)
                self.assertEqual(event.data.mi.dwFlags, 0x0800)
                self.assertEqual((event.data.mi.dx, event.data.mi.dy), (0, 0))
                return 1
            api.SendInput.side_effect = send
            send_wheel(notches, api)
            api.SendInput.assert_called_once()

    def test_rejected_native_input_is_not_reported_sent(self):
        api = Mock()
        api.SendInput.return_value = 0
        mapper = ActionMapper(actions_enabled=True, executor=lambda command: send_wheel(-1, api))
        result = mapper.execute(ActionCommand('scroll', (-1,), 'scroll down'))
        self.assertFalse(result.executed)
        self.assertIn('rejected wheel input', result.error)
        self.assertFalse(mapper.actions_enabled)

    def test_windows_executor_uses_native_notches_and_preserves_failsafe(self):
        fake = Mock()
        with patch.dict('sys.modules', {'pyautogui': fake}), patch(
            'backend.action_mapper.platform.system', return_value='Windows'
        ), patch('backend.scroll_target.prepare_scroll_target'), patch('backend.windows_wheel.send_wheel') as send:
            ActionMapper._execute_with_pyautogui(ActionCommand('scroll', (-1,), 'scroll down'))
            send.assert_called_once_with(-1)
            fake.scroll.assert_not_called()
            fake.failSafeCheck.assert_called_once()
            fake.failSafeCheck.side_effect = RuntimeError('failsafe')
            with self.assertRaisesRegex(RuntimeError, 'failsafe'):
                ActionMapper._execute_with_pyautogui(ActionCommand('scroll', (-1,), 'scroll down'))
            self.assertEqual(send.call_count, 1)
