"""Privacy-safe bridge request diagnostics.

Only status/size/error-class metadata is saved. Never store prompt text,
NPC names, HTTP headers, API keys, request bodies, response text or URLs.
"""
from __future__ import annotations

import json
import re
import time
from collections import deque
from pathlib import Path
from threading import Lock

SAFE_TOKEN = re.compile(r"^[a-zA-Z0-9_.-]{1,48}$")

def safe_label(value, fallback="unknown"):
    text=str(value)
    return text if SAFE_TOKEN.fullmatch(text) else fallback

class RequestHistory:
    def __init__(self,path:Path,max_events:int=60):
        self.path=path
        self.lock=Lock()
        self.events=deque(maxlen=max_events)
        path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists():
            try:
                with path.open("r",encoding="utf-8") as handle:
                    for line in handle:
                        if len(line)>700: continue
                        item=json.loads(line)
                        if isinstance(item,dict) and "status" in item:
                            self.events.append(item)
            except (OSError,ValueError,UnicodeError):
                pass

    def record(self, *, status:int, phase:str="bridge", provider:str="none",
               code:str="ok", duration_ms:int=0, chars:int=0,
               messages:int=0, streaming:bool=False):
        entry={"at":int(time.time()),
               "status":int(status),
               "phase":safe_label(phase),
               "provider":safe_label(provider),
               "code":safe_label(code),
               "duration_ms":max(0,int(duration_ms)),
               "prompt_chars":max(0,int(chars)),
               "message_count":max(0,int(messages)),
               "streaming":bool(streaming)}
        with self.lock:
            self.events.append(entry)
            try:
                # Keep on-disk history small and overwrite the oldest entries.
                tmp=self.path.with_suffix(".tmp")
                tmp.write_text("".join(json.dumps(e,separators=(",",":"))+"\n" for e in self.events),
                               encoding="utf-8")
                tmp.replace(self.path)
            except OSError:
                pass
        return entry

    def recent(self):
        with self.lock:
            return list(reversed(self.events))
