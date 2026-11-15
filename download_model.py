"""Download an official Russian Vosk model (data only, no remote code)."""
from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import urllib.request
import zipfile

NAME = "vosk-model-small-ru-0.22"
URL = f"https://alphacephei.com/vosk/models/{NAME}.zip"
ROOT = Path(__file__).resolve().parent
DEST = ROOT / "models" / NAME
MAX_EXTRACT_BYTES = 500 * 1024 * 1024

def main():
    if (DEST / "am" / "final.mdl").exists():
        print(f"[OK] Model already installed: {DEST}")
        return
    (ROOT / "models").mkdir(parents=True, exist_ok=True)
    print(f"Downloading official Vosk model: {URL}")
    with tempfile.TemporaryDirectory(dir=ROOT / "models") as td:
        target = Path(td) / "model.zip"
        urllib.request.urlretrieve(URL, target)
        with zipfile.ZipFile(target) as archive:
            members = archive.infolist()
            if sum(e.file_size for e in members) > MAX_EXTRACT_BYTES:
                raise ValueError("Model archive exceeds expected size")
            for item in members:
                path = Path(item.filename)
                if path.parts[0] != NAME or ".." in path.parts or path.is_absolute():
                    raise ValueError(f"Unsafe model archive entry: {item.filename}")
            archive.extractall(Path(td) / "unpacked")
        extracted = Path(td) / "unpacked" / NAME
        if not (extracted / "am" / "final.mdl").exists():
            raise ValueError("Unrecognized Vosk model")
        if DEST.exists():
            shutil.rmtree(DEST)
        shutil.move(str(extracted), str(DEST))
    print(f"[OK] Downloaded to {DEST}")

if __name__ == "__main__":
    main()
