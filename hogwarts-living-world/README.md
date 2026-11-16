# Hogwarts Living World v0.4.1 — cloud-free-only prototype

**This is a standalone technical prototype, not yet an installed Hogwarts Legacy mod.**
It does not change the existing Voice Caster or any game files.

It uses **cloud models only** (no local neural network) and stores deterministic
NPC relationships in SQLite. Generated proposals are NOT executed in the game.

## Included

- OpenAI-compatible Chat Completions loopback HTTP endpoint
  http://127.0.0.1:8765/v1/chat/completions with basic SSE output.
- Gemini gemini-3.5-flash-lite with Groq openai/gpt-oss-20b fallback.
- No paid providers, dynamic URLs, automatic payment or model upgrades.
- Persistent conservative LOCAL daily caps: Gemini 120 / Groq 300.
  These are **not** official provider free quotas.
- SQLite per-save/per-NPC affinity and trust, deduplicated events, safe event queue.
- HTTP server binds strictly to 127.0.0.1; secrets stay in your local environment.

## Windows setup

In GitHub go to Actions -> Hogwarts Living World - tests and Windows build ->
latest successful run -> Artifacts. Download the Windows artifact, extract
its ZIP and launch run.bat.

Or with Python 3.11+ installed, run from the hogwarts-living-world directory:

    py -3 -m hlw

Create an account with a FREE tier at https://aistudio.google.com/apikey
and/or https://console.groq.com/keys . In the same CMD session, enter:

    set GEMINI_API_KEY=your_free_tier_key
    set GROQ_API_KEY=your_free_plan_key
    run.bat

One API key is enough. Do NOT commit keys to GitHub or share screenshots of them.

Check http://127.0.0.1:8765/health to see the configured providers.
Without free provider access, requests return HTTP 503 with no paid fallback.

**Financial safety warning:** Keys from billing-enabled/paid cloud projects can
generate charges. There is no way to enforce Google's Free tier with a request
flag. If zero cost is mandatory, use only projects WITHOUT billing or accounts
on a confirmed no-billing free plan. The program never activates paid services.
Availability, quotas and region policies can change. Free Gemini content can
be used for Google's product improvement.

## Dialogue example (PowerShell)

    $body = @{ model='hogwarts-living-world-free'; messages=@(@{role='user'; content='Привет, Себастьян!'}) } | ConvertTo-Json -Depth 6
    Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8765/v1/chat/completions' -ContentType 'application/json' -Body ([Text.Encoding]::UTF8.GetBytes($body))

## World event example (PowerShell)

    $event = @{ player_id='save_1'; npc_id='sebastian'; event='player_refused'; event_id='decision_001' } | ConvertTo-Json
    Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8765/v1/world/event' -ContentType 'application/json' -Body $event
    Invoke-RestMethod 'http://127.0.0.1:8765/v1/world/npc?player_id=save_1&npc_id=sebastian'
    Invoke-RestMethod 'http://127.0.0.1:8765/v1/world/outbox?player_id=save_1'

Supported event kinds: player_helped, player_refused, player_ignored,
apology_accepted, gift_given. Any NPC note output is only a PROPOSAL for
a future verified game adapter. The game world does not change yet.
Persistent data: %LOCALAPPDATA%/HogwartsLivingWorld/world.sqlite3.

## Sonorus compatibility — not yet verified in-game

Sonorus supports an OpenAI-compatible backend and a custom base URL.
Potential settings: OpenAI Chat Completions (disable Responses API),
base URL http://127.0.0.1:8765/v1, model hogwarts-living-world-free.
Use a placeholder API key if required by Sonorus.

Optional: set HLW_BRIDGE_TOKEN to a long random value and configure that
same value as the bearer API token in the Sonorus client.
Sonorus agents can send special tool messages not yet supported here;
this requires a real compatibility test on the gaming PC.

Russian speech input and TTS have NOT been implemented here.
No local speech models are installed. Game quests, scene scripting and
NPC animations require separate development and testing.

## Tests

    cd hogwarts-living-world
    python -m unittest discover -s tests -v

GitHub Actions runs tests on Ubuntu and Windows. After tests pass,
it builds a Windows standalone EXE ZIP using PyInstaller and uploads it
as a GitHub Actions artifact. It does NOT publish a GitHub Release.


## 0.2.0 — Sonorus integration test and game event inbox

Read SONORUS_SETUP.md for step-by-step Sonorus 1.0.7 configuration.
The bridge now accepts more OpenAI-compatible text chat message structures
and opt-in system-prompt memory markers; it does not execute AI tool calls.
It also creates character-specific story proposals, with exactly-once
milestones for Sebastian, Ominis and Poppy.

