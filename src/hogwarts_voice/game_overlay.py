"""Optional tiny, click-through, no-focus status overlay for borderless games.

No screen capture, hooks, or injected game code. The widget only displays
trusted local log events from our own listener. It is OFF by default.
Exclusive fullscreen can hide desktop overlays; borderless is recommended.
"""
from __future__ import annotations
import ctypes
import os
import re
import tkinter as tk

_BG="#172231"
_FG="#ecf0f7"
_GREEN="#9bd8ad"
_GOLD="#f1d28d"
_RED="#f4a29a"

def classify_line(line: str):
    """Return a concise (message, color) or None for non-game messages."""
    value=line.strip()
    patterns=(
        (r"^\[game:cast\]\s+([A-Za-z0-9]+)", "✦ Применено: {}", _GREEN),
        (r"^\[game:failed\]\s+([A-Za-z0-9]+)", "Не сработало: {}", _RED),
        (r"^\[game:busy\]\s+([A-Za-z0-9]+)", "Палочка занята: {}", _GOLD),
        (r"^\[game:unverified\]\s+([A-Za-z0-9]+)", "Без подтверждения: {}", _GOLD),
        (r"^\[sent\]\s+([A-Za-z0-9]+)", "Отправлено в игру: {}", _GOLD),
        (r"^\[interact\]\s+([A-Za-z0-9]+)", "Взаимодействие: {}", _GOLD),
        (r"^\[TEST\]\s+([A-Za-z0-9]+)", "Тест: {}", _GREEN),
    )
    for pattern, fmt, color in patterns:
        found=re.search(pattern,value,re.I)
        if found:
            return fmt.format(found.group(1)), color
    return None

class GameOverlay:
    """Construct once on the Tk main thread. Never calls focus() or grab()."""
    def __init__(self, root, *, enabled=False):
        self.root=root
        self.enabled=bool(enabled)
        self.after_id=None
        self.window=tk.Toplevel(root)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.configure(background=_BG)
        self.window.wm_attributes("-topmost", True)
        self.text=tk.Label(
            self.window, text="", bg=_BG, fg=_FG,
            font=("Segoe UI",12,"bold"),
            padx=18,pady=14,anchor="w",
        )
        self.text.pack(fill="both",expand=True)
        self.window.update_idletasks()
        if os.name=="nt":
            try:
                self._click_through()
            except (OSError, AttributeError, TypeError):
                # Avoid affecting game focus if Windows denies overlay style.
                self.enabled=False

    def _click_through(self):
        user32=ctypes.WinDLL("user32",use_last_error=True)
        # Tk on Windows sometimes exposes an inner child HWND through
        # winfo_id; styles must be applied to its real TOP-LEVEL ancestor.
        hwnd=self.window.winfo_id()
        user32.GetAncestor.argtypes=[ctypes.c_void_p,ctypes.c_uint]
        user32.GetAncestor.restype=ctypes.c_void_p
        root_hwnd=user32.GetAncestor(hwnd,2)  # GA_ROOT
        if root_hwnd:
            hwnd=root_hwnd
        GWL_EXSTYLE=-20
        WS_EX_TRANSPARENT=0x20
        WS_EX_NOACTIVATE=0x08000000
        WS_EX_TOOLWINDOW=0x80
        WS_EX_LAYERED=0x80000
        if ctypes.sizeof(ctypes.c_void_p)==8:
            get_style=user32.GetWindowLongPtrW
            set_style=user32.SetWindowLongPtrW
        else:
            get_style=user32.GetWindowLongW
            set_style=user32.SetWindowLongW
        get_style.argtypes=[ctypes.c_void_p,ctypes.c_int]
        get_style.restype=ctypes.c_ssize_t
        set_style.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_ssize_t]
        set_style.restype=ctypes.c_ssize_t
        old=get_style(hwnd,GWL_EXSTYLE)
        set_style(hwnd,GWL_EXSTYLE,old|WS_EX_TRANSPARENT|WS_EX_NOACTIVATE
                  |WS_EX_TOOLWINDOW|WS_EX_LAYERED)

    def set_enabled(self, enabled: bool):
        self.enabled=bool(enabled)
        if not self.enabled:
            self.hide()

    def show(self, line: str):
        if not self.enabled or os.name!="nt":
            return
        parsed=classify_line(line)
        if not parsed:
            return
        from .windows import game_focused
        if not game_focused():
            return
        message,color=parsed
        self.text.configure(text=message,fg=color)
        w=350
        h=55
        self.window.geometry(f"{w}x{h}+{self.root.winfo_screenwidth()-w-26}+54")
        self.window.deiconify()
        # NOACTIVATE and TRANSPARENT flags avoid stealing game focus.
        if self.after_id is not None:
            self.root.after_cancel(self.after_id)
        self.after_id=self.root.after(1700,self.hide)

    def hide(self):
        self.after_id=None
        if self.window.winfo_exists():
            self.window.withdraw()

    def close(self):
        if self.after_id is not None:
            self.root.after_cancel(self.after_id)
            self.after_id=None
        if self.window.winfo_exists():
            self.window.destroy()
