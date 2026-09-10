"""The opt-in OS test helper must refuse unowned windows and arbitrary input."""
import io
import json
import unittest
from unittest.mock import Mock, patch

from scripts.desktop_history_input import main


class DesktopGuardTests(unittest.TestCase):
    def request(self,kind='hotkey',arguments=None):
        return io.StringIO(json.dumps({
            'title_token':'NEO-HISTORY-CHECK-11111111-2222-3333-4444-555555555555',
            'command':{'kind':kind,'arguments':arguments or ['alt','left'],'description':'browser back'},
        }))

    def test_non_test_foreground_refuses_input(self):
        fake=Mock()
        def title(window,buffer,length): buffer.value='Unrelated app'
        fake.user32.GetWindowTextW.side_effect=title
        with patch('scripts.desktop_history_input.sys.platform','win32'), \
             patch('scripts.desktop_history_input.ctypes.windll',fake,create=True), \
             patch('sys.stdin',self.request()), patch('scripts.desktop_history_input.ActionMapper.execute') as execute:
            with self.assertRaisesRegex(RuntimeError,'no input sent'): main()
            execute.assert_not_called()

    def test_arbitrary_input_is_rejected_before_windows_api(self):
        with patch('scripts.desktop_history_input.sys.platform','win32'), \
             patch('sys.stdin',self.request('click',[100,100,1,'left'])), \
             patch('scripts.desktop_history_input.ActionMapper.execute') as execute:
            with self.assertRaises(ValueError): main()
            execute.assert_not_called()
