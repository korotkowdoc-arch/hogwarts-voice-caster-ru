# Hogwarts Living World 0.2.0 — Sonorus connection guide (beta)

**Status:** HTTP compatibility tested in CI; **NOT** yet tested in Hogwarts Legacy.
It does not automatically patch game files or inject new quests.

## Step 1 — prepare the standalone bridge

Get the latest 0.2.0 Windows artifact from GitHub Actions and unzip it.
Create FREE accounts at the provider consoles if you don't have them.
For absolutely zero extra costs, **do not enable billing** in those accounts.

Open Windows CMD in the bridge directory:

    set GEMINI_API_KEY=your_free_key
    set GROQ_API_KEY=your_free_key
    set HLW_REPLY_LANGUAGE=ru
    run.bat

You can set only one key. Check in your browser:

    http://127.0.0.1:8765/health

You should see "world":"ready" and at least one configured provider.
No API keys are ever stored in the project or GitHub repository.

## Step 2 — install official Sonorus

Official Nexus page:
https://www.nexusmods.com/hogwartslegacy/mods/2409

Use the author's installer as instructed. Before changing mods, back up
Hogwarts Legacy saves and Sonorus user data. Do not install a second UE4SS
copy if your voice spell caster already uses it. Keep a single UE4SS and
check the author's compatibility instructions.

In the Sonorus web configuration page:

- LLM provider: OpenAI (custom endpoint/proxy)
- API URL: http://127.0.0.1:8765/v1
- Model: hogwarts-living-world-free
- API key: placeholder (unless HLW_BRIDGE_TOKEN is set)
- "Use Responses API": OFF
- "Enable Reasoning": OFF
- Vision: OFF (image input not supported by this bridge)
- Long-term memory system: OFF for initial compatibility test (the
  bridge keeps its own separate relationship memory).
- Voice synthesis (TTS): OFF for first test, so dialogue uses subtitles.
  Gemini cloud TTS is not wired into Sonorus voice playback yet.
- Game subtitles: ON.
- Voice chat: leave disabled first; use Sonorus's typed chat input.

Save settings, then choose "Test LLM Configuration". If it fails,
leave the game and check health, then send only the error text/logs
WITHOUT keys.

Note: Not all Sonorus agent features are implemented. The bridge
supports OpenAI-style text chat with SSE, opt-in JSON-object output,
basic tool observation messages, and input validation. It intentionally
does NOT implement the OpenAI Responses API, vision, audio input or
arbitrary action/function execution. Sonorus may require additional
compatibility work.

## Step 3 — optional NPC relationship memory

Sonorus does not send the bridge's private player/npc metadata by
default. The bridge can use an explicit marker embedded in a Sonorus
character bio/reference **system prompt**. For example, in the Sebastian
character reference (if that field is passed as a system message):

    [HLW_CONTEXT player=save_1 npc=sebastian]

For Ominis:

    [HLW_CONTEXT player=save_1 npc=ominis]

For Poppy:

    [HLW_CONTEXT player=save_1 npc=poppy]

This associates the conversation with the correct SQLite relationship.
The marker is ignored if it only occurs in a user chat message. If
Sonorus does not forward reference text as a system message, the marker
will not work until we implement a dedicated adapter. Do NOT assume
automatic context capture until confirmed on your PC.

To inspect saved relationships, open:

    http://127.0.0.1:8765/v1/world/npc?player_id=save_1&npc_id=sebastian

## Step 4 — simulate deterministic story events

Run the demo in PowerShell while the bridge is running:

    powershell -ExecutionPolicy Bypass -File .\demo-story.ps1

This simulates two verified "player helped" events.
It produces a proposal for a Hogwarts owl-letter invitation in the
outbox. **It does NOT send an owl, move an NPC or write a game save**.
The next milestone is a genuine game-side adapter with verified hooks.

## Troubleshooting

- 503 No free provider: add a real free API key or wait for quota reset.
  If an account has billing enabled, the local cap cannot guarantee zero cost.
- 400 Vision not supported: disable Sonorus vision.
- 400 json_schema unsupported: disable strict JSON schema modes or report
  the failing Sonorus request shape with secrets removed.
- 401 unauthorized: HLW_BRIDGE_TOKEN does not match the configured client key.
- Subtitles absent: enable Hogwarts Legacy subtitles.
- Two UE4SS installations: follow Sonorus's single-install compatibility guide.

No external requests were made in CI: all provider calls use mocks.


## Separate cloud Russian voice experiment (not in game)

If you want to test Google Gemini's free cloud speech generation, set
HLW_ENABLE_CLOUD_TTS=1 and GEMINI_API_KEY in CMD before starting the bridge;
then run demo-voice.ps1. The voice is a generic synthetic voice, not
Sebastian's/Ominis's/Poppy's original actor voice. It is NOT wired
to Sonorus TTS, and does not speak inside Hogwarts Legacy yet.
