"""Fast partial-result command gate, isolated for deterministic tests."""
from __future__ import annotations

import time

class StreamGate:
    """Emit each recognised occurrence once, even from a live partial result."""
    def __init__(self, spellbook, stable_updates=2, min_gap_ms=0, repeat_gap_ms=500):
        if stable_updates < 1:
            raise ValueError("stable_updates must be >= 1")
        self.spellbook = spellbook
        self.stable_updates = stable_updates
        self.min_gap = min_gap_ms / 1000.0
        self.repeat_gap = repeat_gap_ms / 1000.0
        self._stable_list: tuple[str, ...] = ()
        self._stable_count = 0
        self._emitted = 0
        self._last_spell = None
        self._last_at = float("-inf")

    def feed(self, transcript: str, *, final=False, now=None) -> list[str]:
        if now is None:
            now = time.monotonic()
        sequence = tuple(self.spellbook.parse(transcript))
        if sequence == self._stable_list:
            self._stable_count += 1
        else:
            self._stable_list = sequence
            self._stable_count = 1
        result = []
        if (final or self._stable_count >= self.stable_updates) and len(sequence) > self._emitted:
            for spell in sequence[self._emitted:]:
                gap = self.repeat_gap if spell == self._last_spell else self.min_gap
                if now - self._last_at >= gap:
                    result.append(spell)
                    self._last_at = now
                    self._last_spell = spell
            self._emitted = len(sequence)
        if final:
            self.reset_segment()
        return result

    def reset_segment(self):
        self._stable_list = ()
        self._stable_count = 0
        self._emitted = 0

