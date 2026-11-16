"""Cloud-only LLM router with fixed provider endpoints and model IDs."""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Never allow request or config to inject an arbitrary/potentially paid endpoint.
PROVIDERS = {
    "gemini": {
        "model": "gemini-3.5-flash-lite",
        "env": "GEMINI_API_KEY",
        "url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent",
    },
    "groq": {
        "model": "openai/gpt-oss-20b",
        "env": "GROQ_API_KEY",
        "url": "https://api.groq.com/openai/v1/chat/completions",
    },
}

class ProviderError(RuntimeError):
    def __init__(self, provider: str, code: str):
        self.provider = provider
        self.code = code
        super().__init__(f"{provider}:{code}")

class NoFreeProvider(RuntimeError):
    """No free provider available."""

@dataclass(frozen=True)
class Completion:
    text: str
    provider: str
    model: str

class DailyBudget:
    """Persistent per-machine request cap, not a cloud billing guarantee."""
    def __init__(self, path: Path, limits: dict[str, int]):
        self.path, self.limits, self.lock = path, limits, Lock()
        path.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict | None:
        """Invalid budget files deny calls; never silently reset used requests."""
        today=date.today().isoformat()
        if not self.path.exists():
            return {"date":today,"counts":{}}
        try:
            state=json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(state,dict) or not isinstance(state.get("counts"),dict):
                return None
            old_day=date.fromisoformat(state.get("date",""))
            if old_day>date.today():
                return None
            if old_day<date.today():
                return {"date":today,"counts":{}}
            for name,count in state["counts"].items():
                if not isinstance(name,str) or type(count) is not int or count<0:
                    return None
            return state
        except (OSError,ValueError,TypeError):
            return None

    def status(self) -> dict:
        with self.lock:
            state=self._read()
            if state is None:
                return {"state":"locked_corrupt_counter","remaining":{}}
            return {"state":"ok",
                    "remaining":{p:max(0,limit-state["counts"].get(p,0))
                                 for p,limit in self.limits.items()},
                    "limits":dict(self.limits)}

    def consume(self, provider: str) -> bool:
        if provider not in self.limits:
            return False
        with self.lock:
            state=self._read()
            if state is None:
                return False
            used=state["counts"].get(provider,0)
            if used>=self.limits[provider]:
                return False
            state["counts"][provider]=used+1
            tmp=self.path.with_suffix(".tmp")
            try:
                tmp.write_text(json.dumps(state,ensure_ascii=False),encoding="utf-8")
                os.replace(tmp,self.path)
            except OSError:
                return False  # Do not spend an unaccounted cloud request.
            return True

class FreeRouter:
    def __init__(self, budget: DailyBudget, transport=None, keys: dict[str, str] | None = None):
        self.budget = budget
        self.transport = transport or urlopen
        self.keys = keys if keys is not None else os.environ
        self.cooldown_until: dict[str, float] = {}

    @property
    def configured(self) -> list[str]:
        return [p for p in PROVIDERS if self.keys.get(PROVIDERS[p]["env"])]

    def complete(self, messages: list[dict], *, max_tokens: int = 250, output_format: str = "text") -> Completion:
        max_tokens = min(1600, max(1, int(max_tokens)))
        if output_format not in ("text","json_object"):
            raise ValueError("Unsupported output_format")
        if output_format == "json_object":
            messages = [{"role":"system","content":"Return exactly one valid JSON object, no code fences or commentary."}] + messages
        for provider, details in PROVIDERS.items():
            key = self.keys.get(details["env"])
            if not key or self.cooldown_until.get(provider, 0) > time.monotonic():
                continue
            if not self.budget.consume(provider):
                continue
            try:
                text = self._gemini(messages, key, max_tokens, output_format) if provider == "gemini" else self._groq(messages, key, max_tokens, output_format)
                if text.strip():
                    if output_format == "json_object":
                        try:
                            if not isinstance(json.loads(text), dict):
                                continue
                        except ValueError:
                            continue
                    return Completion(text.strip(), provider, details["model"])
            except ProviderError as exc:
                self.cooldown_until[provider] = time.monotonic() + (300 if exc.code == "429" else 45)
        raise NoFreeProvider("No free response available; game state stays intact.")

    def _send(self, provider: str, key: str, body: dict) -> dict:
        details = PROVIDERS[provider]
        headers = {"Content-Type": "application/json", "User-Agent": "HogwartsLivingWorld/0.1"}
        if provider == "gemini":
            headers["x-goog-api-key"] = key
        else:
            headers["Authorization"] = "Bearer " + key
        request = Request(details["url"], data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        try:
            with self.transport(request, timeout=18) as response:
                return json.loads(response.read(2_000_000).decode("utf-8"))
        except HTTPError as exc:
            raise ProviderError(provider, str(exc.code)) from None
        except (TimeoutError, URLError, ValueError, OSError) as exc:
            raise ProviderError(provider, "network_or_payload_error") from exc

    def _gemini(self, messages: list[dict], key: str, max_tokens: int, output_format: str = "text") -> str:
        system = "\n".join(str(m.get("content", "")) for m in messages if m.get("role") == "system")
        contents = []
        for msg in messages:
            if msg.get("role") not in ("user", "assistant"):
                continue
            content = msg.get("content", "")
            if isinstance(content, str):
                contents.append({"role": "model" if msg["role"] == "assistant" else "user", "parts": [{"text": content}]})
        if not contents:
            contents = [{"role": "user", "parts": [{"text": "Привет."}]}]
        payload = {"contents": contents, "generationConfig": {"maxOutputTokens": max_tokens}}
        if output_format == "json_object":
            payload["generationConfig"]["responseMimeType"] = "application/json"
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        data = self._send("gemini", key, payload)
        try:
            parts=data["candidates"][0]["content"]["parts"]
            return "".join(part["text"] for part in parts
                           if isinstance(part,dict) and isinstance(part.get("text"),str))
        except (KeyError, TypeError, IndexError, ValueError) as exc:
            raise ProviderError("gemini", "empty_answer") from exc

    def _groq(self, messages: list[dict], key: str, max_tokens: int, output_format: str = "text") -> str:
        payload = {"model": PROVIDERS["groq"]["model"], "messages": messages,
                   "max_completion_tokens": max_tokens, "temperature": 0.7, "stream": False}
        if output_format == "json_object":
            payload["response_format"] = {"type":"json_object"}
        data = self._send("groq", key, payload)
        try:
            content=data["choices"][0]["message"]["content"]
            if not isinstance(content,str):
                raise TypeError("Expected text completion")
            return content
        except (KeyError, TypeError, IndexError) as exc:
            raise ProviderError("groq", "empty_answer") from exc
