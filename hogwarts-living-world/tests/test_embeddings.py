"""Tests for Sonorus LTM embedding bridge. NO network or cloud key needed."""
import base64
import json
import math
import struct
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request,urlopen

from hlw.embeddings import (GeminiEmbeddingBridge,EmbeddingUnavailable,parse_input,
                            URL,DIMENSIONS,MODEL)
from hlw.server import create_app
from hlw.providers import Completion

class FakeResponse:
    def __init__(self,raw):
        self.raw=json.dumps(raw).encode("utf-8")
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self,n): return self.raw[:n]

class EmbedTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.calls=[]
        def transport(req,timeout):
            self.calls.append((req.full_url,json.loads(req.data.decode("utf-8")),timeout))
            return FakeResponse({"embedding":{"values":[float(i+1) for i in range(DIMENSIONS)]}})
        self.bridge=GeminiEmbeddingBridge(self.root,transport,
                                         {"GEMINI_API_KEY":"fake-test-key"})
    def tearDown(self):
        self.bridge.close()
        self.tmp.cleanup()

    def test_text_embedding_openai_format_and_norm(self):
        result=self.bridge.response({"model":"text-embedding-3-small","input":"Где библиотека?"})
        self.assertEqual(result["object"],"list")
        self.assertEqual(result["model"],"text-embedding-3-small")
        self.assertEqual(result["data"][0]["index"],0)
        vec=result["data"][0]["embedding"]
        self.assertEqual(len(vec),1536)
        self.assertAlmostEqual(math.sqrt(sum(v*v for v in vec)),1,places=5)
        self.assertEqual(self.calls[0][0],URL)
        self.assertEqual(self.calls[0][1]["model"],"models/"+MODEL)
        self.assertEqual(self.calls[0][1]["outputDimensionality"],1536)
        self.assertEqual(self.calls[0][1]["taskType"],"SEMANTIC_SIMILARITY")

    def test_batch_and_persistent_cache(self):
        result=self.bridge.response({"input":["сова","волшебная палочка","сова"],
                                    "encoding_format":"base64"})
        self.assertEqual(len(result["data"]),3)
        self.assertEqual(len(self.calls),2)
        blob=base64.b64decode(result["data"][0]["embedding"],validate=True)
        self.assertEqual(len(blob),1536*4)
        self.assertEqual(result["data"][0]["embedding"],result["data"][2]["embedding"])
        self.assertEqual(self.bridge.status()["cached_vectors"],2)
        self.assertEqual(self.bridge.budget.status()["remaining"]["gemini_embedding"],238)
        self.bridge.close()
        self.bridge=GeminiEmbeddingBridge(self.root,
                transport=lambda *_a,**_kw: self.fail("Repeated request must be cached"),
                keys={})
        again=self.bridge.response({"input":"сова","encoding_format":"base64"})
        self.assertEqual(again["data"][0]["embedding"],result["data"][0]["embedding"])

    def test_invalid_model_size_and_encoding_are_rejected(self):
        for body in (
            {"input":"test","model":"unknown-paid-model"},
            {"input":"test","dimensions":3072},
            {"input":"test","encoding_format":"unknown"},
            {"input":["x"]*17},
            {"input":"a"*8000},
            {"input":[]},
            {"input":[42]}
        ):
            with self.subTest(body=str(body)[:70]),self.assertRaises(ValueError):
                self.bridge.response(body)
        self.assertFalse(self.calls)

    def test_missing_gemini_key_stays_offline(self):
        self.bridge.close()
        self.bridge=GeminiEmbeddingBridge(self.root,
                transport=lambda *_a,**_kw: self.fail("Network forbidden"),
                keys={})
        with self.assertRaises(EmbeddingUnavailable) as err:
            self.bridge.response({"input":"Привет"})
        self.assertEqual(err.exception.reason,"gemini_embedding_key_missing")

    def test_usage_cap_fails_without_network(self):
        self.bridge.budget.limits["gemini_embedding"]=1
        self.bridge.response({"input":"первый"})
        with self.assertRaises(EmbeddingUnavailable):
            self.bridge.response({"input":"второй"})
        self.assertEqual(len(self.calls),1)

class MockRouter:
    configured=["test_fake"]
    def complete(self,messages,*,max_tokens=250,output_format="text"):
        return Completion("Ответ","fake","test_fake")

class EmbedHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.folder=Path(self.tmp.name)
        self.app=None
        self.srv=None
        self.t=None
    def tearDown(self):
        if self.srv:
            self.srv.shutdown();self.srv.server_close();self.t.join()
            self.app.close_storage()
        self.tmp.cleanup()
    def start(self,enabled):
        self.env=patch.dict("os.environ",{"HLW_ENABLE_EMBEDDINGS":"1" if enabled else "0"})
        with self.env:
            self.app=create_app(self.folder,MockRouter())
        self.srv=ThreadingHTTPServer(("127.0.0.1",0),self.app)
        self.t=threading.Thread(target=self.srv.serve_forever,daemon=True)
        self.t.start()
        return f"http://127.0.0.1:{self.srv.server_port}"
    def post(self,base,body):
        req=Request(base+"/v1/embeddings",data=json.dumps(body).encode(),
                    headers={"Content-Type":"application/json"})
        return urlopen(req,timeout=3)
    def test_endpoint_is_disabled_by_default(self):
        base=self.start(False)
        with self.assertRaises(HTTPError) as got:
            self.post(base,{"model":"text-embedding-3-small","input":"привет"})
        self.assertEqual(got.exception.code,404)
    def test_enabled_without_key_is_503_and_does_not_use_paid_fallback(self):
        with patch.dict("os.environ",{"GEMINI_API_KEY":""}):
            base=self.start(True)
            with self.assertRaises(HTTPError) as got:
                self.post(base,{"model":"text-embedding-3-small","input":"Привет"})
        self.assertEqual(got.exception.code,503)
        with urlopen(base+"/health",timeout=3) as r:
            health=json.loads(r.read())
            self.assertTrue(health["long_term_embeddings"]["model"]==MODEL)

if __name__=="__main__": unittest.main()
