"""Coalesce concurrent identical cloud calls and briefly cache successful retries."""
from __future__ import annotations

import threading
import time
from typing import Callable, TypeVar

T=TypeVar("T")

class RetryCache:
    def __init__(self, ttl_seconds: float = 25, capacity: int = 128):
        self.ttl=float(ttl_seconds)
        self.capacity=max(1,int(capacity))
        self._lock=threading.Lock()
        self._cached: dict[str,tuple[float,object]]={}
        self._inflight: dict[str,threading.Event]={}

    def get_or_run(self, key: str, run: Callable[[],T]) -> T:
        now=time.monotonic()
        with self._lock:
            entry=self._cached.get(key)
            if entry is not None and entry[0]>now:
                return entry[1]
            inflight=self._inflight.get(key)
            owner=inflight is None
            if owner:
                inflight=threading.Event()
                self._inflight[key]=inflight
        if not owner:
            # The owner may attempt more than one free provider. Waiting
            # threads never make a second duplicate outbound request.
            if not inflight.wait(timeout=50):
                raise TimeoutError("Timed out waiting for existing cloud request")
            with self._lock:
                entry=self._cached.get(key)
                if entry is not None and entry[0]>time.monotonic():
                    return entry[1]
            raise LookupError("Concurrent cloud attempt returned no cached response")
        try:
            result=run()
            with self._lock:
                self._cached[key]=(time.monotonic()+self.ttl,result)
                if len(self._cached)>self.capacity:
                    # In-memory only: process restarts always clear this cache.
                    expired=[k for k,(until,_) in self._cached.items() if until<time.monotonic()]
                    for k in expired:
                        self._cached.pop(k,None)
                    while len(self._cached)>self.capacity:
                        self._cached.pop(next(iter(self._cached)))
            return result
        finally:
            with self._lock:
                self._inflight.pop(key,None)
                inflight.set()
