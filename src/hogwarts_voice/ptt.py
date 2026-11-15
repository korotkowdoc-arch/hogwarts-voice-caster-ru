"""One push-to-talk hold = one utterance, without silence detection.

Audio is captured only while the button is held. The key-up event closes
the phrase and hands it to the acoustic matcher once. Invalid lengths are
rejected, never split into two spells or silently truncated.
"""
from __future__ import annotations

from .dtw_voice import SAMPLE_RATE

MIN_DURATION_MS = 190
MAX_DURATION_MS = 2500
KEYS = {
    "F9": 0x78,
    "F10": 0x79,
    "F11": 0x7A,
    "Mouse4": 0x05,
    "Mouse5": 0x06,
}

def key_code(name: str) -> int:
    try:
        return KEYS[name]
    except KeyError:
        raise ValueError(f"Unknown PTT key: {name}. Choose {', '.join(KEYS)}") from None

class PushToTalkCapture:
    def __init__(self, *, samplerate=SAMPLE_RATE,
                 minimum_ms=MIN_DURATION_MS, maximum_ms=MAX_DURATION_MS):
        self.samplerate = samplerate
        self.minimum_ms = minimum_ms
        self.maximum_ms = maximum_ms
        self.reset()

    def reset(self):
        self.held = False
        self.frames = []
        self.nbytes = 0
        self.overlong = False
        self.presses = 0

    def press(self):
        """Start a fresh attempt; never carry audio from another hold."""
        if self.held:
            return False
        self.held = True
        self.frames = []
        self.nbytes = 0
        self.overlong = False
        self.presses += 1
        return True

    def add(self, pcm: bytes):
        if not self.held or self.overlong:
            return
        if not pcm or len(pcm) % 2:
            return
        self.nbytes += len(pcm)
        if self.nbytes > self.maximum_ms * self.samplerate * 2 / 1000:
            # Reject overlong speech instead of casting first 2.5 seconds.
            self.overlong = True
            self.frames.clear()
            return
        self.frames.append(pcm)

    def release(self):
        """Return (PCM or None, duration_ms, reason).

        Only key-up finishes a phrase, exactly once. The caller is free to
        match asynchronously and must still reject ambiguous matches.
        """
        if not self.held:
            return None, 0.0, "not recording"
        self.held = False
        ms = self.nbytes * 1000.0 / (2 * self.samplerate)
        if self.overlong or ms > self.maximum_ms:
            result, reason = None, "too long"
        elif ms < self.minimum_ms:
            result, reason = None, "too short"
        else:
            result, reason = b"".join(self.frames), "captured"
        self.frames = []
        self.nbytes = 0
        self.overlong = False
        return result, ms, reason
