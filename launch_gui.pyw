"""Windows no-console entry point.

Launched with .venv/Scripts/pythonw.exe. Capture startup errors in a local
log and also show a visible message box, so failures aren't silent.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

try:
    from hogwarts_voice.ui import main
    raise SystemExit(main())
except BaseException as exc:
    logdir = Path(os.environ.get("LOCALAPPDATA") or ROOT) / "HogwartsVoiceCasterRU"
    try:
        logdir.mkdir(parents=True, exist_ok=True)
        (logdir / "startup_error.log").write_text(
            "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
            encoding="utf-8",
        )
    except OSError:
        pass
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Hogwarts Voice Caster: ошибка запуска",
            f"{exc}\n\nПодробности: {logdir / 'startup_error.log'}",
            parent=root,
        )
        root.destroy()
    except Exception:
        pass
    raise
