"""Presentation metadata, separate from in-game commands and recognition."""
from __future__ import annotations

READINGS = {
    "Accio": ("Акцио", "AK-ee-oh"), "Levioso": ("Левиосо", "leh-vee-OH-soh"),
    "Depulso": ("Депульсо", "deh-PUL-soh"), "Descendo": ("Десцендо", "deh-SEN-doh"),
    "Flipendo": ("Флипендо", "flih-PEN-doh"), "Glacius": ("Глациус", "GLAY-see-us"),
    "ArrestoMomentum": ("Арресто Моментум", "ah-RES-toh moh-MEN-tum"),
    "Incendio": ("Инсендио", "in-SEN-dee-oh"), "Confringo": ("Конфринго", "kon-FRING-goh"),
    "Diffindo": ("Диффиндо", "dih-FIN-doh"), "Bombarda": ("Бомбарда", "bom-BAR-dah"),
    "Stupefy": ("Ступефай", "STOO-puh-fy"),
    "Expelliarmus": ("Экспеллиармус", "eks-pel-ee-AR-mus"),
    "Protego": ("Протего", "proh-TAY-goh"), "Oppugno": ("Оппуньо", "oh-PUG-noh"),
    "Lumos": ("Люмос", "LOO-mos"), "Nox": ("Нокс", "NOKS"),
    "Reparo": ("Репаро", "reh-PAR-oh"), "Revelio": ("Ревелио", "reh-VEH-lee-oh"),
    "Disillusionment": ("Дезиллюминация", "dis-ill-OO-zhun"),
    "Wingardium": ("Вингардиум Левиоса", "win-GAR-dee-um lev-ee-OH-sah"),
    "Transformation": ("Трансформация", "trans-for-MAY-shun"),
    "Vanishment": ("Эванеско", "ev-ah-NES-koh"),
    "Crucio": ("Круцио", "KROO-see-oh"),
    "Imperius": ("Империо", "im-PEH-ree-oh"),
    "AvadaKedavra": ("Авада Кедавра", "ah-VAH-dah keh-DAH-vrah"),
    "Finisher": ("Древняя магия", "ancient magic"),
    "AppareVestigium": ("Путь к цели", "show objective path"),
    "Alohomora": ("Алохомора", "interact with a nearby lock"),
    "Finite": ("Фините", "cancel an active spell"),
    "Broomstick": ("Акцио метла", "summon broom"),
    "Map": ("Открой карту", "open map"),
    "Inventory": ("Открой инвентарь", "open inventory"),
    "Petrificus": ("Петрификус Тоталус", "stealth takedown"),
    "Conjuration": ("Конжурация", "room of requirement"),
    "Mount": ("Призови гиппогрифа", "summon mount"),
    "Quests": ("Открой задания", "open quests"),
    "Character": ("Открой персонажа", "open character"),
    "Talents": ("Открой таланты", "open talents"),
    "Collections": ("Открой коллекции", "open collections"),
    "Challenges": ("Открой испытания", "open challenges"),
    "Mail": ("Открой письма", "open owl mail"),
    "Settings": ("Открой настройки", "open game settings"),
}

GROUPS = {
    "Force": ["Accio", "Depulso", "Descendo", "Flipendo"],
    "Control": ["Levioso", "Glacius", "ArrestoMomentum", "Transformation"],
    "Damage": ["Incendio", "Confringo", "Diffindo", "Bombarda", "Expelliarmus"],
    "Utility": ["Lumos", "Nox", "Reparo", "Revelio", "Disillusionment", "Wingardium", "AppareVestigium"],
    "Dark Arts": ["Crucio", "Imperius", "AvadaKedavra"],
    "Essential": ["Stupefy", "Protego", "Oppugno", "Finisher"],
    "Transfiguration": ["Vanishment"],
    "Actions": ["Alohomora", "Finite", "Broomstick", "Map", "Inventory",
                "Mount", "Quests", "Character", "Talents", "Collections",
                "Challenges", "Mail", "Settings"],
    "Contextual": ["Petrificus", "Conjuration"],
}
PALETTE = {
    "Force": ("#a887ef", "#2c2147", "СИЛОВОЕ"),
    "Control": ("#d4b96c", "#453920", "КОНТРОЛЬ"),
    "Damage": ("#e98879", "#4a2626", "БОЕВОЕ"),
    "Utility": ("#90c9df", "#1c3d50", "ПОЛЕЗНОЕ"),
    "Dark Arts": ("#9bd0ae", "#1e3c2b", "ТЁМНАЯ МАГИЯ"),
    "Essential": ("#e1cdaa", "#49392c", "ОСНОВНОЕ"),
    "Transfiguration": ("#a6c6a8", "#2a4030", "ТРАНСФИГУРАЦИЯ"),
    "Actions": ("#a2c9b9", "#223a35", "ДЕЙСТВИЯ"),
    "Contextual": ("#c2b0e2", "#322942", "КОНТЕКСТ"),
}

def group_of(spell: str) -> str:
    for group, names in GROUPS.items():
        if spell in names:
            return group
    return "Essential"

def palette_of(spell: str):
    return PALETTE[group_of(spell)]
