"""Resemblyzer speaker-embedding backend, loaded lazily.

VoiceEncoder runs locally, no account/cloud. It uses ~1.6s windows internally,
so individual fast commands may lack enough speech for reliable verification.
"""
from __future__ import annotations

import numpy as np

from .voice_profile import VoiceProfile

MIN_VOICED_SECONDS = 0.55
SAMPLE_RATE = 16000

class SpeakerEncoder:
    def __init__(self):
        try:
            from resemblyzer import VoiceEncoder, preprocess_wav
        except ImportError as exc:
            raise RuntimeError("Speaker model unavailable: reinstall with install.bat") from exc
        self.preprocess_wav = preprocess_wav
        self.encoder = VoiceEncoder("cpu")

    def encode_float(self, wav) -> list[float]:
        data = np.asarray(wav, dtype=np.float32).flatten()
        if len(data) < SAMPLE_RATE * MIN_VOICED_SECONDS or np.max(np.abs(data)) < 0.015:
            raise ValueError("Voice too short or too quiet")
        trimmed = self.preprocess_wav(data, source_sr=SAMPLE_RATE)
        if len(trimmed) < SAMPLE_RATE * MIN_VOICED_SECONDS:
            raise ValueError("Not enough voiced audio; speak longer and closer to the mic")
        embedding = self.encoder.embed_utterance(trimmed)
        return embedding.tolist()

    def encode_pcm16(self, pcm: bytes) -> list[float]:
        if len(pcm) % 2:
            raise ValueError("Invalid 16-bit PCM length")
        data = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
        return self.encode_float(data)

class SpeakerVerifier:
    def __init__(self, profile: VoiceProfile, threshold: float = 0.68):
        if not profile.ready():
            raise RuntimeError("Voice profile incomplete; open Voice Setup")
        if not 0.50 <= threshold <= 0.95:
            raise ValueError("speaker_threshold must be between 0.50 and 0.95")
        self.profile = profile
        self.threshold = threshold
        self.encoder = SpeakerEncoder()

    def verify_pcm(self, pcm: bytes) -> tuple[bool, float]:
        try:
            voice = self.encoder.encode_pcm16(pcm)
            return self.profile.match(voice, self.threshold)
        except ValueError:
            return False, 0.0
