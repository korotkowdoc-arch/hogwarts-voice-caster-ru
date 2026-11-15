"""Contextual Hogwarts Legacy actions not exposed by SpellCaster's wand API.

Alohomora is an interact prompt, not a SpellToolRecord. Trigger only a
user-configured interaction key while the game is FOREGROUND. This can open
a lock's minigame, but cannot tell whether a lock is targeted. Do not claim
that a door was unlocked or bypass a lock-level requirement.
"""
from __future__ import annotations

import ctypes
import os
import time
from .windows import game_focused

ACTION_IDS = frozenset({"Alohomora"})
DEFAULT_INTERACT_KEY = "F"
VALID_KEYS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")

def validate_interact_key(key: str) -> str:
    if not isinstance(key, str) or len(key) != 1 or key.upper() not in VALID_KEYS:
        raise ValueError("interaction_key must be one A-Z or 0-9 key")
    return key.upper()

def _send_keyboard(key: str) -> None:
    if os.name != "nt":
        raise OSError("Keyboard interaction requires Windows")
    from ctypes import wintypes

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_size_t),
        ]
    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG), ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t),
        ]
    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD),
        ]
    class INPUTUNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT),
                    ("hi", HARDWAREINPUT)]
    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("data", INPUTUNION)]

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SendInput.argtypes = [
        wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int,
    ]
    user32.SendInput.restype = wintypes.UINT
    user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
    user32.MapVirtualKeyW.restype = wintypes.UINT

    vk = ord(key)
    scan = user32.MapVirtualKeyW(vk, 0)
    if not scan:
        raise OSError(f"No keyboard scan code for {key}")
    # Scan codes avoid keyboard layout surprises (Russian/English).
    SCANCODE = 0x0008
    KEYUP = 0x0002
    events = (INPUT * 2)(
        INPUT(type=1, data=INPUTUNION(ki=KEYBDINPUT(
            wVk=0, wScan=scan, dwFlags=SCANCODE, time=0, dwExtraInfo=0))),
        INPUT(type=1, data=INPUTUNION(ki=KEYBDINPUT(
            wVk=0, wScan=scan, dwFlags=SCANCODE | KEYUP, time=0, dwExtraInfo=0))),
    )
    # A down/up pair in one Windows call can be too fast for Unreal's
    # per-frame polling. Hold one key briefly, then ALWAYS release it.
    size = ctypes.sizeof(INPUT)
    n = user32.SendInput(1, ctypes.byref(events[0]), size)
    if n != 1:
        raise OSError(f"SendInput key-down failed: {ctypes.get_last_error()}")
    try:
        time.sleep(0.055)
    finally:
        released = user32.SendInput(1, ctypes.byref(events[1]), size)
    if released != 1:
        raise OSError(f"SendInput key-up failed: {ctypes.get_last_error()}")

def interact_with_lock(*, key=DEFAULT_INTERACT_KEY,
                       focus_check=None, sender=None):
    """One safe contextual interact. Returns (success, status).

    A command must never inject keyboard input outside focused game window,
    even if general 'require_game_focus' has been disabled for diagnostics.
    """
    key = validate_interact_key(key)
    if focus_check is None:
        focus_check = game_focused
    if not focus_check():
        return False, "game not foreground; interaction blocked"
    if sender is None:
        sender = _send_keyboard
    try:
        sender(key)
    except (OSError, ValueError) as exc:
        return False, f"interaction failed: {exc}"
    return True, "interact"
