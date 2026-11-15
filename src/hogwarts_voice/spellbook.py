"""Incantation normalization and longest-match spell lookup."""
from __future__ import annotations

import re
from typing import Mapping, Sequence

# Short expressions are intentionally conservative to reduce false positives.
DEFAULT_SPELLS: dict[str, list[str]] = {
    "Accio": ["акцио", "аксио"],
    "Levioso": ["левиосо", "левиоза"],
    "Depulso": ["депульсо", "депулсо"],
    "Descendo": ["десцендо", "десендо"],
    "Flipendo": ["флипендо"],
    "Glacius": ["глациус", "гляциус"],
    "ArrestoMomentum": ["арресто моментум", "аресто моментум"],
    "Incendio": ["инсендио", "инцендио"],
    "Confringo": ["конфринго"],
    "Diffindo": ["диффиндо", "дифиндо"],
    "Bombarda": ["бомбарда"],
    "Stupefy": ["ступефай", "ступефи"],
    "Expelliarmus": ["экспеллиармус", "экспелиармус"],
    "Protego": ["протего"],
    "Oppugno": ["оппуньо", "оппугно"],
    "Lumos": ["люмос", "люмус"],
    "Nox": ["нокс"],
    "Reparo": ["репаро"],
    "Revelio": ["ревелио"],
    "Disillusionment": ["дезиллюминация", "невидимость"],
    "Wingardium": ["вингардиум левиоса", "вингардиум"],
    "Transformation": ["трансформация", "трансфигурация"],
    "Vanishment": ["эванеско"],
    "Crucio": ["круцио"],
    "Imperius": ["империо", "империус"],
    "AvadaKedavra": ["авада кедавра"],
    "Finisher": ["древняя магия"],
    "AppareVestigium": ["аппаре вестигиум"],
    "Alohomora": ["алохомора"],
    "Finite": ["фините", "фините инкантатем"],
    "Broomstick": ["акцио метла", "вызови метлу"],
    "Map": ["открой карту", "апперта маппа"],
    "Inventory": ["открой инвентарь", "апперта кодекс"],
}

_WORDS = re.compile(r"[^\w\s]+", re.UNICODE)

def normalize(text: str) -> str:
    return " ".join(_WORDS.sub(" ", text.casefold().replace("ё", "е")).split())

class Spellbook:
    def __init__(self, entries: Mapping[str, Sequence[str]]):
        self.entries: dict[str, list[str]] = {}
        self.lookup: dict[tuple[str, ...], str] = {}
        for spell, phrases in entries.items():
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,26}", spell):
                raise ValueError(f"Invalid ASCII game spell name: {spell!r}")
            self.entries[spell] = []
            for phrase in phrases:
                clean = normalize(phrase)
                if not clean:
                    continue
                key = tuple(clean.split())
                prior = self.lookup.get(key)
                if prior and prior != spell:
                    raise ValueError(f"Phrase {phrase!r} maps to both {prior} and {spell}")
                self.lookup[key] = spell
                if clean not in self.entries[spell]:
                    self.entries[spell].append(clean)
        self.max_words = max(map(len, self.lookup), default=1)

    def grammar(self) -> list[str]:
        return sorted({" ".join(phrase) for phrase in self.lookup}) + ["[unk]"]

    def parse(self, transcript: str) -> list[str]:
        """Extract longest exact incantations, possibly several in one utterance."""
        words = normalize(transcript).split()
        out = []
        i = 0
        while i < len(words):
            for width in range(min(self.max_words, len(words) - i), 0, -1):
                spell = self.lookup.get(tuple(words[i:i+width]))
                if spell:
                    out.append(spell)
                    i += width
                    break
            else:
                i += 1
        return out

