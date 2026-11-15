"""User-assisted installation of the optional 'Nonverbal Spells' PAK.

The user downloads the third-party PAK from its official Nexus page.
We NEVER download/ship copyrighted assets and NEVER suppress all game audio.
All changes take effect after restarting Hogwarts Legacy.
"""
from __future__ import annotations
import os
from pathlib import Path
import shutil

OFFICIAL_NONVERBAL_PAGE = "https://www.nexusmods.com/hogwartslegacy/mods/855"
OFFICIAL_AUTO_ALOHOMORA_PAGE = "https://www.nexusmods.com/hogwartslegacy/mods/2524"

def pak_directory(game_folder: str | Path) -> Path:
    chosen = Path(game_folder).expanduser().resolve()
    if chosen.name.casefold() == "paks" and chosen.parent.name.casefold() == "content":
        folder = chosen
    else:
        folder = chosen / "Phoenix" / "Content" / "Paks"
    if not folder.is_dir():
        raise FileNotFoundError(
            "Не найдена папка Phoenix/Content/Paks. Выбери папку "
            "Hogwarts Legacy либо непосредственно Content/Paks."
        )
    return folder

def install_nonverbal(source: str | Path, game_folder: str | Path) -> Path:
    """Copy a user-chosen .pak into an existing game's ~mods directory.

    Never overwrite another mod or touch files outside the game's Paks folder.
    The caller records the returned path to permit a reversible disable.
    """
    source = Path(source).expanduser().resolve()
    if not source.is_file() or source.suffix.casefold() != ".pak":
        raise ValueError("Выбери извлечённый файл .pak мода Nonverbal Spells")
    if source.stat().st_size <= 0:
        raise ValueError("Файл .pak пуст")
    mod_dir = pak_directory(game_folder) / "~mods"
    dest = mod_dir / source.name
    if dest.exists() or Path(str(dest) + ".disabled").exists():
        raise FileExistsError(
            f"Файл {source.name} уже существует в игре. "
            "Автоматическое перезаписывание запрещено."
        )
    mod_dir.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    try:
        shutil.copy2(source, tmp)
        os.replace(tmp, dest)
    finally:
        if tmp.exists():
            tmp.unlink()
    return dest.resolve()

def set_nonverbal_enabled(installed_path: str | Path,
                          game_folder: str | Path, enabled: bool) -> Path:
    """Reversibly toggle only the specific file imported by this app.

    Disabling renames it to .pak.disabled; never delete files.
    """
    imported = Path(installed_path).expanduser().resolve()
    pak_dir = pak_directory(game_folder)
    safe_dir = (pak_dir / "~mods").resolve()
    if imported.parent != safe_dir or imported.suffix.casefold() != ".pak":
        raise ValueError("Путь к управляемому моду находится вне ~mods")
    disabled = Path(str(imported) + ".disabled")
    old, new = (disabled, imported) if enabled else (imported, disabled)
    if not old.is_file():
        raise FileNotFoundError(f"Не найден файл мода: {old.name}")
    if new.exists():
        raise FileExistsError(f"Нельзя перезаписать существующий файл: {new.name}")
    old.rename(new)
    return new

def nonverbal_status(installed_path: str | Path, game_folder: str | Path) -> str:
    imported = Path(installed_path).expanduser().resolve()
    safe_dir = (pak_directory(game_folder) / "~mods").resolve()
    if imported.parent != safe_dir or imported.suffix.casefold() != ".pak":
        return "unmanaged"
    if imported.is_file():
        return "enabled"
    if Path(str(imported) + ".disabled").is_file():
        return "disabled"
    return "missing"
