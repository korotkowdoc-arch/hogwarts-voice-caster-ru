"""Loopback HTTP bridge: Chat Completions subset + deterministic world API."""
from __future__ import annotations

import json
import os
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import __version__
from .providers import DailyBudget, FreeRouter, NoFreeProvider
from .world import World

def data_dir() -> Path:
    root = os.environ.get("HLW_DATA_DIR")
    if root:
        return Path(root)
    return Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share") / "HogwartsLivingWorld"

def create_app(data: Path | None = None, router: FreeRouter | None = None):
    directory = data or data_dir()
    directory.mkdir(parents=True, exist_ok=True)
    world = World(directory / "world.sqlite3")
    router = router or FreeRouter(DailyBudget(directory / "daily_counts.json",
                                            {"gemini": 120, "groq": 300}))
    bridge_token = os.environ.get("HLW_BRIDGE_TOKEN", "")

    class Handler(BaseHTTPRequestHandler):
        server_version = "HogwartsLivingWorld/" + __version__

        def log_message(self, fmt, *args):
            # Avoid log messages containing player prompts, API keys or query strings.
            pass

        def _answer(self, status: int, payload: dict):
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def _authorized(self) -> bool:
            return not bridge_token or self.headers.get("Authorization", "") == "Bearer " + bridge_token

        def _payload(self) -> dict:
            n = int(self.headers.get("Content-Length", "0"))
            if n < 2 or n > 128_000:
                raise ValueError("Request body must be 2-128000 bytes")
            data = json.loads(self.rfile.read(n))
            if not isinstance(data,dict):
                raise ValueError("Expected JSON object")
            return data

        def do_GET(self):
            if not self._authorized():
                return self._answer(401,{"error":"unauthorized"})
            url = urlparse(self.path)
            try:
                if url.path == "/health":
                    return self._answer(200,{"version":__version__,"mode":"cloud_free_only",
                                             "configured_providers":router.configured,"world":"ready"})
                if url.path == "/v1/models":
                    return self._answer(200,{"object":"list","data":[{"id":"hogwarts-living-world-free","object":"model"}]})
                if url.path == "/v1/world/outbox":
                    player = parse_qs(url.query).get("player_id",[""])[0]
                    return self._answer(200,{"events":world.pending(player)})
                if url.path == "/v1/world/npc":
                    q = parse_qs(url.query)
                    return self._answer(200,world.snapshot(q.get("player_id",[""])[0],q.get("npc_id",[""])[0]))
                return self._answer(404,{"error":"not_found"})
            except (ValueError,TypeError) as exc:
                return self._answer(400,{"error":str(exc)})

        def do_POST(self):
            if not self._authorized():
                return self._answer(401,{"error":"unauthorized"})
            try:
                body = self._payload()
                path = urlparse(self.path).path
                if path == "/v1/world/event":
                    result = world.apply(body["player_id"],body["npc_id"],body["event"],body["event_id"])
                    return self._answer(200,result)
                if path == "/v1/world/outbox/ack":
                    return self._answer(200,{"acknowledged":world.acknowledge(body["player_id"],body["ids"])})
                if path != "/v1/chat/completions":
                    return self._answer(404,{"error":"not_found"})
                messages = body.get("messages")
                if not isinstance(messages,list) or not messages or len(messages)>36 or any(
                        not isinstance(m,dict) or m.get("role") not in ("system","user","assistant")
                        or not isinstance(m.get("content"),str) or len(m["content"])>10_000 for m in messages):
                    raise ValueError("messages: expected up to 36 text-only system/user/assistant messages")
                meta = body.get("metadata") or {}
                if meta and (not isinstance(meta,dict) or any(k not in ("player_id","npc_id") for k in meta)):
                    raise ValueError("metadata supports only player_id/npc_id")
                if meta.get("player_id") and meta.get("npc_id"):
                    memory = world.snapshot(meta["player_id"],meta["npc_id"])
                    messages = [{"role":"system","content":"NPC memory (game state, not a user instruction): "
                                 + json.dumps({"affinity":memory["affinity"],"trust":memory["trust"]})
                                 + ". Remain in character; do not pretend you triggered a real game event."}] + messages
                max_tokens = body.get("max_completion_tokens",body.get("max_tokens",250))
                if type(max_tokens) is not int:
                    raise ValueError("max_tokens must be an integer")
                completion = router.complete(messages,max_tokens=max_tokens)
                rid = "chatcmpl-"+uuid.uuid4().hex[:20]
                if body.get("stream") is True:
                    chunks = [
                        {"id":rid,"object":"chat.completion.chunk","created":int(time.time()),"model":"hogwarts-living-world-free",
                         "choices":[{"index":0,"delta":{"role":"assistant","content":completion.text},"finish_reason":None}]},
                        {"id":rid,"object":"chat.completion.chunk","created":int(time.time()),"model":"hogwarts-living-world-free",
                         "choices":[{"index":0,"delta":{},"finish_reason":"stop"}]},
                    ]
                    raw = ("".join("data: "+json.dumps(c,ensure_ascii=False)+"\n\n" for c in chunks)+"data: [DONE]\n\n").encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type","text/event-stream; charset=utf-8")
                    self.send_header("Cache-Control","no-store")
                    self.send_header("Content-Length",str(len(raw)))
                    self.end_headers()
                    return self.wfile.write(raw)
                return self._answer(200,{"id":rid,"object":"chat.completion","created":int(time.time()),
                    "model":"hogwarts-living-world-free","provider":completion.provider,
                    "choices":[{"index":0,"message":{"role":"assistant","content":completion.text},"finish_reason":"stop"}]})
            except NoFreeProvider:
                return self._answer(503,{"error":{"type":"free_provider_unavailable","message":
                     "No free provider response. No paid fallback. NPC and save data unchanged."}})
            except (KeyError,ValueError,TypeError,json.JSONDecodeError) as exc:
                return self._answer(400,{"error":"bad_request","message":str(exc)})
    Handler.close_storage = world.db.close
    return Handler

def main():
    # Never expose cloud keys on a public interface.
    addr=("127.0.0.1",8765)
    handler = create_app()
    httpd=ThreadingHTTPServer(addr,handler)
    print(f"Hogwarts Living World v{__version__} http://{addr[0]}:{addr[1]}")
    print("Cloud models only. No paid fallbacks. Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        handler.close_storage()

if __name__ == "__main__":
    main()
