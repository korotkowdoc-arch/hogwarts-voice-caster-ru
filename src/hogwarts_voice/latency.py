"""Lightweight onset timing. This estimates speech-start to command dispatch.

A speech onset estimate includes the time needed to pronounce the word.
It is NOT a pure recognizer latency or an acoustic word-end timestamp.
"""
from __future__ import annotations

import audioop

class AudioDelayMeter:
    def __init__(self, rms_threshold=650, release_ms=330):
        self.threshold = rms_threshold
        self.release_s = release_ms / 1000.0
        self.onset = None
        self.quiet_since = None

    def observe(self, pcm: bytes, captured_at: float):
        level = audioop.rms(pcm, 2)
        if level >= self.threshold:
            if self.onset is None:
                self.onset = captured_at
            self.quiet_since = None
        elif self.onset is not None:
            if self.quiet_since is None:
                self.quiet_since = captured_at
            elif captured_at - self.quiet_since >= self.release_s:
                self.reset()
        return self.onset

    def reset(self):
        self.onset = None
        self.quiet_since = None
