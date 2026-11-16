"""Optional cloud-only Russian speech preview using Gemini 3.8 TTS.

NOT integrated into Sonorus voice playback. Never clones game character voices.
Fixed model and URL, rate-limited and cached. Disabled by default.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .providers import DailyBudget

URL="https://generativelanguage.googleapis.com/v1beta/interactions"
MODEL="gemini-3.8-flash-tts"
VOICES={"Kore","Puck","Charon","Aoede"}
STYLES={"neutral":"calm, naturally expressive","warm":"warm and relaxed","tense":"quiet, tense"}
MAX_AUDIO_BYTES=4_000_000

class SpeechUnavailable(RuntimeError):
    pass

class CloudSpeech:
    def __init__(self, directory: Path, transport=None, keys=None):
        self.root=directory
        self.cache=directory/"tts_cache"
        self.cache.mkdir(parents=True,exist_ok=True)
        self.budget=DailyBudget(directory/"speech_counts.json",{"gemini_tts":20})
        self.keys=keys if keys is not None else os.environ
        self.transport=transport or urlopen

    def synthesize(self, text: str, voice: str="Kore", style: str="neutral") -> bytes:
        if not isinstance(text,str) or not 1<=len(text.strip())<=240:
            raise ValueError("text must be 1-240 characters")
        if voice not in VOICES or style not in STYLES:
            raise ValueError("unsupported voice or style")
        text=text.strip()
        digest=hashlib.sha256(f"{MODEL}|{voice}|{style}|{text}".encode("utf-8")).hexdigest()
        path=self.cache/(digest+".wav")
        if path.exists():
            audio=path.read_bytes()
            if audio.startswith(b"RIFF") and len(audio)<=MAX_AUDIO_BYTES:
                return audio
        key=self.keys.get("GEMINI_API_KEY")
        if not key:
            raise SpeechUnavailable("No Gemini free API key available")
        if not self.budget.consume("gemini_tts"):
            raise SpeechUnavailable("Cloud TTS local daily cap reached")
        payload={
            "model":MODEL,
            "input":[{"type":"user_input","content":[{
                "type":"text","text":text,"annotations":[{"type":"speech_metadata","style":STYLES[style]}]
            }]}],
            "response_format":{"type":"audio"},
            "generation_config":{"speech_config":[{"voice":voice}]}
        }
        request=Request(URL,method="POST",data=json.dumps(payload).encode("utf-8"),
                        headers={"Content-Type":"application/json","x-goog-api-key":key,
                                 "User-Agent":"HogwartsLivingWorld/0.2"})
        try:
            with self.transport(request,timeout=40) as response:
                raw=response.read(6_000_000)
            data=json.loads(raw)
            audio=None
            for step in data.get("steps",[]):
                for part in step.get("content",[]):
                    if part.get("type") == "audio" and isinstance(part.get("data"),str):
                        audio=base64.b64decode(part["data"],validate=True)
            if not audio or len(audio)>MAX_AUDIO_BYTES or not audio.startswith(b"RIFF"):
                raise SpeechUnavailable("TTS returned no valid WAV")
            tmp=path.with_suffix(".tmp")
            tmp.write_bytes(audio)
            os.replace(tmp,path)
            return audio
        except (HTTPError,URLError,TimeoutError,OSError,ValueError,KeyError,TypeError) as exc:
            raise SpeechUnavailable("Cloud TTS unavailable; no paid fallback") from exc
