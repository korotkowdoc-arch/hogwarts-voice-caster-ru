"""Offline few-shot acoustic word matcher with constrained dynamic time warping.

Unlike Vosk's limited vocabulary, this compares spoken *sounds*, not generated
Russian text. Deliberately independent of Vosk and any cloud service.
Requires 3-6 examples per command. NOT a production-grade KWS classifier.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000
FRAME_SIZE = 400
HOP = 160
NUM_FRAMES = 48
NUM_MELS = 26
NUM_MFCC = 13
FEAT_DIM = (NUM_MFCC - 1) * 2
MIN_TAKES = 3
VERSION = 2
MIN_SCORE = 0.72  # Experimental; tune on real positive and negative utterances.
MIN_MARGIN = 0.065

def model_path() -> Path:
    base = Path(os.getenv("LOCALAPPDATA") or (Path.home() / ".local" / "share"))
    return base / "HogwartsVoiceCasterRU" / "pronunciation_dtw_v2.json"

def _mel(hz):
    return 2595.0 * np.log10(1 + np.asarray(hz) / 700.0)

def _hz(mel):
    return 700.0 * (np.power(10.0, np.asarray(mel) / 2595.0) - 1.0)

def _melbank():
    nfft = 512
    points = np.floor((nfft + 1) * _hz(
        np.linspace(_mel(80), _mel(7300), NUM_MELS + 2)
    ) / SAMPLE_RATE).astype(int)
    filters = np.zeros((NUM_MELS, nfft // 2 + 1), dtype=np.float32)
    for k in range(NUM_MELS):
        a, b, c = points[k:k + 3]
        if not a < b < c:
            continue
        filters[k, a:b] = np.linspace(0, 1, b - a, endpoint=False)
        filters[k, b:c] = np.linspace(1, 0, c - b, endpoint=False)
    return filters

MELBANK = _melbank()
DCT = np.cos((np.arange(NUM_MFCC)[:, None] * np.pi / NUM_MELS) *
             (np.arange(NUM_MELS)[None, :] + 0.5)).astype(np.float32)

def extract(pcm: bytes):
    """Convert PCM16 into 48x24 MFCC+delta vectors, with a duration hint.

    Trailing/leading silence is removed identically at training and runtime.
    Neither raw audio nor transcription is stored.
    """
    if len(pcm) % 2:
        raise ValueError("Invalid 16-bit audio")
    raw = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
    if raw.size < SAMPLE_RATE * 0.19:
        raise ValueError("Слишком короткая запись")
    n = (len(raw) // HOP) * HOP
    rms = np.sqrt((raw[:n].reshape(-1, HOP) ** 2).mean(axis=1))
    peak = float(rms.max(initial=0))
    if peak < 0.017:
        raise ValueError("Микрофон не слышит речь")
    active = np.flatnonzero(rms >= max(0.013, peak * 0.24))
    if len(active) < 13:
        raise ValueError("Слишком короткое произношение")
    start = max(0, active[0] * HOP - 400)
    end = min(len(raw), (active[-1] + 1) * HOP + 400)
    speech = raw[start:end]
    duration = len(speech) / SAMPLE_RATE
    if not 0.19 <= duration <= 2.5:
        raise ValueError("Заклинание должно длиться от 0.2 до 2.5 секунды")

    # 25ms frames with 10ms hop. The same frontend is used in both modes.
    speech = np.concatenate((speech[:1], speech[1:] - 0.95 * speech[:-1]))
    frames = np.lib.stride_tricks.sliding_window_view(speech, FRAME_SIZE)[::HOP]
    spectrum = np.abs(np.fft.rfft(frames * np.hanning(FRAME_SIZE), n=512, axis=1)) ** 2
    mel = np.log(np.maximum(1e-7, spectrum @ MELBANK.T))
    mfcc = (mel @ DCT.T)[:, 1:]
    # Remove mic coloration without losing all absolute vowel information.
    mean = mfcc.mean(axis=0, keepdims=True)
    std = np.maximum(mfcc.std(axis=0, keepdims=True), 2.0)
    static = (mfcc - 0.75 * mean) / std
    delta = np.gradient(mfcc, axis=0) / std
    feature = np.concatenate([static, 0.7 * delta], axis=1)
    feature /= np.maximum(1e-5, np.linalg.norm(feature, axis=1, keepdims=True))

    # Time normalization keeps DTW work bounded and consistent.
    grid = np.linspace(0, len(feature) - 1, NUM_FRAMES)
    low = grid.astype(int)
    high = np.minimum(low + 1, len(feature) - 1)
    portion = (grid - low)[:, None]
    feature = feature[low] * (1 - portion) + feature[high] * portion
    feature /= np.maximum(1e-5, np.linalg.norm(feature, axis=1, keepdims=True))
    return feature.astype(np.float32), float(duration)

def _dtw(a, b, da, db):
    """Sakoe-Chiba band DTW on cosine distances; one-shot, no model loading."""
    x = np.asarray(a, dtype=np.float32)
    y = np.asarray(b, dtype=np.float32)
    if x.shape != (NUM_FRAMES, FEAT_DIM) or y.shape != x.shape:
        raise ValueError("Invalid DTW template shape")
    costs = 1.0 - np.clip(x @ y.T, -1, 1)
    previous = np.full(NUM_FRAMES + 1, np.inf, dtype=np.float32)
    previous[0] = 0
    band = 11
    for i in range(NUM_FRAMES):
        current = np.full(NUM_FRAMES + 1, np.inf, dtype=np.float32)
        for j in range(max(0, i-band), min(NUM_FRAMES, i+band+1)):
            current[j+1] = costs[i,j] + min(previous[j],
                           previous[j+1] + 0.045, current[j] + 0.045)
        previous = current
    length_penalty = min(0.24, abs(math.log(max(da,0.1) / max(db,0.1))) * 0.10)
    return float(np.clip(1.0 - previous[-1] / NUM_FRAMES - length_penalty, -1.0, 1.0))

class DTWBank:
    def __init__(self, samples=None):
        self.samples = {}
        for spell, examples in (samples or {}).items():
            if not isinstance(spell, str) or not spell.isascii() or not spell.isalnum():
                continue
            valid = []
            for sample in examples:
                try:
                    features = np.asarray(sample["features"], dtype=np.float32)
                    duration = float(sample["duration"])
                    if (features.shape == (NUM_FRAMES, FEAT_DIM)
                        and np.isfinite(features).all() and 0.19 <= duration <= 2.5):
                        valid.append({"features": features.tolist(), "duration": duration})
                except (TypeError, KeyError, ValueError):
                    pass
            if valid:
                self.samples[spell] = valid[-6:]

    @classmethod
    def load(cls, path: Path | None = None):
        path = path or model_path()
        if not path.exists():
            return cls()
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        if data.get("version") != VERSION:
            raise ValueError("Несовместимая версия базы произношений")
        return cls(data.get("samples", {}))

    def save(self, path: Path | None = None):
        target = path or model_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as file:
            json.dump({"version": VERSION, "samples": self.samples},
                      file, ensure_ascii=False)
        os.replace(tmp, target)

    def add(self, spell: str, pcm: bytes):
        if not spell or not spell.isascii() or not spell.isalnum():
            raise ValueError("Invalid spell name")
        features, duration = extract(pcm)
        self.samples.setdefault(spell, []).append({
            "features": np.round(features, 5).tolist(),
            "duration": round(duration, 3),
        })
        self.samples[spell] = self.samples[spell][-6:]
        return self.count(spell)

    def count(self, spell: str):
        return len(self.samples.get(spell, []))

    def trained(self, spell: str):
        return self.count(spell) >= MIN_TAKES

    def trained_spells(self):
        return {s for s in self.samples if self.trained(s)}

    def clear(self, spell: str):
        self.samples.pop(spell, None)

    def rank(self, pcm: bytes):
        if not self.trained_spells():
            return []
        x, duration = extract(pcm)
        # Cheap diagonal correlation prefilter; only compare the 8 likeliest
        # commands with DTW to bound CPU latency as the vocabulary grows.
        rough = []
        for spell in sorted(self.trained_spells()):
            samples = self.samples[spell]
            best = max(float(np.mean(np.sum(x * np.asarray(e["features"]), axis=1)))
                       for e in samples)
            rough.append((spell, best))
        short = sorted(rough, key=lambda pair: pair[1], reverse=True)[:8]
        scored = []
        for spell, _ in short:
            scores = sorted(
                (_dtw(x, e["features"], duration, e["duration"])
                 for e in self.samples[spell]),
                reverse=True,
            )
            scored.append((spell, float(np.mean(scores[:2]))))
        return sorted(scored, key=lambda pair: pair[1], reverse=True)

    def match(self, pcm: bytes, *, threshold=MIN_SCORE, margin=MIN_MARGIN):
        ranking = self.rank(pcm)
        if not ranking:
            return None, 0.0, "no trained commands"
        spell, score = ranking[0]
        second = ranking[1][1] if len(ranking)>1 else -1
        if score < threshold:
            return None, round(score,3), "low acoustic similarity"
        if score - second < margin:
            return None, round(score,3), "ambiguous: too similar to another spell"
        return spell, round(score,3), "recognized"

    def quality(self, spell: str) -> float | None:
        """Pairwise agreement of training examples (not a confidence guarantee)."""
        take = self.samples.get(spell, [])
        if len(take) < MIN_TAKES:
            return None
        values = [
            _dtw(take[i]["features"], take[j]["features"],
                 take[i]["duration"], take[j]["duration"])
            for i in range(len(take)) for j in range(i+1,len(take))
        ]
        return float(np.median(values))
