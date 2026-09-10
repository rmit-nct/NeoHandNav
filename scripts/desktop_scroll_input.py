"""Opt-in wheel delivery test, restricted to the owned foreground Chrome window."""
import ctypes
from ctypes import wintypes
import json
import sys

from backend.action_mapper import ActionCommand, ActionMapper


def main():
    request=json.load(sys.stdin)
    token=request['title_token']
    delta=request['delta']
    if sys.platform!='win32' or not token.startswith('NEO-SCROLL-CHECK-') or len(token)<40:
        raise ValueError('Expected a Windows test session token')
    if type(delta) is not int or delta not in (-1,1):
        raise ValueError('Only one wheel step up or down is permitted')
    import pyautogui  # establishes the same DPI handling as the app
    user32=ctypes.windll.user32
    user32.GetForegroundWindow.restype=ctypes.c_void_p
    user32.GetWindowTextW.argtypes=(ctypes.c_void_p,ctypes.c_wchar_p,ctypes.c_int)
    user32.GetClientRect.argtypes=(ctypes.c_void_p,ctypes.POINTER(wintypes.RECT))
    user32.ClientToScreen.argtypes=(ctypes.c_void_p,ctypes.POINTER(wintypes.POINT))
    window=user32.GetForegroundWindow()
    title=ctypes.create_unicode_buffer(1024)
    user32.GetWindowTextW(window,title,len(title))
    if not title.value.startswith(token+' - ') or 'Google Chrome' not in title.value:
        raise RuntimeError('Owned Chrome is not foreground; no input sent')
    rect=wintypes.RECT()
    if not user32.GetClientRect(window,ctypes.byref(rect)) or rect.bottom<300:
        raise RuntimeError('Cannot identify a usable test window')
    centre=wintypes.POINT(rect.right//2,rect.bottom//2)
    if not user32.ClientToScreen(window,ctypes.byref(centre)):
        raise RuntimeError('Cannot identify the test window centre')
    if user32.GetForegroundWindow()!=window:
        raise RuntimeError('Focus changed; no input sent')
    mapper=ActionMapper(actions_enabled=True)
    for command in (ActionCommand('move',(centre.x,centre.y),'test pointer'),
                    ActionCommand('scroll',(delta,),'test scroll')):
        result=mapper.execute(command)
        if result.error or not result.executed:
            raise RuntimeError(result.error or 'Input not sent')
    print(json.dumps({'executed':True,'delta':delta}))


if __name__=='__main__': main()
