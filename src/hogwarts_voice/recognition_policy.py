"""Safety-first routing for combined acoustic + Vosk spell recognition.

Vosk partials from a constrained vocabulary may be guesses, NOT verified
commands. Never cast an unrelated word when known samples failed to match.
"""
from __future__ import annotations

def route_spells(*, trained_spells, acoustic_spell, vosk_candidates,
                 allow_untrained_fallback=False):
    """Returns a list of approved spell names (never raw guesses)."""
    if acoustic_spell:
        return [acoustic_spell] if acoustic_spell in trained_spells else []
    # If trained templates exist, an acoustic mismatch must not be
    # overridden by an arbitrary speech-to-text vocabulary guess.
    if trained_spells and not allow_untrained_fallback:
        return []
    for spell in vosk_candidates:
        if spell not in trained_spells:
            return [spell]
    return []
