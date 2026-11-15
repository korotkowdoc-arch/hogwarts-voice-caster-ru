"""Read confirmed UE4SS SpellCaster outcomes from the game's own log.

No modification of the game's DLL or incompatible shared-memory ABI.
IPC queued != game executed: only the mod's explicit success line may yield
a "cast" status. If the log is unavailable, report "unverified", never fake
an acknowledgement.

Reference:
https://github.com/pierre-cheneau/HogwartsLegacy-SpellCaster/
  blob/main/ue4ss-mod/SpellCasterMod/dllmain.cpp
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
import re
import time

ATTEMPT = re.compile(r"\[SpellCaster\].*?Attempting to cast:\s*(\w+)\s*===", re.I)
SUCCESS = re.compile(r"\[SpellCaster\].*?Successfully cast:\s*(\w+)", re.I)
UNKNOWN = re.compile(r"\[SpellCaster\].*?Unknown spell\s+'([^']+)'", re.I)
BUSY = re.compile(r"\[SpellCaster\].*?(\w+)\s+still not available after cancel", re.I)
GENERAL_FAIL = re.compile(
    r"\[SpellCaster\].*?(?:Failed to execute cast|Failed to initialize casting system|SpellToolRecord not found)", re.I,
)
SPECIAL = re.compile(
    r"\[SpellCaster\].*?(Finite - cancelled active spell|Nox - cancelled Lumos|"
    r"Lumos already active - ignoring|Nox - Lumos not active|"
    r"(Apperta\w+) - Opening \w+|"
    r"(AccioBroomstick|AccioMount)\b.*?(?:[Ss]uccess|[Ss]ummon|[Ff]ound))", re.I
)
STATUS_DELAY = 5.0

@dataclass(frozen=True)
class ModEvent:
    state: str
    spell: str
    detail: str
    latency_ms: int = 0

@dataclass
class _Pending:
    command: str
    spoken: str
    since: float

def find_log(game_folder: str | Path | None = None,
             game_executable: str | Path | None = None) -> Path | None:
    """Only look in plausible known UE4SS locations, no recursive scan."""
    roots = []
    if game_folder:
        roots.append(Path(game_folder).expanduser())
    if game_executable:
        roots.append(Path(game_executable).expanduser().parent)
    for base in roots:
        candidates = [
            base / "UE4SS_Logs" / "UE4SS.log",
            base / "Phoenix" / "Binaries" / "Win64" / "UE4SS_Logs" / "UE4SS.log",
            base.parent / "Win64" / "UE4SS_Logs" / "UE4SS.log",
        ]
        for candidate in candidates:
            if candidate.is_file():
                return candidate
    return None

class ModLogMonitor:
    def __init__(self, path: str | Path, *, clock=None):
        self.path = Path(path)
        self.clock = clock or time.monotonic
        self.offset = None
        self.pending: deque[_Pending] = deque()
        self.active_attempt: str | None = None
        self.max_lines_per_poll = 2000

    def begin(self):
        try:
            self.offset = self.path.stat().st_size
        except OSError:
            self.offset = 0

    def record_sent(self, app_spell: str, game_command: str, *, now=None):
        """Track only a successfully QUEUED command."""
        now = self.clock() if now is None else now
        self.pending.append(_Pending(game_command, app_spell, now))
        # Memory-bounded even if game mod stops processing.
        while len(self.pending) > 48:
            self.pending.popleft()

    def _resolve(self, command: str, state: str, detail: str, now) -> ModEvent | None:
        for item in self.pending:
            if item.command.casefold() == command.casefold():
                self.pending.remove(item)
                return ModEvent(state, item.spoken, detail,
                                max(0, int((now - item.since) * 1000)))
        return None

    def _parse(self, line, now):
        result = []
        found = ATTEMPT.search(line)
        if found:
            self.active_attempt = found.group(1)
        success = SUCCESS.search(line)
        if success:
            event = self._resolve(success.group(1), "cast", "confirmed by UE4SS log", now)
            if event:
                result.append(event)
        unknown = UNKNOWN.search(line)
        if unknown:
            event = self._resolve(unknown.group(1), "failed", "unknown command in game mod", now)
            if event:
                result.append(event)
        busy = BUSY.search(line)
        if busy:
            for item in self.pending:
                if item.command.casefold() == busy.group(1).casefold():
                    result.append(ModEvent("busy", item.spoken, "spell tool busy; retrying"))
                    break
        if GENERAL_FAIL.search(line) and self.active_attempt:
            event = self._resolve(self.active_attempt, "failed", "UE4SS failed to cast", now)
            if event:
                result.append(event)
        special = SPECIAL.search(line)
        if special:
            line_lower = line.casefold()
            if "finite -" in line_lower:
                key, state = "Finite", "cast"
            elif "nox -" in line_lower:
                key, state = "Nox", "cast" if "cancelled" in line_lower else "ignored"
            elif "lumos already" in line_lower:
                key, state = "Lumos", "ignored"
            elif special.group(2):
                key, state = special.group(2), "cast"
            elif special.group(3):
                key, state = special.group(3), "cast"
            else:
                key, state = "", "unknown"
            if key:
                event = self._resolve(key, state, "special command handled by mod", now)
                if event:
                    result.append(event)
        return result

    def poll(self, *, now=None) -> list[ModEvent]:
        now = self.clock() if now is None else now
        if self.offset is None:
            self.begin()
        events = []
        try:
            size = self.path.stat().st_size
            if size < self.offset:  # log rotated/truncated
                self.offset = 0
            if size > self.offset:
                with self.path.open("rb") as stream:
                    stream.seek(self.offset)
                    # avoid consuming megabytes of unrelated UE4SS logs per frame
                    blob = stream.read(min(size - self.offset, 1_000_000))
                    self.offset = stream.tell()
                for line in blob.decode("utf-8", "replace").splitlines()[:self.max_lines_per_poll]:
                    events.extend(self._parse(line, now))
        except OSError:
            pass
        # No positive confirmation after a timeout; not proof of failure.
        while self.pending and now - self.pending[0].since >= STATUS_DELAY:
            item = self.pending.popleft()
            events.append(ModEvent(
                "unverified", item.spoken, "No matching game-mod log result",
                int((now - item.since) * 1000)
            ))
        return events
