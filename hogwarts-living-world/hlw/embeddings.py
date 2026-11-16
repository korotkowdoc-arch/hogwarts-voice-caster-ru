"""OpenAI-compatible embedding adapter backed ONLY by Gemini free-tier text embeddings.

Sonorus can keep using its 'text-embedding-3-small' model identifier:
the actual provider is ALWAYS the fixed Gemini embedding-001 endpoint.
Opt-in: HLW_ENABLE_EMBEDDINGS=1, zero paid fallback, local daily cap.
No local neural model. Embeddings cached on disk by SHA256; text not saved.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import sqlite3
import struct
import time
from pathlib import Path
from threading import RLock
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .providers import DailyBudget

DIMENSIONS = 1536
MODEL = "gemini-embedding-001"
URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent"
ALIASES = frozenset(("text-embedding-3-small", "hogwarts-living-world-embedding"))
MAX_INPUTS = 16
MAX_CHARS = 7000

class EmbeddingUnavailable(RuntimeError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)

def parse_input(value) -> list[str]:
    if isinstance(value,str):
        values=[value]
    elif isinstance(value,list) and value and all(isinstance(v,str) for v in value):
        values=value
    else:
        raise ValueError("Embeddings input must be text or a nonempty array of texts")
    if not 1 <= len(values) <= MAX_INPUTS:
        raise ValueError("Embeddings input batch too large")
    if any(not v.strip() or len(v)>MAX_CHARS for v in values):
        raise ValueError("Empty or oversized embedding text (max 7000 chars)")
    return values

class GeminiEmbeddingBridge:
    def __init__(self, directory:Path, transport=None, keys=None):
        directory.mkdir(parents=True,exist_ok=True)
        self.cache_path=directory / "embedding-cache.sqlite3"
        self.budget=DailyBudget(directory / "embedding_counts.json", {"gemini_embedding":240})
        self.transport=transport or urlopen
        self.keys=keys if keys is not None else os.environ
        self.lock=RLock()
        self.db=sqlite3.connect(self.cache_path,check_same_thread=False,timeout=30)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS embedding_cache "
                        "(digest TEXT PRIMARY KEY, vector BLOB NOT NULL, created INTEGER NOT NULL)")
        self.db.commit()

    def close(self):
        with self.lock:
            self.db.close()

    def status(self) -> dict:
        with self.lock:
            count=self.db.execute("SELECT COUNT(*) FROM embedding_cache").fetchone()[0]
        return {"model":"gemini-embedding-001",
                "openai_alias":"text-embedding-3-small",
                "dimensions":DIMENSIONS,"cached_vectors":count,
                "key_present":bool(self.keys.get("GEMINI_API_KEY")),
                "local_budget":self.budget.status(),
                "integration_tested_with_game":False}

    @staticmethod
    def _cache_id(text:str)->str:
        return hashlib.sha256((MODEL+"|"+str(DIMENSIONS)+"|"+text).encode("utf-8")).hexdigest()

    def _embed_one(self,text:str)->bytes:
        digest=self._cache_id(text)
        with self.lock:
            row=self.db.execute("SELECT vector FROM embedding_cache WHERE digest=?",(digest,)).fetchone()
            if row and len(row[0])==4*DIMENSIONS:
                return row[0]
            key=self.keys.get("GEMINI_API_KEY")
            if not key:
                raise EmbeddingUnavailable("gemini_embedding_key_missing")
            if not self.budget.consume("gemini_embedding"):
                raise EmbeddingUnavailable("free_embedding_budget_exhausted_or_locked")
            payload={
                "model":"models/"+MODEL,
                "content":{"parts":[{"text":text}]},
                "outputDimensionality":DIMENSIONS,
                "taskType":"SEMANTIC_SIMILARITY",
            }
            request=Request(URL,method="POST",
                data=json.dumps(payload,ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type":"application/json",
                         "x-goog-api-key":key,
                         "User-Agent":"HogwartsLivingWorld/0.5"})
            try:
                with self.transport(request,timeout=25) as response:
                    data=json.loads(response.read(2_000_000))
                values=data["embedding"]["values"]
                if not isinstance(values,list) or len(values)!=DIMENSIONS:
                    raise ValueError("Embedding dimension mismatch")
                floats=[float(v) for v in values]
                if not all(math.isfinite(v) for v in floats):
                    raise ValueError("Invalid embedding vector")
                # Gemini embedding-001 truncated vectors require normalization.
                norm=math.sqrt(sum(v*v for v in floats))
                if not norm or not math.isfinite(norm):
                    raise ValueError("Zero embedding vector")
                blob=struct.pack("<"+str(DIMENSIONS)+"f",*(v/norm for v in floats))
            except HTTPError as exc:
                raise EmbeddingUnavailable("gemini_embedding_http_"+str(exc.code)) from None
            except (URLError,TimeoutError,OSError,ValueError,KeyError,TypeError,
                    OverflowError,struct.error) as exc:
                raise EmbeddingUnavailable("gemini_embedding_unavailable") from exc
            self.db.execute("INSERT OR REPLACE INTO embedding_cache(digest,vector,created) VALUES(?,?,?)",
                            (digest,blob,int(time.time())))
            self.db.commit()
            return blob

    def response(self, body:dict)->dict:
        model=body.get("model","text-embedding-3-small")
        if model not in ALIASES:
            raise ValueError("Unsupported embedding model alias")
        dimensions=body.get("dimensions")
        if dimensions is not None and (type(dimensions) is not int or dimensions!=DIMENSIONS):
            raise ValueError("Embeddings require exactly 1536 dimensions")
        encoding=body.get("encoding_format","float")
        if encoding not in ("float","base64"):
            raise ValueError("Embeddings encoding_format must be float or base64")
        texts=parse_input(body.get("input"))
        data=[]
        for i,text in enumerate(texts):
            blob=self._embed_one(text)
            vector=(base64.b64encode(blob).decode("ascii") if encoding=="base64"
                    else list(struct.unpack("<"+str(DIMENSIONS)+"f",blob)))
            data.append({"object":"embedding","embedding":vector,"index":i})
        return {"object":"list","data":data,"model":model,
                "usage":{"prompt_tokens":0,"total_tokens":0}}
