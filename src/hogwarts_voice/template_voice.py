"""Experimental, purely local per-word pronunciation templates.

A pronunciation sample is a compressed log-mel spectral trajectory, NOT raw
audio and NOT a speaker authentication template. Compare fixed-size spectral
trajectories for a small user-trained command vocabulary. Requires no cloud
service or extra packages beyond NumPy (already needed by the app).

This is a lightweight acoustic matcher, not a guaranteed speech recognizer.
Scores depend on microphone/noise. In particular, unrelated words can match
if pronounced similarly; validate with real positive AND negative samples.
"""
from __future__ import annotations

from collections import deque
import json
import math
import os
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000
MIN_SECONDS = 0.18
MAX_SECONDS = 2.6
FEATURE_FRAMES = 32
FEATURE_DIM = 15
VERSION = 1
MIN_TAKES = 3
MIN_SCORE = 0.78
MIN_MARGIN = 0.055

def bank_path() -> Path:
    base = Path(os.getenv("LOCALAPPDATA") or (Path.home() / ".local" / "share"))
    return base / "HogwartsVoiceCasterRU" / "pronunciation_templates.json"

def _mel(hz):
    return 2595.0 * np.log10(1.0 + hz / 700.0)

def _hz(mel):
    return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)

def _melbank():
    nfft = 512
    hz = _hz(np.linspace(_mel(100), _mel(7700), 28))
    bins = np.floor((nfft + 1) * hz / SAMPLE_RATE).astype(int)
    filt = np.zeros((26, nfft // 2 + 1), dtype=np.float32)
    for j in range(26):
        a, b, c = bins[j:j+3]
        if not a < b < c:
            continue
        filt[j, a:b] = np.linspace(0, 1, b - a, endpoint=False)
        filt[j, b:c] = np.linspace(1, 0, c - b, endpoint=False)
    return filt

MELBANK = _melbank()
DCT = np.cos(np.pi / 26.0 * (np.arange(FEATURE_DIM)[:, None] *
                             (np.arange(26)[None, :] + 0.5))).astype(np.float32)

def extract(pcm: bytes):
    """Return (trajectory[32,15], duration) or raise for silence/too-short.

    Trim silence from 16k mono PCM16, 25 ms Hanning windows, 10 ms step.
    Resample temporal MFCC trajectory to fixed length; discards raw waveform.
    """
    if len(pcm) % 2:
        raise ValueError("Invalid PCM16 data")
    signal = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
    if signal.size < int(MIN_SECONDS * SAMPLE_RATE):
        raise ValueError("Too little speech")
    # Segment energy measured every 10 ms, 20ms window.
    hop = 160
    usable = signal[:(len(signal) // hop) * hop]
    power = np.sqrt(np.mean(usable.reshape(-1, hop) ** 2, axis=1))
    peak = float(power.max(initial=0))
    if peak < 0.018:
        raise ValueError("No audible speech")
    active = np.where(power >= max(0.015, peak * 0.22))[0]
    if len(active) < 12:
        raise ValueError("Speech is too short")
    start = max(0, int(active[0] * hop - 480))
    end = min(len(signal), int((active[-1] + 1) * hop + 480))
    voiced = signal[start:end]
    duration = len(voiced) / SAMPLE_RATE
    if not MIN_SECONDS <= duration <= MAX_SECONDS:
        raise ValueError("Spell must be between 0.18 and 2.6 seconds")
    # Pre-emphasis and strided FFT frames.
    voiced = np.concatenate((voiced[:1], voiced[1:] - 0.97 * voiced[:-1]))
    if len(voiced) < 400:
        raise ValueError("Too short for spectral analysis")
    frames = np.lib.stride_tricks.sliding_window_view(voiced, 400)[::hop]
    spectrum = np.abs(np.fft.rfft(frames * np.hanning(400), n=512, axis=1)) ** 2
    mel = np.log(np.maximum(1e-9, spectrum @ MELBANK.T))
    mfcc = mel @ DCT.T
    mfcc = mfcc[:, 1:]  # remove the loudness coefficient
    # Remove global microphone colour, retaining temporal phoneme changes.
    mfcc -= mfcc.mean(axis=0, keepdims=True)
    norms = np.linalg.norm(mfcc, axis=1, keepdims=True)
    mfcc /= np.maximum(norms, 1e-4)
    t = np.linspace(0, len(mfcc) - 1, FEATURE_FRAMES)
    i = np.floor(t).astype(int)
    j = np.minimum(i + 1, len(mfcc) - 1)
    portion = (t - i)[:, None]
    sampled = mfcc[i] * (1 - portion) + mfcc[j] * portion
    # Each row is an L2-normalized, spectral-change vector.
    sampled /= np.maximum(np.linalg.norm(sampled, axis=1, keepdims=True), 1e-4)
    return sampled.astype(np.float32), duration

def similarity(a, b, dur_a, dur_b):
    aa = np.asarray(a, dtype=np.float32)
    bb = np.asarray(b, dtype=np.float32)
    if aa.shape != (FEATURE_FRAMES, FEATURE_DIM - 1) or bb.shape != aa.shape:
        raise ValueError("Invalid pronunciation feature shape")
    cosine = float(np.mean(np.sum(aa * bb, axis=1)))
    length_penalty = min(0.25, abs(math.log(max(dur_a, 0.1) / max(dur_b, 0.1))) * 0.12)
    return max(-1.0, min(1.0, cosine - length_penalty))

class PronunciationBank:
    def __init__(self, samples=None):
        self.samples: dict[str, list[dict]] = {}
        for spell, items in (samples or {}).items():
            if not isinstance(items, list) or not spell.isascii():
                continue
            approved = []
            for item in items:
                try:
                    shape = np.asarray(item["features"], dtype=np.float32)
                    dur = float(item["duration"])
                    if shape.shape != (FEATURE_FRAMES, FEATURE_DIM - 1):
                        continue
                    if not np.isfinite(shape).all() or not MIN_SECONDS <= dur <= MAX_SECONDS:
                        continue
                    approved.append({"features": shape.tolist(), "duration": dur})
                except (ValueError, KeyError, TypeError):
                    continue
            if approved:
                self.samples[spell] = approved[-6:]

    @classmethod
    def load(cls, path: Path | None = None):
        dest = path or bank_path()
        if not dest.is_file():
            return cls()
        with dest.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("version") != VERSION:
            raise ValueError("Unsupported pronunciation template version")
        return cls(data.get("samples", {}))

    def save(self, path: Path | None = None):
        dest = path or bank_path()
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump({"version": VERSION, "samples": self.samples}, f, ensure_ascii=False)
        os.replace(tmp, dest)

    def count(self, spell):
        return len(self.samples.get(spell, []))

    def trained(self, spell):
        return self.count(spell) >= MIN_TAKES

    def clear(self, spell: str):
        """Remove only one spell's invalid training examples."""
        self.samples.pop(spell, None)

    def trained_spells(self):
        return {spell for spell in self.samples if self.trained(spell)}

    def add(self, spell: str, pcm: bytes):
        if not spell or not spell.isascii() or not spell.isalnum():
            raise ValueError("Invalid game spell")
        arr, duration = extract(pcm)
        self.samples.setdefault(spell, []).append({
            "features": np.round(arr, 5).tolist(),
            "duration": round(duration, 3),
        })
        self.samples[spell] = self.samples[spell][-6:]
        return self.count(spell)

    def rank(self, pcm: bytes):
        if not self.trained_spells():
            return []
        features, duration = extract(pcm)
        scores = []
        for spell in self.trained_spells():
            entries = self.samples[spell]
            # Best of recorded pronunciations, not a generic language guess.
            sims = sorted((similarity(features, e["features"], duration, e["duration"])
                          for e in entries), reverse=True)
            scores.append((spell, float(np.mean(sims[:2]))))
        return sorted(scores, key=lambda x: x[1], reverse=True)

    def match(self, pcm: bytes, *, threshold=MIN_SCORE, margin=MIN_MARGIN):
        scores = self.rank(pcm)
        if not scores:
            return None, 0.0, "not trained"
        first, score = scores[0]
        runner = scores[1][1] if len(scores) > 1 else -1.0
        if score < threshold:
            return None, round(score, 3), "low similarity"
        if score - runner < margin:
            return None, round(score, 3), "ambiguous pronunciation"
        return first, round(score, 3), "matched"

class SpeechSegmenter:
    """Streaming 20ms audio segmenter; triggers after ~100ms silence.

    Only volatile PCM buffers are kept and cleared on each detected pause.
    """
    def __init__(self, sample_rate=16000, silence_ms=100, min_ms=180, max_ms=2600):
        self.samplerate = sample_rate
        self.silence_ms = silence_ms
        self.min_ms = min_ms
        self.max_ms = max_ms
        self.reset()

    def reset(self):
        self.preroll = deque(maxlen=5)
        self.frames = []
        self.active = False
        self.silent_ms = 0

    def feed(self, pcm: bytes):
        import audioop
        if not pcm:
            return None
        duration_ms = len(pcm) / 2 / self.samplerate * 1000
        amplitude = audioop.rms(pcm, 2)
        voiced = amplitude > 680
        self.preroll.append(pcm)
        if voiced and not self.active:
            self.active = True
            self.frames = list(self.preroll)
            self.silent_ms = 0
            return None
        if not self.active:
            return None
        self.frames.append(pcm)
        self.silent_ms = 0 if voiced else self.silent_ms + duration_ms
        elapsed = sum(len(x) for x in self.frames) * 1000 / (self.samplerate * 2)
        ended = self.silent_ms >= self.silence_ms or elapsed >= self.max_ms
        if not ended:
            return None
        result = b"".join(self.frames)
        self.reset()
        if elapsed < self.min_ms:
            return None
        return result
