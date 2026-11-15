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

    def consume(self, provider: str) -> bool:
        with self.lock:
            today = date.today().isoformat()
            try:
                state = json.loads(self.path.read_text(encoding="utf-8"))
                if state.get("date") != today:
                    state = {"date": today, "counts": {}}
            except (OSError, ValueError, TypeError):
                state = {"date": today, "counts": {}}
            counts = state["counts"]
            used = int(counts.get(provider, 0))
            if used >= self.limits[provider]:
                return False
            counts[provider] = used + 1
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.path)
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

    def complete(self, messages: list[dict], *, max_tokens: int = 250) -> Completion:
        max_tokens = min(600, max(1, int(max_tokens)))
        for provider, details in PROVIDERS.items():
            key = self.keys.get(details["env"])
            if not key or self.cooldown_until.get(provider, 0) > time.monotonic():
                continue
            if not self.budget.consume(provider):
                continue
            try:
                text = self._gemini(messages, key, max_tokens) if provider == "gemini" else self._groq(messages, key, max_tokens)
                if text.strip():
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

    def _gemini(self, messages: list[dict], key: str, max_tokens: int) -> str:
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
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        data = self._send("gemini", key, payload)
        try:
            return "".join(part.get("text", "") for part in data["candidates"][0]["content"]["parts"])
        except (KeyError, TypeError, IndexError) as exc:
            raise ProviderError("gemini", "empty_answer") from exc

    def _groq(self, messages: list[dict], key: str, max_tokens: int) -> str:
        payload = {"model": PROVIDERS["groq"]["model"], "messages": messages,
                   "max_completion_tokens": max_tokens, "temperature": 0.7, "stream": False}
        data = self._send("groq", key, payload)
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, TypeError, IndexError) as exc:
            raise ProviderError("groq", "empty_answer") from exc
