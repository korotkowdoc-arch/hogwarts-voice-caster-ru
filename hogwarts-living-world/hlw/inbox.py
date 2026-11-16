"""Append-only game event inbox for a future UE4SS/Sonorus game adapter.

Never reads/writes Hogwarts Legacy files. Watches a user-controlled JSONL
file in the bridge data directory. All events are validated by World.apply.
"""
from __future__ import annotations

import json
from pathlib import Path
from threading import Event, Thread
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .world import World

class GameEventInbox:
    def __init__(self,path:Path,world:"World"):
        self.path=path
        self.world=world
        self.stop_event=Event()
        self.worker=None

    def poll_once(self, limit=100) -> dict:
        """Consume up to limit complete JSONL rows; return sanitized counters."""
        counters={"applied":0,"duplicate":0,"rejected":0}
        if not self.path.is_file():
            return counters
        source=str(self.path.resolve())
        offset=self.world.source_offset(source)
        if self.path.stat().st_size < offset:
            # Log rotation/truncate: previous event IDs still prevent duplication.
            offset=0
            self.world.store_source_offset(source,0)
        with self.path.open("rb") as handle:
            handle.seek(offset)
            for _ in range(min(100,max(1,int(limit)))):
                start=handle.tell()
                line=handle.readline(16385)
                if not line:
                    break
                if len(line)>16384 and not line.endswith(b"\n"):
                    # Consume one oversized *complete* record without loading
                    # unbounded untrusted data into memory. Incomplete records
                    # are retried when the producer finishes writing them.
                    completed=False
                    for _chunk in range(128):
                        rest=handle.readline(16385)
                        if not rest:
                            break
                        if rest.endswith(b"\n"):
                            completed=True
                            break
                    if not completed:
                        handle.seek(start)
                        break
                    counters["rejected"]+=1
                    offset=handle.tell()
                    self.world.store_source_offset(source,offset)
                    continue
                if not line.endswith(b"\n"):
                    break  # Incomplete line: wait for the producer to finish.
                end=handle.tell()
                try:
                    if len(line)>16384:
                        raise ValueError("event line too large")
                    body=json.loads(line.decode("utf-8"))
                    if not isinstance(body,dict) or set(body)!={"player_id","npc_id","event","event_id"}:
                        raise ValueError("event fields invalid")
                    result=self.world.apply(body["player_id"],body["npc_id"],body["event"],body["event_id"])
                    counters["duplicate" if result["duplicate"] else "applied"]+=1
                except (ValueError,TypeError,UnicodeDecodeError,KeyError):
                    counters["rejected"]+=1
                # Commit the cursor after World.apply. After an interrupted run
                # event_id idempotency makes retry safe.
                self.world.store_source_offset(source,end)
                offset=end
        return counters

    def start(self):
        if self.worker is not None:
            return
        self.worker=Thread(target=self._run,daemon=True,name="hlw-event-inbox")
        self.worker.start()

    def _run(self):
        while not self.stop_event.wait(0.8):
            try:
                self.poll_once()
            except OSError:
                pass  # A temporary filesystem problem is retried later.

    def stop(self):
        self.stop_event.set()
        if self.worker:
            self.worker.join(timeout=3)
            self.worker=None
