import io
import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from hlw.providers import DailyBudget, FreeRouter, NoFreeProvider, PROVIDERS

class MockResponse:
    def __init__(self, data):
        self.payload=json.dumps(data).encode()
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self,n): return self.payload[:n]

class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/"budget.json"
        self.keys={"GEMINI_API_KEY":"fake_gemini","GROQ_API_KEY":"fake_groq"}
    def tearDown(self): self.temp.cleanup()

    def test_gemini_request_uses_free_model_and_keeps_system_prompt(self):
        seen=[]
        def transport(request,timeout):
            seen.append((request.full_url,json.loads(request.data)))
            return MockResponse({"candidates":[{"content":{"parts":[{"text":"Привет!"}]}}]})
        router=FreeRouter(DailyBudget(self.path,{"gemini":10,"groq":10}),transport,self.keys)
        reply=router.complete([{"role":"system","content":"Ты Себастьян"},{"role":"user","content":"Привет"}])
        self.assertEqual(reply.text,"Привет!")
        self.assertIn("gemini-3.5-flash-lite",seen[0][0])
        self.assertEqual(seen[0][1]["systemInstruction"]["parts"][0]["text"],"Ты Себастьян")
        self.assertEqual(len(seen),1)

    def test_rate_limit_falls_back_to_groq(self):
        urls=[]
        def transport(request,timeout):
            urls.append(request.full_url)
            if "googleapis" in request.full_url:
                raise HTTPError(request.full_url,429,"quota",{},io.BytesIO(b""))
            return MockResponse({"choices":[{"message":{"content":"Оминис рядом."}}]})
        router=FreeRouter(DailyBudget(self.path,{"gemini":1,"groq":1}),transport,self.keys)
        reply=router.complete([{"role":"user","content":"Где Оминис?"}])
        self.assertEqual(reply.provider,"groq")
        self.assertEqual(reply.text,"Оминис рядом.")
        self.assertEqual(len(urls),2)
        with self.assertRaises(NoFreeProvider):
            router.complete([{"role":"user","content":"Ещё раз"}])

    def test_no_keys_no_calls_and_no_money(self):
        router=FreeRouter(DailyBudget(self.path,{"gemini":1,"groq":1}),
                          lambda *args,**kwargs:self.fail("Must not call cloud"),{})
        with self.assertRaises(NoFreeProvider):
            router.complete([{"role":"user","content":"hello"}])

    def test_gemini_json_object_requests_mime_and_validates(self):
        seen=[]
        def transport(request,timeout):
            seen.append(json.loads(request.data))
            return MockResponse({"candidates":[{"content":{"parts":[{"text":'{"spoken":"Привет"}'}]}}]})
        router=FreeRouter(DailyBudget(self.path,{"gemini":2,"groq":1}),transport,self.keys)
        reply=router.complete([{"role":"user","content":"json"}],output_format="json_object")
        self.assertEqual(json.loads(reply.text),{"spoken":"Привет"})
        self.assertEqual(seen[0]["generationConfig"]["responseMimeType"],"application/json")

    def test_free_model_allowlist_fixed(self):
        self.assertEqual(set(PROVIDERS),{"gemini","groq"})
        self.assertEqual(PROVIDERS["groq"]["model"],"openai/gpt-oss-20b")

if __name__ == "__main__": unittest.main()
