"""Deterministic NPC relationship state; generated AI text is never game authority."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from threading import RLock

EVENTS = {
    "player_helped": (12, 8),
    "player_refused": (-9, -4),
    "player_ignored": (-5, -3),
    "apology_accepted": (7, 12),
    "gift_given": (5, 3),
    "meeting_accepted": (4, 2),
    "meeting_declined": (-3, -1),
    "meeting_attended": (12, 8),
    "meeting_missed": (-10, -8),
    "probe_ping": (0, 0),
}

def safe_id(value: str) -> str:
    if not isinstance(value, str) or not (1 <= len(value) <= 64) or not all(
            c.isascii() and (c.isalnum() or c in "_-.") for c in value):
        raise ValueError("ID must be 1-64 ASCII letters, numbers, _, -, or .")
    return value

class World:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.lock = RLock()
        with self.lock:
            self.db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS relations (
                    player TEXT NOT NULL, npc TEXT NOT NULL,
                    affinity INTEGER NOT NULL DEFAULT 0, trust INTEGER NOT NULL DEFAULT 0,
                    updated INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(player,npc));
                CREATE TABLE IF NOT EXISTS events (
                    player TEXT NOT NULL, event_id TEXT NOT NULL,
                    npc TEXT NOT NULL, kind TEXT NOT NULL,
                    PRIMARY KEY(player,event_id));
                CREATE TABLE IF NOT EXISTS probe_status (
                    source TEXT PRIMARY KEY, last_seen INTEGER NOT NULL,
                    event_id TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS milestones (
                    player TEXT NOT NULL, npc TEXT NOT NULL, milestone TEXT NOT NULL,
                    PRIMARY KEY(player,npc,milestone));
                CREATE TABLE IF NOT EXISTS source_offsets (
                    source TEXT NOT NULL PRIMARY KEY, byte_offset INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    player TEXT NOT NULL, npc TEXT NOT NULL, kind TEXT NOT NULL,
                    payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                    created INTEGER NOT NULL);
            """)

    def snapshot(self, player: str, npc: str) -> dict:
        safe_id(player)
        safe_id(npc)
        with self.lock:
            row = self.db.execute(
                "SELECT affinity, trust, updated FROM relations WHERE player=? AND npc=?",
                (player,npc)).fetchone()
        return {"player_id":player, "npc_id":npc, "affinity":row["affinity"] if row else 0,
                "trust":row["trust"] if row else 0,"updated":row["updated"] if row else None}

    def apply(self, player: str, npc: str, kind: str, event_id: str) -> dict:
        safe_id(player)
        safe_id(npc)
        safe_id(event_id)
        if kind not in EVENTS:
            raise ValueError("Unknown event type; allowed: " + ", ".join(EVENTS))
        da, dt = EVENTS[kind]
        now = int(time.time())
        if kind == "probe_ping":
            with self.lock:
                cursor = self.db.execute(
                    "INSERT OR IGNORE INTO events(player,event_id,npc,kind) VALUES(?,?,?,?)",
                    (player,event_id,npc,kind))
                if cursor.rowcount:
                    self.db.execute(
                        "INSERT INTO probe_status(source,last_seen,event_id) VALUES(?,?,?) "
                        "ON CONFLICT(source) DO UPDATE SET last_seen=excluded.last_seen,event_id=excluded.event_id",
                        (player,now,event_id))
            return {"duplicate":not bool(cursor.rowcount), "probe":True, "received_at":now}

        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                old = self.db.execute("SELECT npc,kind FROM events WHERE player=? AND event_id=?", (player,event_id)).fetchone()
                if old:
                    if old["npc"] != npc or old["kind"] != kind:
                        raise ValueError("Event ID reused with different content")
                    self.db.execute("COMMIT")
                    return {"duplicate":True, **self.snapshot(player,npc)}
                current = self.snapshot(player,npc)
                affinity = max(-100,min(100,current["affinity"]+da))
                trust = max(-100,min(100,current["trust"]+dt))
                self.db.execute("INSERT INTO events(player,event_id,npc,kind) VALUES(?,?,?,?)",(player,event_id,npc,kind))
                self.db.execute(
                    "INSERT INTO relations(player,npc,affinity,trust,updated) VALUES(?,?,?,?,?) "
                    "ON CONFLICT(player,npc) DO UPDATE SET affinity=excluded.affinity,trust=excluded.trust,updated=excluded.updated",
                    (player,npc,affinity,trust,now))
                # Only proposals. A verified game adapter must consume and confirm these.
                if kind == "player_refused" and trust <= -8:
                    self._enqueue_once(player,npc,"first_conflict","npc_note",
                                       {"reason":"unresolved_refusal","tone":"cold"},now)
                elif kind == "player_helped" and affinity >= 12:
                    self._enqueue_once(player,npc,"first_gratitude","npc_note",
                                       {"reason":"gratitude","tone":"warm"},now)
                if trust <= -25:
                    self._enqueue_once(player,npc,"serious_distrust","relationship_consequence_proposal",
                                       {"behavior":"avoids_player","requires_game_adapter":True},now)
                # Deterministic story milestone, once per save & NPC, never directly a game action.
                if npc in ("sebastian","ominis","poppy") and affinity >= 24 and trust >= 16:
                    inserted = self.db.execute(
                        "INSERT OR IGNORE INTO milestones(player,npc,milestone) VALUES(?,?,?)",
                        (player,npc,"first_invitation"))
                    if inserted.rowcount:
                        self._enqueue(player,npc,"owl_letter_proposal",{
                            "story":"first_invitation",
                            "summary":"The NPC would like to meet the player.",
                            "requires_game_adapter":True},now)
                if kind == "meeting_accepted":
                    location = {"sebastian":"Undercroft","ominis":"Hogwarts courtyard",
                                "poppy":"Beasts classroom"}.get(npc)
                    if location:
                        self._enqueue(player,npc,"meeting_proposal",{
                            "location":location,"requires_game_adapter":True},now)
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
        return {"duplicate":False,"player_id":player,"npc_id":npc,"affinity":affinity,
                "trust":trust,"updated":now}

    def _enqueue_once(self, player: str, npc: str, milestone: str,
                      kind: str, payload: dict, now: int):
        inserted=self.db.execute(
            "INSERT OR IGNORE INTO milestones(player,npc,milestone) VALUES(?,?,?)",
            (player,npc,milestone))
        if inserted.rowcount:
            self._enqueue(player,npc,kind,payload,now)

    def _enqueue(self, player: str, npc: str, kind: str, payload: dict, now: int):
        self.db.execute("INSERT INTO outbox(player,npc,kind,payload,created) VALUES(?,?,?,?,?)",
                        (player,npc,kind,json.dumps(payload),now))

    def pending(self, player: str, limit: int = 20) -> list[dict]:
        safe_id(player)
        with self.lock:
            rows = self.db.execute(
                "SELECT id,npc,kind,payload,created FROM outbox WHERE player=? AND status='pending' ORDER BY id LIMIT ?",
                (player,max(1,min(int(limit),100)))).fetchall()
        return [{"id":r["id"],"npc_id":r["npc"],"kind":r["kind"],
                 "payload":json.loads(r["payload"]),"created":r["created"]} for r in rows]

    def acknowledge(self, player: str, ids: list[int]) -> int:
        safe_id(player)
        if not isinstance(ids,list) or len(ids)>100 or any(type(x) is not int or x <= 0 for x in ids):
            raise ValueError("ids must be a list of positive integers (max 100)")
        with self.lock:
            cursor = self.db.executemany(
                "UPDATE outbox SET status='acknowledged' WHERE player=? AND id=? AND status='pending'",
                [(player,i) for i in ids])
            return cursor.rowcount


    def source_offset(self, source: str) -> int:
        with self.lock:
            row=self.db.execute("SELECT byte_offset FROM source_offsets WHERE source=?",(source,)).fetchone()
        return int(row["byte_offset"]) if row else 0

    def store_source_offset(self, source: str, offset: int):
        if offset < 0:
            raise ValueError("negative offset")
        with self.lock:
            self.db.execute("INSERT INTO source_offsets(source,byte_offset) VALUES(?,?) "
                            "ON CONFLICT(source) DO UPDATE SET byte_offset=excluded.byte_offset",
                            (source,offset))

    def last_probe(self) -> dict:
        """Local debug status only; not proof of an actual UE4SS game hook."""
        with self.lock:
            row = self.db.execute(
                "SELECT source,last_seen FROM probe_status ORDER BY last_seen DESC LIMIT 1"
            ).fetchone()
        return {"source":row["source"],"received_at":row["last_seen"]} if row else {"source":None,"received_at":None}

    def integrity_check(self) -> str:
        with self.lock:
            return self.db.execute("PRAGMA integrity_check").fetchone()[0]

    def backup(self, directory: Path, keep: int = 5) -> Path:
        """Online backup avoids corrupt copies when WAL is active."""
        from datetime import datetime, timezone
        directory.mkdir(parents=True, exist_ok=True)
        stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        dest=directory / ("world-"+stamp+".sqlite3")
        with self.lock:
            target=sqlite3.connect(dest)
            try:
                self.db.backup(target)
                if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise OSError("Backup integrity check failed")
            except BaseException:
                target.close()
                dest.unlink(missing_ok=True)
                raise
            finally:
                target.close()
        old=sorted(directory.glob("world-*.sqlite3"),reverse=True)
        for path in old[max(1,keep):]:
            path.unlink(missing_ok=True)
        return dest
