"""Resolve Windows wheel focus without clicking or changing system settings."""

import ctypes
import os
import platform
from ctypes import wintypes

from backend.action_mapper import InputTargetUnavailable


def prepare_scroll_target(user32=None, *, process_id=None):
    """Focus the external window under the pointer, or explain why it cannot scroll.

    Windows may otherwise send wheel input to the camera preview when inactive
    window scrolling is disabled. SetForegroundWindow is deliberately allowed
    to fail: the user can focus the desired app once and continue the pose.
    """
    if user32 is None:
        if platform.system() != "Windows":
            return
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        signatures = {
            "GetCursorPos": ([ctypes.POINTER(wintypes.POINT)], wintypes.BOOL),
            "WindowFromPoint": ([wintypes.POINT], wintypes.HWND),
            "GetAncestor": ([wintypes.HWND, wintypes.UINT], wintypes.HWND),
            "GetWindowThreadProcessId": ([wintypes.HWND, ctypes.POINTER(wintypes.DWORD)], wintypes.DWORD),
            "GetForegroundWindow": ([], wintypes.HWND),
            "SetForegroundWindow": ([wintypes.HWND], wintypes.BOOL),
        }
        for name, (args, result) in signatures.items():
            function = getattr(user32, name)
            function.argtypes = args
            function.restype = result
    point = wintypes.POINT()
    if not user32.GetCursorPos(ctypes.byref(point)):
        raise InputTargetUnavailable("Cannot locate pointer; point inside the browser")
    child = user32.WindowFromPoint(point)
    target = user32.GetAncestor(child, 2) if child else None  # GA_ROOT
    if not target:
        raise InputTargetUnavailable("Point inside the page you want to scroll")
    owner = wintypes.DWORD()
    if not user32.GetWindowThreadProcessId(target, ctypes.byref(owner)):
        raise InputTargetUnavailable("Target closed; point inside the browser")
    if owner.value == (os.getpid() if process_id is None else process_id):
        raise InputTargetUnavailable("Pointer is over HandNav; point inside the browser")
    if user32.GetForegroundWindow() != target:
        user32.SetForegroundWindow(target)
        if user32.GetForegroundWindow() != target:
            raise InputTargetUnavailable("Click the browser once to focus it, then scroll")
