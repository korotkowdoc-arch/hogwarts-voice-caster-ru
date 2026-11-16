# OPTIONAL UE4SS probe (untested in Hogwarts Legacy)

This is a tiny non-invasive Lua mod that ONLY tests whether the existing
UE4SS installation can talk to the Hogwarts Living World event inbox.

1. **Back up your save and Sonorus data first.**
2. Confirm there is a single UE4SS installation from Sonorus/SpellCaster.
3. Put the folder `HLWProbe` inside the *existing*
   `Phoenix/Binaries/Win64/ue4ss/Mods`. Do not overwrite anything.
4. If your UE4SS version needs manual registration, add `HLWProbe : 1`
   to `ue4ss/Mods/mods.txt`. Newer versions may auto-enable via enabled.txt.
5. Launch the bridge using run.bat with event inbox enabled (default).
6. Launch Hogwarts Legacy; while the game is focused press
   **Ctrl+Alt+F10** once.
7. Visit http://127.0.0.1:8765/health and check `last_probe`.
   A recent value means the inbox received an event. It does not prove
   automatic quest hooks or Sonorus integration.
8. To remove the probe, delete *only* `ue4ss/Mods/HLWProbe` and
   its corresponding line in mods.txt, if you added one.

No NPC, quest, memory, world state or save is modified by this Lua code.
Lua `io.open`, `os.getenv`, and key bindings must be available in the
installed UE4SS build; successful behavior is **not yet game-tested**.
