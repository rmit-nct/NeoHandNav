"""Windows wheel injection with explicit notch units and delivery checks."""

import ctypes
from ctypes import wintypes


class MouseInput(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class InputUnion(ctypes.Union):
    _fields_ = [("mi", MouseInput)]


class Input(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("data", InputUnion)]


def send_wheel(notches: int, user32=None) -> None:
    """Send signed wheel notches without moving the cursor or suppressing errors."""
    if type(notches) is not int or not -(2**31//120) <= notches <= (2**31-1)//120:
        raise ValueError("Wheel notches must fit a signed Windows wheel delta")
    if notches == 0:
        return
    if user32 is None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int]
        user32.SendInput.restype = wintypes.UINT
    event = Input(type=0, data=InputUnion(mi=MouseInput(
        mouseData=(notches * 120) & 0xffffffff, dwFlags=0x0800,
    )))
    if user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(Input)) != 1:
        raise OSError("Windows rejected wheel input; check the target app's input permissions")
