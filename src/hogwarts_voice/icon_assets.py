"""User-supplied original Hogwarts Legacy icon pack import.

Official game artworks belong to their copyright owners. We do NOT bundle
or redistribute them. The user imports a local ZIP for personal use.
"""
from __future__ import annotations

from pathlib import Path
import io
import os
import zipfile

from PIL import Image, ImageOps

SOURCE_PAGE = "https://www.spriters-resource.com/pc_computer/hogwartslegacy/asset/494960/"
# Basenames of actual spell icons in the published game asset collection.
SOURCE_FILES = {
    "Accio": "UI_T_accio.png",
    "Levioso": "UI_T_levioso.png",
    "Depulso": "UI_T_depulso.png",
    "Descendo": "UI_T_Descendo.png",
    "Flipendo": "UI_T_flipendo.png",
    "Glacius": "UI_T_glacius.png",
    "ArrestoMomentum": "UI_T_arrestomomentum.png",
    "Incendio": "UI_T_incendio.png",
    "Confringo": "UI_T_confringo.png",
    "Diffindo": "UI_T_diffindo.png",
    "Bombarda": "UI_T_spellmeter_Bombarda_Overlay.png",
    "Stupefy": "UI_T_stupefy.png",
    "Expelliarmus": "UI_T_expelliarmus.png",
    "Protego": "UI_T_protego.png",
    "Oppugno": "UI_T_Oppugno.png",
    "Lumos": "UI_T_lumos.png",
    "Reparo": "UI_T_reparo.png",
    "Revelio": "UI_T_revelio.png",
    "Disillusionment": "UI_T_disillusionment.png",
    "Wingardium": "UI_T_wingardium.png",
    "Transformation": "UI_T_transformation.png",
    "Vanishment": "UI_T_Vanishment.png",
    "Crucio": "UI_T_spell_Crucio.png",
    "Imperius": "UI_T_imperius.png",
    "AvadaKedavra": "UI_T_avadakedavra.png",
    "Finisher": "UI_T_FinisherBlackParticleExplode.png",
}
# Nox and AppareVestigium do not have separate game spell icons in this pack.

def icon_dir() -> Path:
    root = Path(os.getenv("LOCALAPPDATA") or (Path.home() / ".local" / "share"))
    return root / "HogwartsVoiceCasterRU" / "spell_icons"

def icon_file(spell: str) -> Path:
    return icon_dir() / f"{spell}.png"

def has_icon(spell: str) -> bool:
    return icon_file(spell).is_file()

def count_icons() -> int:
    return sum(has_icon(spell) for spell in SOURCE_FILES)

def import_zip(path: Path, dest: Path | None = None) -> list[str]:
    """Extract matching images only; do not extract arbitrary ZIP contents.

    Limits avoid decompression bombs and path traversal; all outputs get
    generated filenames. Images stay on the user's PC (not committed to Git).
    """
    target_dir = dest or icon_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    imported = []
    with zipfile.ZipFile(path) as archive:
        by_name = {}
        for info in archive.infolist():
            if info.is_dir():
                continue
            if info.file_size > 8 * 1024 * 1024:
                continue
            by_name.setdefault(Path(info.filename).name.lower(), info)
        for spell, wanted in SOURCE_FILES.items():
            member = by_name.get(wanted.lower())
            if member is None:
                continue
            try:
                raw = archive.read(member)
                with Image.open(io.BytesIO(raw)) as opened:
                    if opened.width > 4096 or opened.height > 4096:
                        continue
                    img = opened.convert("RGBA")
                bound = img.getchannel("A").getbbox()
                if bound:
                    img = img.crop(bound)
                img = ImageOps.contain(img, (432, 432), method=Image.Resampling.LANCZOS)
                output = Image.new("RGBA", (480, 480), (0, 0, 0, 0))
                output.alpha_composite(img, ((480 - img.width) // 2, (480 - img.height) // 2))
                tmp = target_dir / (spell + ".tmp")
                # Explicit PNG format because temp filename lacks a PNG extension.
                output.save(tmp, format="PNG")
                os.replace(tmp, target_dir / (spell + ".png"))
                imported.append(spell)
            except (OSError, ValueError, SyntaxError):
                continue
    return imported
