"""Download the official sherpa-onnx GigaAM v2 Russian CTC model.

Non-commercial model license applies; no model weights are committed to Git.
Pinned Hugging Face revision and SHA-256 for the 236MB ONNX file.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from hogwarts_voice.ru_asr import model_directory, MODEL_FILE, TOKENS_FILE

REPO = "csukuangfj/sherpa-onnx-nemo-ctc-giga-am-v2-russian-2025-04-19"
REVISION = "499bb8aa0334ec8399ff827f00d791dc0ac7015d"
PREFIX = f"https://huggingface.co/{REPO}/resolve/{REVISION}"
# Source: published model.int8.onnx SHA256 (Hugging Face Xet details).
MODEL_SHA256 = "d0ce4aef25f58d495781ee8f05320d9e51b821f47804e07aa6549b53a72f67e8"
CHUNK = 1024 * 1024

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK * 4):
            digest.update(chunk)
    return digest.hexdigest()

def download_one(name, expected_sha=None, min_bytes=100):
    folder = model_directory()
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / name
    if destination.is_file() and destination.stat().st_size >= min_bytes:
        if expected_sha is None or sha256_file(destination) == expected_sha:
            print(f"[OK] Already installed: {destination}", flush=True)
            return destination
    tmp = destination.with_suffix(destination.suffix + ".part")
    if tmp.exists():
        tmp.unlink()
    url = f"{PREFIX}/{name}"
    print(f"[download] {name} from {REPO}", flush=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "HogwartsVoiceCasterRU/1.0"})
        with urllib.request.urlopen(req, timeout=90) as response, tmp.open("wb") as output:
            total = 0
            digest = hashlib.sha256()
            last_report = 0
            while chunk := response.read(CHUNK):
                output.write(chunk)
                digest.update(chunk)
                total += len(chunk)
                if total - last_report >= 16 * CHUNK:
                    print(f"[download] {name}: {total//CHUNK} MiB", flush=True)
                    last_report = total
            output.flush()
        if total < min_bytes:
            raise IOError(f"Model download incomplete: {total} bytes")
        if expected_sha and digest.hexdigest() != expected_sha:
            raise IOError(
                f"Model checksum mismatch for {name}; no unverified model installed. "
                "Check network/proxy and retry."
            )
        tmp.replace(destination)
        print(f"[OK] Saved {name}: {total // CHUNK} MiB", flush=True)
        return destination
    finally:
        if tmp.exists():
            tmp.unlink()

def main():
    folder = model_directory()
    print(f"[model] GigaAM v2 Russian speech model in: {folder}", flush=True)
    download_one(MODEL_FILE, expected_sha=MODEL_SHA256, min_bytes=150_000_000)
    download_one(TOKENS_FILE, min_bytes=100)
    from hogwarts_voice.ru_asr import RussianASR
    print("[model] Loading offline neural recognizer for verification...", flush=True)
    model = RussianASR(num_threads=2)
    # No speech: must NOT result in a spell. This only validates the model can load.
    import numpy as np
    sample = (np.zeros(16000, dtype=np.int16)).tobytes()
    print(f"[model] Silence smoke-test: {model.transcribe(sample)!r}", flush=True)
    print("[OK] Offline Russian neural speech engine installed.", flush=True)

if __name__ == "__main__":
    main()
