"""Deterministic and idempotent story proposal rules.

No AI-controlled arbitrary actions: all events are proposed for review by a
future trusted Sonorus/UE4SS integration. Each milestone happens once per
player save and NPC, independent of process restarts.
"""
from __future__ import annotations

from typing import Iterator

def story_proposals(npc: str, event: str, affinity: int, trust: int,
                    prior_conflict: bool) -> Iterator[tuple[str,str,dict]]:
    base={"requires_game_adapter":True,"game_action_performed":False}
    if npc=="sebastian":
        if event=="meeting_attended" and trust>=0:
            yield ("undercroft_discussion","scene_proposal",{
                **base,"scene_id":"sebastian_undercroft_discussion",
                "subject":"Себастьян хочет обсудить трудный выбор в Подземелье",
                "site":"Undercroft"})
        elif event=="secret_kept" and trust>=10:
            yield ("trusted_confidant","social_reaction_proposal",{
                **base,"reaction_id":"sebastian_confidant",
                "subject":"Себастьян благодарен за сохранённый секрет"})
        elif event=="secret_revealed_to_ominis":
            yield ("disclosure_confrontation","social_reaction_proposal",{
                **base,"reaction_id":"sebastian_disclosure",
                "subject":"Себастьян хочет обсудить раскрытие своего секрета"})
    if npc=="ominis":
        if event=="meeting_attended":
            yield ("ominis_serious_conversation","scene_proposal",{
                **base,"scene_id":"ominis_friendship_discussion",
                "subject":"Оминис хочет обсудить доверие и опасные решения",
                "site":"Hogwarts courtyard"})
    if npc=="poppy":
        if event=="meeting_attended" and trust>=0:
            yield ("poppy_creatures_discussion","scene_proposal",{
                **base,"scene_id":"poppy_creatures_discussion",
                "subject":"Поппи предлагает разговор о защите волшебных существ",
                "site":"Beasts classroom"})
    if event=="meeting_missed":
        yield ("first_missed_meeting","owl_letter_proposal",{
            **base,"letter_id":"missed_meeting_followup",
            "subject":"Напоминание о пропущенной встрече"})
    if event=="apology_accepted" and prior_conflict:
        yield ("first_reconciliation","social_reaction_proposal",{
            **base,"reaction_id":"first_reconciliation",
            "subject":"Персонаж готов восстановить доверие после конфликта"})
