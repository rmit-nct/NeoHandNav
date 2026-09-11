import unittest
from unittest.mock import Mock, patch

from backend.action_mapper import ActionCommand, ActionMapper, InputTargetUnavailable
from backend.scroll_target import prepare_scroll_target


class ScrollTargetTests(unittest.TestCase):
    def api(self, *, foreground=20, owner=200, allow_focus=True):
        api = Mock()
        api.GetCursorPos.return_value = 1
        api.WindowFromPoint.return_value = 21
        api.GetAncestor.return_value = 20
        api.GetForegroundWindow.return_value = foreground
        def process(window, output):
            output._obj.value = owner
            return 1
        api.GetWindowThreadProcessId.side_effect = process
        def focus(window):
            if allow_focus:
                api.GetForegroundWindow.return_value = window
            return allow_focus
        api.SetForegroundWindow.side_effect = focus
        return api

    def test_foreground_browser_needs_no_focus_change(self):
        api = self.api()
        prepare_scroll_target(api, process_id=100)
        api.SetForegroundWindow.assert_not_called()

    def test_inactive_browser_is_focused_without_clicking(self):
        api = self.api(foreground=10)
        prepare_scroll_target(api, process_id=100)
        api.SetForegroundWindow.assert_called_once_with(20)

    def test_preview_and_denied_focus_are_recoverable(self):
        for api, message in ((self.api(owner=100), 'over HandNav'),
                             (self.api(foreground=10, allow_focus=False), 'focus it')):
            with self.subTest(message=message):
                executor = lambda command: prepare_scroll_target(api, process_id=100)
                mapper = ActionMapper(actions_enabled=True, executor=executor)
                result = mapper.execute(ActionCommand('scroll', (-1,), 'scroll down'))
                self.assertFalse(result.executed)
                self.assertIsNone(result.error)
                self.assertIn(message, result.blocked_reason)
                self.assertTrue(mapper.actions_enabled)

    def test_missing_window_or_cursor_blocks_input(self):
        for method in ('GetCursorPos', 'WindowFromPoint', 'GetAncestor', 'GetWindowThreadProcessId'):
            api = self.api()
            getattr(api, method).side_effect = None
            getattr(api, method).return_value = 0
            with self.subTest(method=method), self.assertRaises(InputTargetUnavailable):
                prepare_scroll_target(api, process_id=100)
            api.SetForegroundWindow.assert_not_called()

    def test_blocked_target_never_sends_wheel_and_recovers(self):
        fake = Mock()
        mapper = ActionMapper(actions_enabled=True)
        command = ActionCommand('scroll', (-1,), 'scroll down')
        with patch.dict('sys.modules', {'pyautogui': fake}), patch('backend.action_mapper.platform.system', return_value='Linux'), patch(
            'backend.scroll_target.prepare_scroll_target',
            side_effect=[InputTargetUnavailable('Focus browser'), None],
        ):
            self.assertFalse(mapper.execute(command).executed)
            fake.scroll.assert_not_called()
            self.assertTrue(mapper.execute(command).executed)
            fake.scroll.assert_called_once_with(-1, _pause=False)


if __name__ == '__main__':
    unittest.main()
