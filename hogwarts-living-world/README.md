# Hogwarts Living World v0.1.0 — cloud-free-only prototype

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
