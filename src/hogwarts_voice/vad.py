"""Adaptive low-latency speech segmenter for 16-kHz mono PCM16.

A fixed RMS gate of 680 was breaking Russian spell names at their quiet
consonants. This detector adapts to background noise, uses a lower level for
continuing a word, preserves a pre-roll and tolerates internal pauses.
It is NOT a speech recognizer and does not produce game commands.
"""
from __future__ import annotations
import audioop
from collections import deque

class AdaptiveSpeechSegmenter:
    def __init__(self, sample_rate=16000, silence_ms=170, min_speech_ms=170,
                 max_ms=2600, preroll_ms=120):
        self.samplerate = sample_rate
        self.silence_ms = silence_ms
        self.min_speech_ms = min_speech_ms
        self.max_ms = max_ms
        self.preroll_ms = preroll_ms
        self.reset()

    def reset(self):
        self.noise_rms = 115.0
        self.preroll = deque()
        self.preroll_duration = 0.0
        self.frames = []
        self.active = False
        self.strong_run = 0
        self.speech_ms = 0.0
        self.silence_ms_seen = 0.0
        self.total_ms = 0.0

    def feed(self, pcm: bytes) -> bytes | None:
        if not pcm or len(pcm) % 2:
            return None
        ms = len(pcm) * 1000.0 / (2 * self.samplerate)
        rms = audioop.rms(pcm, 2)
        # Keep the start of quiet consonants even when the loud vowel follows.
        self.preroll.append(pcm)
        self.preroll_duration += ms
        while self.preroll_duration > self.preroll_ms + ms and len(self.preroll)>1:
            evicted = self.preroll.popleft()
            self.preroll_duration -= len(evicted) * 1000.0 / (2*self.samplerate)

        onset_level = max(370.0, self.noise_rms * 2.9)
        continue_level = max(185.0, self.noise_rms * 1.65)

        if not self.active:
            if rms >= onset_level:
                self.strong_run += 1
            else:
                self.strong_run = 0
                # Background level only learns while waiting for speech.
                self.noise_rms = (self.noise_rms * .975 + min(rms, onset_level) * .025)
            if self.strong_run < 2:
                return None
            self.active = True
            self.frames = list(self.preroll)
            self.total_ms = sum(len(f) for f in self.frames)*1000/(2*self.samplerate)
            self.speech_ms = 2*ms
            self.silence_ms_seen = 0.
            return None

        self.frames.append(pcm)
        self.total_ms += ms
        if rms >= continue_level:
            self.speech_ms += ms
            self.silence_ms_seen = 0
        else:
            self.silence_ms_seen += ms

        finish = self.silence_ms_seen >= self.silence_ms or self.total_ms >= self.max_ms
        if not finish:
            return None
        # Reject clicks and very short fragments rather than casting random
        # trained spells. Long phrases are also rejected, never truncated.
        valid = self.speech_ms >= self.min_speech_ms and self.total_ms < self.max_ms
        result = b"".join(self.frames) if valid else None
        preserved_noise = self.noise_rms
        self.reset()
        self.noise_rms = preserved_noise
        return result