When HLW_WATCH_EVENTS=1 (default in run.bat), an **optional JSONL inbox**
watches %LOCALAPPDATA%/HogwartsLivingWorld/game-events.jsonl.
A future authenticated game adapter can append only allowlisted events:

    {"player_id":"slot_1","npc_id":"sebastian","event":"player_helped","event_id":"quest_1"}

Each complete line is processed once. It never edits any Hogwarts save.
This is NOT a working UE4SS hook yet; the game does NOT write this file.

To test safely without game files:

    powershell -ExecutionPolicy Bypass -File .\demo-story.ps1

Sonorus custom OpenAI URL, JSON and streaming support are **not game-tested**.
Initial support is text/subtitle-only. Cloud speech integration to Sonorus
is a separate milestone.


## Optional cloud voice experiment

Gemini 3.8 Flash TTS can return a Russian WAV from a supported free-tier
account. **Not** connected to Sonorus voice playback and **not** character
voice cloning. Do not enable Gemini project billing if zero cost is required.

In the same CMD session before starting run.bat:

    set HLW_ENABLE_CLOUD_TTS=1
    set GEMINI_API_KEY=your_confirmed_free_tier_key
    run.bat

Then in another PowerShell window in the bridge folder run:

    powershell -ExecutionPolicy Bypass -File .\demo-voice.ps1

This sends one short text (maximum 240 characters) to a fixed Gemini 3.8
TTS model, caches returned WAV locally and plays it. Supports built-in
voices Kore, Puck, Charon and Aoede, without imitating the actors.
The program allows up to 20 *new* cloud TTS requests per local day.
Previously cached sentences don't consume the request cap.
No paid fallback exists. Free-tier account selection is your responsibility.


## 0.3.0 — Reliability and game connection groundwork

**Tomorrow's short setup:** run setup-free.bat once to enter Gemini and/or
Groq keys securely. Keys are encrypted with Windows DPAPI for your local
user profile. Then double-click run.bat: no need to re-enter keys.
Cloud speech is still disabled by default.

- Automatic daily SQLite online backup on bridge restart, keeps 5 snapshots.
- New doctor.bat creates a local diagnostic report without exposing keys.
- Improved oversized event inbox recovery; safe repeated game event handling.
- First deterministic cross-NPC choice:
  secret_revealed_to_ominis changes Sebastian and Ominis relations differently,
  and creates a *proposal* for Ominis to respond. Nothing in the game
  changes until real game hooks are implemented and verified.
- Optional UE4SS-OPTIONAL/HLWProbe contains an isolated Lua keybind probe.
  Installing it is optional and not automatic. With an existing UE4SS
  installation, Ctrl+Alt+F10 should append a non-mutating event to the inbox.
  /health and doctor.bat report the last received probe.
  This is NOT a working in-game quest hook.

***Do not install a second copy of UE4SS.***
The probe is not compatible-verified with the player's Sonorus build yet.
Back up saves and Sonorus data before installation.

Run tests: python -m unittest discover -s tests -v


## 0.4.0 — Release candidate before first in-game test

- Russian context-aware NPC persona cards for Sebastian, Ominis and Poppy
  with the last five confirmed player actions and per-save relationship tiers.
- Small, deterministic story arcs: meetings, refusals, disclosures, missed
  meetings and reconciliation. All effects remain proposals; no game hooks
  or original quests are modified yet.
- 25-second in-memory retry cache and singleflight protection prevent
  duplicate simultaneous calls from consuming multiple free requests.
- Local Host and Origin validation to prevent DNS-rebind/cross-site requests.
- Daily cloud counters now **fail closed if corrupted**, rather than silently
  resetting the request limit; remaining requests visible in the dashboard.
- A guarded optional probe installer/uninstaller for an existing Sonorus
  UE4SS installation. It NEVER installs a second UE4SS.
- A complete offline story dry run: demo-full-story.ps1. No API key needed.
- Draft ADAPTER_PROTOCOL.md records explicit inbound factual event schema,
  outbound proposals, and why a future verified game adapter is still needed.
- CI now runs a self-test of the packaged Windows EXE, not just Python sources,
  and bundles a SHA256 checksum.

See QUICKSTART_RU.md for the shortest user workflow. The cloud and
in-game integrations are *unverified without the player's free API keys
and installed Hogwarts Legacy/Sonorus environment*.
