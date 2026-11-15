"""Explicit user-facing Russian incantation presets.

'rosmen' is a book-inspired voice mode, NOT a claim that every spell here
occurred in the Rosmen novels. Some game-only spells keep their game names.

The selected spoken phrase never goes directly to the game bridge.
"""
from __future__ import annotations

STYLE_ORIGINAL = "original"
STYLE_ROSMEN = "rosmen"
STYLE_LABELS = {
    STYLE_ORIGINAL: "Оригинальные формулы",
    STYLE_ROSMEN: "Росмэн / книжный стиль",
}
DEFAULT_STYLE = STYLE_ROSMEN

# Every item from the current 28-command spellbook has a visible,
# deliberately chosen Russian reading. Non-book spells use game readings.
ROSMEN_READINGS = {
    "Accio": "Акцио",
    "Levioso": "Левиосо",
    "Depulso": "Депульсо",
    "Descendo": "Десцендо",
    "Flipendo": "Флипендо",
    "Glacius": "Глациус",
    "ArrestoMomentum": "Арресто Моментум",
    "Incendio": "Инсендио",
    "Confringo": "Вспыхни",
    "Diffindo": "Диффиндо",
    "Bombarda": "Бомбарда",
    "Stupefy": "Остолбеней",
    "Expelliarmus": "Экспеллиармус",
    "Protego": "Протего",
    "Oppugno": "Оппуньо",
    "Lumos": "Люмос",
    "Nox": "Нокс",
    "Reparo": "Репаро",
    "Revelio": "Ревелио",
    "Disillusionment": "Дезиллюминация",
    "Wingardium": "Вингардиум Левиоса",
    "Transformation": "Трансформация",
    "Vanishment": "Эванеско",
    "Crucio": "Круцио",
    "Imperius": "Империо",
    "AvadaKedavra": "Авада Кедавра",
    "Finisher": "Древняя магия",
    "AppareVestigium": "Покажи путь",
}

# These ordinary expressions only work in the book-inspired mode; they are
# not generic synonyms shared by every profile.
BOOK_MODE_LITERAL_OVERRIDES = {
    ("Finisher", "древняя магия"),
    ("Transformation", "трансформация"),
}

# Avoid weak single-word abbreviations in book mode: Wingardium must not
# accidentally trigger on half an incantation, and Levioso != Leviosa.
ROSMEN_EXCLUDED_ALIASES = {
    "Levioso": frozenset({"левиоза"}),
    "Wingardium": frozenset({"вингардиум"}),
}

def validate_style(style: str) -> str:
    if style not in STYLE_LABELS:
        raise ValueError(f"Unknown voice style: {style!r}")
    return style

def visible_name(spell: str, style: str = DEFAULT_STYLE) -> str:
    validate_style(style)
    from .spell_meta import READINGS
    if style == STYLE_ROSMEN:
        return ROSMEN_READINGS.get(spell, READINGS.get(spell, (spell,))[0])
    return READINGS.get(spell, (spell,))[0]

def spoken_aliases(spell: str, base_aliases, style: str = DEFAULT_STYLE) -> set[str]:
    validate_style(style)
    result = set(base_aliases)
    if style == STYLE_ROSMEN:
        result.difference_update(ROSMEN_EXCLUDED_ALIASES.get(spell, ()))
        name = ROSMEN_READINGS.get(spell)
        if name:
            result.add(name.casefold())
    return result

def is_book_mode_literal_exception(spell: str, phrase: str, style: str) -> bool:
    return style == STYLE_ROSMEN and (spell, phrase) in BOOK_MODE_LITERAL_OVERRIDES
