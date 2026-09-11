import unittest
from unittest.mock import Mock, patch

from backend.action_mapper import ActionCommand, ActionMapper, InputTargetUnavailable


class PlaybackDeliveryTests(unittest.TestCase):
    def test_player_shortcut_focuses_target_before_one_key(self):
        for key in ('k', 'space'):
            events = []
            fake = Mock()
            fake.press.side_effect = lambda *args, **kwargs: events.append(('key', args))
            with patch.dict('sys.modules', {'pyautogui': fake}), patch(
                'backend.scroll_target.prepare_scroll_target', side_effect=lambda: events.append(('focus', ()))
            ):
                result = ActionMapper(actions_enabled=True).execute(ActionCommand('key', (key,), 'play or pause'))
            self.assertTrue(result.executed)
            self.assertEqual(events, [('focus', ()), ('key', (key,))])

    def test_blocked_player_does_not_type_or_send_media_fallback(self):
        fake = Mock()
        with patch.dict('sys.modules', {'pyautogui': fake}), patch(
            'backend.scroll_target.prepare_scroll_target', side_effect=InputTargetUnavailable('Point inside browser')
        ):
            result = ActionMapper(actions_enabled=True).execute(ActionCommand('key', ('k',), 'play or pause'))
        self.assertFalse(result.executed)
        self.assertIsNotNone(result.blocked_reason)
        fake.press.assert_not_called()
