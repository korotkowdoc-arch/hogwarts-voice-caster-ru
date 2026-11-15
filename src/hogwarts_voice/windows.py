"""Safety switches for Windows-only game focus and keyboard shortcuts."""
from __future__ import annotations
import ctypes
import os

VK_F8 = 0x77
VK_F9 = 0x78
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

def game_focused():
    """Allow spells only when the PC game's EXE is foreground."""
    if os.name != "nt":
        return False
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
        return False
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return False
    try:
        buffer = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(buffer))
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return False
        name = buffer.value.rsplit("\\", 1)[-1].casefold()
        return name in {"hogwartslegacy.exe", "phoenix-win64-shipping.exe"}
    finally:
        kernel32.CloseHandle(handle)

def down(vk):
    if os.name != "nt":
        return False
    return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)

class KeyboardState:
    def __init__(self):
        self.active = True
        self._was_f8 = False

    def update(self):
        now = down(VK_F8)
        toggled = False
        if now and not self._was_f8:
            self.active = not self.active
            toggled = True
        self._was_f8 = now
        return toggled
