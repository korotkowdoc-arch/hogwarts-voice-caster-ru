-- Hogwarts Living World UE4SS handshake ONLY.
-- Does not touch quests, actors, game memory or Hogwarts save files.
-- Requires existing UE4SS from Sonorus/SpellCaster. No second UE4SS installation.
local prefix = "[HLWProbe]"
local root = os.getenv("LOCALAPPDATA")
if not root or root == "" then
    print(prefix .. " LOCALAPPDATA is not available. Probe disabled.\n")
    return
end

local inbox = root .. "\\HogwartsLivingWorld\\game-events.jsonl"
local count = 0

local function send_probe()
    count = count + 1
    local unique = string.format("ue4ss_%d_%d", os.time(), count)
    local line = string.format(
        '{"player_id":"ue4ss_probe","npc_id":"bridge_probe","event":"probe_ping","event_id":"%s"}\n',
        unique
    )
    local handle, err = io.open(inbox, "ab")
    if not handle then
        print(prefix .. " Bridge folder unavailable. Start HogwartsLivingWorld first. " .. tostring(err) .. "\n")
        return
    end
    local ok, message = pcall(function()
        assert(handle:write(line))
        assert(handle:flush())
    end)
    handle:close()
    if ok then
        print(prefix .. " Handshake written. Check bridge /health for last_probe.\n")
    else
        print(prefix .. " Failed to write handshake: " .. tostring(message) .. "\n")
    end
end

print(prefix .. " Loaded. Press Ctrl+Alt+F10 in game to send a non-mutating handshake.\n")
RegisterKeyBind(Key.F10, {ModifierKey.CONTROL,ModifierKey.ALT}, send_probe)
