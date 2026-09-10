"""Opt-in integration helper: send ONE Back/Forward command to owned Chrome.

The browser checker supplies a unique title token and confirms the page URL.
No mouse movement, focus changes, camera use, or arbitrary keys are permitted.
"""
import ctypes
import json
import sys

from backend.action_mapper import ActionCommand, ActionMapper


def main():
    if sys.platform != 'win32':
        raise RuntimeError('This guarded desktop smoke test currently supports Windows only')
    request=json.load(sys.stdin)
    token=request['title_token']
    if not token.startswith('NEO-HISTORY-CHECK-') or len(token)<40:
        raise ValueError('Expected the checker-generated unique title token')
    command=request['command']
    if command['kind']!='hotkey' or command['arguments'] not in (['alt','left'],['alt','right']):
        raise ValueError('Only browser Back/Forward shortcuts are allowed')
    user32=ctypes.windll.user32
    user32.GetForegroundWindow.restype=ctypes.c_void_p
    user32.GetWindowTextW.argtypes=(ctypes.c_void_p,ctypes.c_wchar_p,ctypes.c_int)
    foreground=user32.GetForegroundWindow()
    title=ctypes.create_unicode_buffer(1024)
    user32.GetWindowTextW(foreground,title,len(title))
    if not title.value.startswith(token+' - ') or 'Google Chrome' not in title.value:
        raise RuntimeError('Isolated Chrome is not foreground; no input sent')
    result=ActionMapper(actions_enabled=True).execute(ActionCommand(
        command['kind'],tuple(command['arguments']),command['description']))
    if result.error or not result.executed:
        raise RuntimeError(result.error or 'No input was executed')
    print(json.dumps({'executed':True,'command':command}))


if __name__=='__main__':
    main()
