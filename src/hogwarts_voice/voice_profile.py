"""Locally stored speaker embeddings; raw microphone audio is never persisted.

This is best-effort speaker similarity, NOT strong biometric authentication.
A recording of the owner may be accepted, and short commands are unreliable.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
from typing import Sequence

PROFILE_VERSION = 1
VECTOR_DIM = 256
MIN_READY_TAKES = 6
MIN_READY_SPELLS = 2

def profile_path() -> Path:
    base = Path(os.getenv("LOCALAPPDATA") or (Path.home() / ".local" / "share"))
    return base / "HogwartsVoiceCasterRU" / "voice_profile.json"

def normalize_vector(values: Sequence[float]) -> list[float]:
    if len(values) != VECTOR_DIM:
        raise ValueError(f"Expected {VECTOR_DIM} speaker features")
    v = [float(x) for x in values]
    if not all(math.isfinite(x) for x in v):
        raise ValueError("Invalid voice feature")
    norm = math.sqrt(sum(x * x for x in v))
    if norm < 1e-9:
        raise ValueError("Empty voice feature")
    return [x / norm for x in v]

def similarity(a: Sequence[float], b: Sequence[float]) -> float:
    u = normalize_vector(a)
    v = normalize_vector(b)
    return sum(x * y for x, y in zip(u, v))

def acceptable_alias(text: str) -> bool:
    return bool(re.fullmatch(r"[а-яё][а-яё -]{3,47}", text.casefold().strip())) and len(text.split()) <= 4

class VoiceProfile:
    def __init__(self, *, takes=None, aliases=None):
        self.takes: dict[str, list[list[float]]] = {}
        for name, embeddings in (takes or {}).items():
            if isinstance(name, str) and isinstance(embeddings, list):
                self.takes[name] = [normalize_vector(vector) for vector in embeddings]
        self.aliases: dict[str, list[str]] = {}
        for name, phrases in (aliases or {}).items():
            if isinstance(name, str) and isinstance(phrases, list):
                self.aliases[name] = [str(x) for x in phrases if isinstance(x, str) and acceptable_alias(x)]

    @classmethod
    def load(cls, path: Path | None = None) -> "VoiceProfile":
        p = path or profile_path()
        if not p.exists():
            return cls()
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("version") != PROFILE_VERSION:
            raise ValueError("Unknown voice profile version")
        return cls(takes=data.get("takes", {}), aliases=data.get("aliases", {}))

    def save(self, path: Path | None = None) -> None:
        p = path or profile_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        # Atomic update: losing power during save must not corrupt previous profile.
        target = p.with_name(p.name + ".tmp")
        with target.open("w", encoding="utf-8") as f:
            json.dump({"version": PROFILE_VERSION, "takes": self.takes,
                       "aliases": self.aliases}, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(target, p)

    def add_take(self, spell: str, embedding: Sequence[float]) -> int:
        if not spell or not spell.isascii() or not spell.replace("_", "").isalnum():
            raise ValueError("Invalid spell")
        self.takes.setdefault(spell, []).append(normalize_vector(embedding))
        # Per-spell cap avoids accidentally growing the profile without bound.
        self.takes[spell] = self.takes[spell][-6:]
        return len(self.takes[spell])

    def count(self, spell: str) -> int:
        return len(self.takes.get(spell, []))

    def ready(self) -> bool:
        total = sum(len(v) for v in self.takes.values())
        return total >= MIN_READY_TAKES and sum(bool(v) for v in self.takes.values()) >= MIN_READY_SPELLS

    def centroid(self) -> list[float]:
        all_vectors = [x for vectors in self.takes.values() for x in vectors]
        if not all_vectors:
            raise ValueError("Empty voice profile")
        avg = [sum(v[i] for v in all_vectors) / len(all_vectors) for i in range(VECTOR_DIM)]
        return normalize_vector(avg)

    def match(self, embedding: Sequence[float], threshold: float = 0.68) -> tuple[bool, float]:
        if not self.ready():
            return False, 0.0
        score = similarity(self.centroid(), embedding)
        return score >= threshold, round(score, 3)

    def add_alias(self, spell: str, phrase: str, book) -> None:
        from .spellbook import Spellbook, normalize
        phrase = normalize(phrase)
        if not acceptable_alias(phrase) or spell not in book.entries:
            raise ValueError("Too short or invalid pronunciation")
        entries = {key: list(val) for key, val in book.entries.items()}
        for saved_spell, aliases in self.aliases.items():
            if saved_spell in entries:
                entries[saved_spell].extend(aliases)
        entries[spell].append(phrase)
        Spellbook(entries)  # rejects ambiguous aliases
        existing = self.aliases.setdefault(spell, [])
        if phrase not in existing:
            existing.append(phrase)

    def merged_book(self, book):
        from .spellbook import Spellbook
        merged = {spell: list(phrases) for spell, phrases in book.entries.items()}
        for spell, phrases in self.aliases.items():
            if spell in merged:
                merged[spell].extend(phrases)
        return Spellbook(merged)
