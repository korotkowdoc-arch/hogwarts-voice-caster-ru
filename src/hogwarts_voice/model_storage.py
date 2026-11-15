"""Vosk's Windows DLL may fail to load a model from a non-ASCII path.

Keep language-model files in an ASCII-only user-writable directory.
No raw microphone audio or private profiles are written here.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
import tempfile

MODEL_NAME = "vosk-model-small-ru-0.22"
BASE_DIR = "HogwartsVoiceCasterRU"
REQUIRED_FILES = ("am/final.mdl", "conf/model.conf", "conf/mfcc.conf",
                  "graph/Gr.fst", "graph/HCLr.fst")

def legacy_model_path(project_root: Path) -> Path:
    return project_root / "models" / MODEL_NAME

def _writable(base: Path) -> bool:
    try:
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=base):
            pass
        return True
    except OSError:
        return False

def installed_model_path(project_root: Path, *, environ=None, windows=None) -> Path:
    """Return a stable, writable model path that is ASCII-only on Windows.

    Normal Windows users use LOCALAPPDATA; non-Latin Windows usernames
    automatically fall back to PROGRAMDATA or the public profile.
    """
    if windows is None:
        windows = sys.platform == "win32"
    if not windows:
        return legacy_model_path(project_root)
    env = os.environ if environ is None else environ
    for variable in ("LOCALAPPDATA", "PROGRAMDATA", "ALLUSERSPROFILE", "PUBLIC"):
        name = env.get(variable, "")
        if not name or not name.isascii():
            continue
        destination = Path(name) / BASE_DIR / "models"
        if _writable(destination):
            return destination / MODEL_NAME
    # Do not silently attempt loading from a non-ASCII project path.
    raise OSError(
        "No writable ASCII-only directory was found for the Vosk model. "
        "Check LOCALAPPDATA, PROGRAMDATA and PUBLIC Windows environment variables."
    )

def model_layout_ok(model_dir: Path) -> bool:
    return all((model_dir / name).is_file() and (model_dir / name).stat().st_size > 0
               for name in REQUIRED_FILES)

def migrate_legacy(project_root: Path, destination: Path) -> bool:
    """Copy legacy install once, without downloading or moving the old copy."""
    source = legacy_model_path(project_root)
    if model_layout_ok(destination):
        return True
    if source == destination or not model_layout_ok(source):
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Temporary destination prevents a half-copied model looking installed.
    with tempfile.TemporaryDirectory(prefix="hvc-copy-", dir=destination.parent) as work:
        staging = Path(work) / MODEL_NAME
        shutil.copytree(source, staging)
        if not model_layout_ok(staging):
            return False
        if destination.exists():
            shutil.rmtree(destination)
        shutil.move(str(staging), str(destination))
    return model_layout_ok(destination)
