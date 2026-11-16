"""Small, deterministic character continuity for cloud NPC dialogue.

This is NOT a Sonorus game adapter. It derives world context only from locally
confirmed events and never tells a language model to perform game actions.
"""
from __future__ import annotations

from typing import Mapping

PERSONAS: dict[str, dict[str, str]] = {
    "sebastian": {
        "name": "Себастьян Сэллоу",
        "traits": "живой, язвительный, преданный близким; иногда упрямится и рискует",
        "care": "судьба сестры Энн, дружба, опасные знания и последствия собственных решений",
    },
    "ominis": {
        "name": "Оминис Мракс",
        "traits": "сдержанный, наблюдательный, принципиальный; опасается тёмной магии",
        "care": "доверие и безопасность друзей, особенно Себастьяна",
    },
    "poppy": {
        "name": "Поппи Добринг",
        "traits": "добрая и решительная; с воодушевлением говорит о магических существах",
        "care": "защита волшебных существ и доверие к людям",
    },
}

LABELS = {
    "player_helped": "Игрок помог персонажу",
    "player_refused": "Игрок отказался помогать",
    "player_ignored": "Игрок проигнорировал просьбу",
    "apology_accepted": "Извинение принято",
    "gift_given": "Игрок сделал подарок",
    "meeting_accepted": "Игрок согласился на встречу",
    "meeting_declined": "Игрок отказался от встречи",
    "meeting_attended": "Игрок пришёл на встречу",
    "meeting_missed": "Игрок пропустил встречу",
    "secret_kept": "Игрок сохранил секрет Себастьяна",
    "secret_revealed_to_ominis": "Игрок раскрыл Оминису секрет Себастьяна",
}

def relation_tone(affinity: int, trust: int) -> str:
    """Coarse tiers avoid huge prompts and exaggerated emotional shifts."""
    if trust <= -35:
        return "серьёзное недоверие: сдержанность, осторожность, возможная дистанция"
    if affinity <= -25 or trust <= -12:
        return "холодные отношения: настороженность, недовольство, короткие ответы"
    if trust >= 40 and affinity >= 40:
        return "крепкая дружба: тепло, забота, честность; не обещай невозможного"
    if trust >= 16 and affinity >= 16:
        return "растущее доверие: больше открытости и естественного юмора"
    return "нейтральное знакомство: не предполагай близость или совместные приключения"

def compact_context(npc_id: str, snapshot: Mapping, recent_events: list[dict],
                    proposals: list[dict]) -> str:
    """Prompt capped to avoid unnecessary free-tier token usage."""
    persona = PERSONAS.get(npc_id)
    pieces = ["Подтверждённая локальная память NPC, а не новые поручения:"]
    if persona:
        pieces.append("Персонаж: "+persona["name"]+". Характер: "+persona["traits"]+".")
        pieces.append("Интересы: "+persona["care"]+".")
    affinity = int(snapshot["affinity"])
    trust = int(snapshot["trust"])
    pieces.append(f"Отношение {affinity}/100, доверие {trust}/100; тон: {relation_tone(affinity, trust)}.")
    recent = [LABELS[k["kind"]] for k in recent_events[-5:] if k.get("kind") in LABELS]
    if recent:
        pieces.append("Проверенные поступки (от старого к новому): "+"; ".join(recent)+".")
    if proposals:
        # Crucial: a proposal is NOT an action executed inside Hogwarts Legacy.
        kinds = [p["kind"] for p in proposals[:3]]
        pieces.append("Есть НЕИСПОЛНЕННЫЕ предложения сюжетных событий: "+", ".join(kinds)+".")
    pieces.append("Не утверждай, что письма доставлены, встречи назначены в игре, "
                  "задания появились или NPC переместились, пока игровой адаптер "
                  "не подтвердил выполнение. Не меняй сюжетные факты самовольно.")
    return " ".join(pieces)[:1500]
