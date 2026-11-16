# Hogwarts Living World — draft game adapter protocol v0.4

**No verified Sonorus or UE4SS gameplay adapter exists yet.** The optional
HLWProbe sends a harmless handshake only. This contract describes the next
integration layer, without pretending that its actions already work.

## Game → HLW: observed facts only

A future game adapter can append one JSON record per line (UTF-8) to:

    %LOCALAPPDATA%\HogwartsLivingWorld\game-events.jsonl

Record:

    {"player_id":"slot_1","npc_id":"sebastian","event":"player_helped","event_id":"unique_quest_42"}

Four required fields. IDs allow ASCII letters, digits, dot, dash and
underscore, maximum 64 characters. Event names must be allowlisted in
hlw/world.py. Events must be based on actual observed player action, NEVER
on AI-generated text.

The producer must use a stable event_id for an action, and write a trailing
newline. Replayed events are ignored. No game saves are modified by HLW.

## HLW → Game: proposals, not commands

A verified adapter may poll:

    GET /v1/world/outbox?player_id=slot_1

Result shape:

    {"events":[{"id":123,"npc_id":"poppy","kind":"scene_proposal",
                "payload":{"scene_id":"poppy_creatures_discussion",
                           "requires_game_adapter":true,
                           "game_action_performed":false},
                "created":1800000000}]}

A proposal DOES NOT mean an owl has been delivered, an actor has moved,
a quest has started or a scene has played. The future adapter must verify
game state, cutscenes, NPC presence, quest compatibility, save changes and
ownership by other mods.

Only after confirmed success should an adapter acknowledge a proposal:

    POST /v1/world/outbox/ack
    {"player_id":"slot_1","ids":[123]}

The existing acknowledgement endpoint is for manual experiments, not a
finished authenticated delivery protocol. Do not automate game mutations
until adapter authentication and retry semantics are implemented.

Never execute arbitrary code, Python, Lua, console commands or LLM tools
on the strength of a model response. Map events exclusively to tested,
allowlisted game actions.

## Local endpoints

GET /health, /v1/diagnostics, /v1/models,
GET /v1/world/npc, /v1/world/story, /v1/world/outbox,
POST /v1/world/event, /v1/world/backup, /v1/world/outbox/ack,
POST /v1/chat/completions and optional POST /v1/audio/speech.

The bridge must remain bound to 127.0.0.1; do not expose it on any public
interface or tunnel. Sonorus and UE4SS are independent third-party projects,
not official partners of Hogwarts Living World.
