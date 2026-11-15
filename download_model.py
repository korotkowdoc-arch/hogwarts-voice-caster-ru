"""Install/repair the official Vosk Russian model in a Windows-safe path.

The old model folder inside the ZIP/project is migrated automatically.
The Vosk C library itself is used to verify that the model can load.
"""
from __future__ import annotations

from pathlib import Path
import shutil
import sys
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from hogwarts_voice.model_storage import (
    MODEL_NAME, installed_model_path, model_layout_ok, migrate_legacy
)

NAME = MODEL_NAME
URL = f"https://alphacephei.com/vosk/models/{NAME}.zip"
DEST = installed_model_path(ROOT)
MAX_EXTRACT_BYTES = 500 * 1024 * 1024

def check_loadable(path: Path) -> bool:
    if not model_layout_ok(path):
        return False
    try:
        from vosk import Model, SetLogLevel
        SetLogLevel(-1)
        model = Model(str(path))
        del model
        return True
    except Exception as exc:
        print(f"[WARN] Existing Vosk model could not load: {exc}", flush=True)
        return False

def download_fresh(destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    print(f"[download] Official Vosk model: {URL}", flush=True)
    with tempfile.TemporaryDirectory(prefix="hvc-install-", dir=destination.parent) as tmp:
        tmp = Path(tmp)
        archive_file = tmp / "model.zip"
        urllib.request.urlretrieve(URL, archive_file)
        with zipfile.ZipFile(archive_file) as archive:
            members = archive.infolist()
            if sum(e.file_size for e in members) > MAX_EXTRACT_BYTES:
                raise ValueError("Model archive exceeds expected size")
            for member in members:
                p = Path(member.filename)
                if not p.parts or p.parts[0] != NAME or p.is_absolute() or ".." in p.parts:
                    raise ValueError(f"Unsafe model archive entry: {member.filename}")
            archive.extractall(tmp / "unpacked")
        staged = tmp / "unpacked" / NAME
        if not model_layout_ok(staged):
            raise ValueError("Downloaded Vosk model has incomplete contents")
        if not check_loadable(staged):
            raise ValueError("Downloaded model failed to load in Vosk: check Windows/antivirus/storage")
        if destination.exists():
            shutil.rmtree(destination)
        shutil.move(str(staged), str(destination))

def main():
    print(f"[model] Storage: {DEST}", flush=True)
    if not str(DEST).isascii() and sys.platform == "win32":
        raise RuntimeError("Vosk model must be stored in an ASCII-only path on Windows")
    if check_loadable(DEST):
        print(f"[OK] Model already installed and verified: {DEST}", flush=True)
        return
    if migrate_legacy(ROOT, DEST) and check_loadable(DEST):
        print(f"[OK] Model migrated to safe path: {DEST}", flush=True)
        return
    print("[model] Repairing model installation...", flush=True)
    download_fresh(DEST)
    if not check_loadable(DEST):
        raise RuntimeError("Model installation failed verification after download")
    print(f"[OK] Russian speech model installed and verified: {DEST}", flush=True)

if __name__ == "__main__":
    main()
