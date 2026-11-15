"""Pinned, SHA-256 verified optional GigaAM v2 NeMo RNNT model installer.

Non-commercial license applies. Model weights are never committed to Git.
Official converted models from csukuangfj's sherpa-onnx Hugging Face repo.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import urllib.request

from .ru_asr import (
    RussianTransducerASR, transducer_directory, TRANSDUCER_FILES,
)

HF_REPO="csukuangfj/sherpa-onnx-nemo-transducer-giga-am-v2-russian-2025-04-19"
REVISION="fffee92ef28e15bc1703b898784930cbfc505509"
FILES={
    "encoder.int8.onnx": (
        150_000_000,"b51efc61e3c0037ad1cb804079975468de3d175324fe8323aef5be4f5c6a38a1"),
    "decoder.onnx": (
        1_000_000,"208e24cc150fb0ebca3fab169502796daa12e0255dcf7b4acf65015c436e9f76"),
    "joiner.onnx": (
        500_000,"4b02eced18e033fc5173e6c47b6ab166b5efea8d35c3f33a6755ff0d622fb5b0"),
    "tokens.txt":(100,None),
}
CHUNK=1024*1024

def sha256_file(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda:stream.read(CHUNK),b""):
            digest.update(chunk)
    return digest.hexdigest()

def install_transducer(report=None):
    def note(message):
        if report:
            report(message)
    root=transducer_directory()
    root.mkdir(parents=True,exist_ok=True)
    for filename in TRANSDUCER_FILES:
        minimum,checksum=FILES[filename]
        destination=root/filename
        if destination.is_file() and destination.stat().st_size>=minimum:
            if checksum is None or sha256_file(destination)==checksum:
                note(f"[model] {filename}: уже установлен")
                continue
        note(f"[model] Загружаем {filename}...")
        temporary=destination.with_suffix(destination.suffix+".partial")
        try:
            url=f"https://huggingface.co/{HF_REPO}/resolve/{REVISION}/{filename}"
            request=urllib.request.Request(url,headers={
                "User-Agent":"HogwartsVoiceCasterRU-ModelInstaller/1.0"})
            digest=hashlib.sha256()
            total=0
            with urllib.request.urlopen(request,timeout=90) as stream,temporary.open("wb") as out:
                while data:=stream.read(CHUNK):
                    digest.update(data)
                    total+=len(data)
                    out.write(data)
                    if total%(32*CHUNK)<CHUNK:
                        note(f"[model] {filename}: {total//CHUNK} MiB")
            if total<minimum or (checksum and digest.hexdigest()!=checksum):
                raise ValueError(f"File integrity failure: {filename}")
            temporary.replace(destination)
        finally:
            if temporary.exists():
                temporary.unlink()
    note("[model] Проверяем загрузку нейросети...")
    model=RussianTransducerASR(num_threads=2)
    silence=b"\x00\x00"*16000
    model.transcribe(silence)
    note("[model] GigaAM Transducer установлен и проверен")
    return root
