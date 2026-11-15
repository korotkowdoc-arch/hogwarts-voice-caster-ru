"""Offline Russian neural ASR (GigaAM v2 CTC via sherpa-onnx).

The neural network transcribes Russian phonemes; spell selection is a separate,
strict whitelist. No Vosk constrained-language guesses or DTW enrollment.
The network is loaded ONCE per listening session.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
import numpy as np
from .voice_presets import (
    DEFAULT_STYLE, STYLE_ROSMEN, spoken_aliases, visible_name,
    validate_style, is_book_mode_literal_exception,
)

MODEL_NAME = "gigaam-v2-ru-ctc-int8"
MODEL_FILE = "model.int8.onnx"
TOKENS_FILE = "tokens.txt"
# Keep in a stable path; Windows ONNX native libraries are sensitive to exotic
# paths on some builds, as previously observed with Vosk.
def model_directory() -> Path:
    from .model_storage import installed_model_path
    project_root = Path(__file__).resolve().parents[2]
    return installed_model_path(project_root).parent / MODEL_NAME

# A general word hallucination must not turn into a magic command. These two
# spells are the starter whitelist; enable more explicitly in config.json.
DEFAULT_ENABLED = ("Lumos", "Accio")
# These ordinary Russian descriptions are intentionally NOT accepted as
# incantations, even if they appear in the legacy spells.json.
UNSAFE_GENERIC_ALIASES = frozenset({
    "невидимость", "древняя магия", "трансформация",
    "трансфигурация", "путь к цели"
})
# Short contextual commands must match exactly. Fuzzy matching "open the map"
# with a conversational phrase would be unsafe in live gameplay.
EXACT_ONLY_COMMANDS = frozenset({
    "Alohomora", "Finite", "Broomstick", "Map", "Inventory",
})
EXTRA_PRONUNCIATIONS = {
    "Lumos": ("люмос", "люмус", "люмас"),
    "Accio": ("акцио", "аксио"),
    # Genuine GigaAM output observed during real user testing.
    # Keep it as an explicit alias, not unrestricted phonetic fuzziness.
    "Expelliarmus": ("экспелярмус",),
}

def normalized(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold().replace("ё", "е")
    text = re.sub(r"[^а-яa-z\s-]+", " ", text)
    return " ".join(text.replace("-", " ").split())

def _edit_distance(a: str, b: str) -> int:
    if abs(len(a) - len(b)) > 1:
        return 2
    prev = list(range(len(b) + 1))
    for i, char in enumerate(a, 1):
        row = [i]
        for j, target in enumerate(b, 1):
            row.append(min(row[-1] + 1, prev[j] + 1, prev[j-1] + (char != target)))
        prev = row
    return prev[-1]

def match_incantation(text: str, spellbook: dict[str, list[str]],
                      enabled=None, *, style: str = "original"):
    """Return (spell|None, status) with NO casts for unknown/ambiguous text.

    Unlike a closed-vocabulary ASR decoder, the neural text is never forced
    to pick a spell: empty and unrelated words are rejected.
    """
    validate_style(style)
    heard = normalized(text)
    if not heard or len(heard) > 42:
        return None, "empty or excessively long transcript"
    allowed = set(DEFAULT_ENABLED if enabled is None else enabled)
    candidates = []
    for spell, aliases in spellbook.items():
        if spell not in allowed:
            continue
        forms = spoken_aliases(spell,
            set(aliases) | set(EXTRA_PRONUNCIATIONS.get(spell, ())), style)
        for alias in forms:
            target = normalized(alias)
            book_exception = is_book_mode_literal_exception(spell, target, style)
            if not target or (target in UNSAFE_GENERIC_ALIASES and not book_exception):
                continue
            if heard == target:
                candidates.append((spell, "exact"))
            # The special book-style phrases must match EXACTLY. Otherwise
            # a normal word such as "остолбенеть" may accidentally cast.
            elif (not book_exception and spell not in EXACT_ONLY_COMMANDS
                  and not (style == STYLE_ROSMEN
                           and target == normalized(visible_name(spell, style)))
                  and len(target) >= 9 and len(heard) >= 9
                  and _edit_distance(heard, target) == 1):
                candidates.append((spell, "one character different"))
    spells = {name for name, _ in candidates}
    if len(spells) == 1:
        return spells.pop(), candidates[0][1]
    if len(spells) > 1:
        return None, "ambiguous between several incantations"
    return None, "not an enabled incantation"

def load_spell_aliases(path: Path | None = None):
    path = path or (Path(__file__).resolve().parents[2] / "spells.json")
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("spells.json must be an object")
    # Preserve user-edited aliases and introduce new supported game actions
    # without forcing old installations to replace their spells.json.
    from .spellbook import DEFAULT_SPELLS as BUILTIN_SPELLS
    for command, aliases in BUILTIN_SPELLS.items():
        data.setdefault(command, list(aliases))
    return data

class RussianASR:
    def __init__(self, *, model_dir=None, num_threads=4, recognizer=None):
        self.model_dir = Path(model_dir or model_directory())
        self.num_threads = num_threads
        if recognizer is not None:
            self.recognizer = recognizer
            return
        network = self.model_dir / MODEL_FILE
        tokens = self.model_dir / TOKENS_FILE
        if not network.is_file() or network.stat().st_size < 150_000_000:
            raise FileNotFoundError(
                f"Русская нейромодель не установлена: {network}. "
                "Запусти install.bat из последней версии проекта."
            )
        if not tokens.is_file() or tokens.stat().st_size < 100:
            raise FileNotFoundError(f"Отсутствует словарь GigaAM: {tokens}")
        import sherpa_onnx
        self.recognizer = sherpa_onnx.OfflineRecognizer.from_nemo_ctc(
            model=str(network),
            tokens=str(tokens),
            num_threads=num_threads,
            sample_rate=16000,
            feature_dim=80,
            provider="cpu",
            debug=False,
        )

    def transcribe(self, pcm: bytes) -> str:
        if len(pcm) % 2 or len(pcm) < 16000 * 2 * .19:
            raise ValueError("Too little audio for Russian ASR")
        audio = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
        if not np.isfinite(audio).all():
            raise ValueError("Invalid audio")
        if float(np.sqrt(np.mean(audio * audio))) < 0.009:
            return ""
        # Neural CTC decoders benefit from a tiny amount of symmetric context.
        padded = np.pad(audio, (1600, 1600))
        stream = self.recognizer.create_stream()
        stream.accept_waveform(16000, padded)
        self.recognizer.decode_stream(stream)
        return str(stream.result.text).strip()
