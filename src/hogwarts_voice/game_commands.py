"""Translate application spell IDs into game SpellCaster IPC commands.

Verified against the SpellCaster UE4SS SpellDatabase and special commands:
https://github.com/pierre-cheneau/HogwartsLegacy-SpellCaster
"""
from __future__ import annotations

IPC_RENAMES = {
    "Disillusionment": "Invisica",
    "Wingardium": "WingardiumLeviosa",
    "Transformation": "TransfiguraVerto",
    "Imperius": "Imperio",
    "Finisher": "Smash",
}

# The SpellCaster game mod accepts these base game command names as well as
# other mod-pack commands, which are not part of our 28-spell voice set.
SUPPORTED_BASE_COMMANDS = frozenset({
    "Accio", "Levioso", "Depulso", "Descendo", "Flipendo",
    "Glacius", "ArrestoMomentum", "Incendio", "Confringo",
    "Diffindo", "Bombarda", "Stupefy", "Expelliarmus", "Protego",
    "Oppugno", "Lumos", "Nox", "Reparo", "Revelio", "Invisica",
    "WingardiumLeviosa", "TransfiguraVerto", "Vanishment",
    "Crucio", "Imperio", "AvadaKedavra", "Smash",
    "AppareVestigium",
})

def to_game_command(spell: str) -> str:
    """Return the exact case-sensitive ASCII command for the game mod.

    Unknown spell IDs fail closed. This prevents the previous problem of
    enqueueing an unsupported name and printing misleading '[sent]'.
    """
    if not isinstance(spell, str):
        raise ValueError("Expected a spell identifier")
    mapped = IPC_RENAMES.get(spell, spell)
    if mapped not in SUPPORTED_BASE_COMMANDS:
        raise ValueError(f"Unsupported SpellCaster game command: {spell!r}")
    return mapped
