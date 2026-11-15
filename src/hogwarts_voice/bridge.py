"""Windows SpellCaster UE4SS shared-memory IPC.

Protocol: https://github.com/pierre-cheneau/HogwartsLegacy-SpellCaster/blob/main/docs/ipc-protocol.md
"""
from __future__ import annotations
import mmap
import os
import struct
import time

SHM_NAME = "SpellCasterSharedMemory"
RING = 256
SIZE = 64 + RING * 32 + 4096
WRITE, READ, PRODUCER_HB, CONSUMER_HB, DROPPED, TOTAL = 0, 4, 8, 12, 16, 20

class SpellBridge:
    def __init__(self, memory=None):
        self.memory = memory
        self.last_heartbeat = None
        self.last_change = None

    def connect(self):
        if self.memory is None:
            if os.name != "nt":
                raise OSError("Shared-memory game bridge runs only on Windows")
            self.memory = mmap.mmap(-1, SIZE, tagname=SHM_NAME, access=mmap.ACCESS_WRITE)
        self.poll()
        return self

    def close(self):
        if self.memory is not None:
            self.memory.close()
            self.memory = None

    def _u32(self, offset):
        return struct.unpack("<I", self.memory[offset:offset + 4])[0]

    def _put32(self, offset, n):
        self.memory[offset:offset + 4] = struct.pack("<I", n & 0xFFFFFFFF)

    def poll(self, *, now=None):
        if now is None:
            now = time.monotonic()
        hb = self._u32(CONSUMER_HB)
        if hb != self.last_heartbeat:
            if hb != 0:
                self.last_change = now
            self.last_heartbeat = hb
        return self.alive(now=now)

    def alive(self, *, now=None):
        if now is None:
            now = time.monotonic()
        return self.last_change is not None and now - self.last_change <= 2.0

    def heartbeat(self):
        self._put32(PRODUCER_HB, self._u32(PRODUCER_HB) + 1)

    def send(self, spell, *, now=None):
        if self.memory is None:
            return False, "not connected"
        if now is None:
            now = time.monotonic()
        if not self.alive(now=now):
            return False, "game mod not responding (consumer heartbeat)"
        try:
            name = spell.encode("ascii")
        except UnicodeEncodeError:
            return False, "spell's game name must be ASCII"
        if not name or len(name) > 27 or b"\x00" in name:
            return False, "spell name length must be 1..27"

        write = self._u32(WRITE)
        read = self._u32(READ)
        next_write = (write + 1) & 0xFFFFFFFF
        if (next_write & 255) == (read & 255):
            self._put32(DROPPED, self._u32(DROPPED) + 1)
            return False, "command queue full"
        offset = 64 + (write & 255) * 32
        self.memory[offset:offset + 32] = name.ljust(28, b"\x00") + struct.pack("<I", 0)
        self._put32(WRITE, next_write)
        self._put32(TOTAL, self._u32(TOTAL) + 1)
        self.heartbeat()
        return True, "sent"

    def status(self):
        return {"alive": self.alive(), "write": self._u32(WRITE),
                "read": self._u32(READ), "dropped": self._u32(DROPPED),
                "total": self._u32(TOTAL), "consumer_hb": self._u32(CONSUMER_HB)}

