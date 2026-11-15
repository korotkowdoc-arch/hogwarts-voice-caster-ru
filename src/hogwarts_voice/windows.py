"""Foreground process detection for optional game focus gating."""
from __future__ import annotations

import ctypes
import os

VK_F8 = 0x77
VK_F9 = 0x78
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
GAME_PROCESSES = frozenset({
    "hogwartslegacy.exe",
    "hogwartslegacy-win64-shipping.exe",
    "phoenix-win64-shipping.exe",
})

def foreground_process_path() -> str:
    """Absolute executable path of foreground app, if Windows allows it."""
    if os.name != "nt":
        return ""
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return ""
    try:
        buffer = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(buffer))
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return ""
        return buffer.value
    finally:
        kernel32.CloseHandle(handle)

def foreground_process_name() -> str:
    """Name of the currently focused executable, or empty if unavailable."""
    full = foreground_process_path()
    return full.rsplit("\\", 1)[-1].casefold() if full else ""

def is_game_process(name: str) -> bool:
    return name.casefold() in GAME_PROCESSES

def game_focused() -> bool:
    return is_game_process(foreground_process_name())

def down(vk: int) -> bool:
    if os.name != "nt":
        return False
    return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)

class KeyboardState:
    def __init__(self):
        self.active = True
        self._was_f8 = False

    def update(self):
        pressed = down(VK_F8)
        toggled = False
        if pressed and not self._was_f8:
            self.active = not self.active
            toggled = True
        self._was_f8 = pressed
        return toggled
