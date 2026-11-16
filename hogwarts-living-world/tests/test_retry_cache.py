import json
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from hlw.providers import DailyBudget, FreeRouter
from hlw.retry_cache import RetryCache

class RetryCacheTests(unittest.TestCase):
    def test_parallel_identical_requests_execute_once(self):
        cache=RetryCache(ttl_seconds=2)
        gate=threading.Barrier(8)
        counter=[0]
        lock=threading.Lock()
        def action():
            with lock:
                counter[0]+=1
            time.sleep(.12)
            return "ok"
        def invoke(_):
            gate.wait(timeout=4)
            return cache.get_or_run("same",action)
        with ThreadPoolExecutor(max_workers=8) as pool:
            result=list(pool.map(invoke,range(8)))
        self.assertEqual(result,["ok"]*8)
        self.assertEqual(counter[0],1)

    def test_cache_is_per_request_and_short_lived(self):
        cache=RetryCache(ttl_seconds=.05)
        count=[0]
        def action():
            count[0]+=1
            return count[0]
        self.assertEqual(cache.get_or_run("one",action),1)
        self.assertEqual(cache.get_or_run("one",action),1)
        self.assertEqual(cache.get_or_run("two",action),2)
        time.sleep(.075)
        self.assertEqual(cache.get_or_run("one",action),3)

    def test_no_failed_result_is_cached(self):
        cache=RetryCache(ttl_seconds=1)
        calls=[0]
        def flaky():
            calls[0]+=1
            if calls[0]==1:
                raise ValueError("down")
            return 200
        with self.assertRaises(ValueError):
            cache.get_or_run("error",flaky)
        self.assertEqual(cache.get_or_run("error",flaky),200)

    def test_router_retry_uses_one_quota(self):
        with tempfile.TemporaryDirectory() as folder:
            requests=[]
            class FakeResponse:
                def __enter__(self): return self
                def __exit__(self,*args): pass
                def read(self,n):
                    return json.dumps({"candidates":[{"content":{"parts":[{"text":"Привет"}]}}]}).encode()
            def mock(req,timeout):
                requests.append(req)
                return FakeResponse()
            router=FreeRouter(DailyBudget(Path(folder)/"budget.json",{"gemini":2,"groq":2}),
                              mock,{"GEMINI_API_KEY":"fake"})
            msgs=[{"role":"user","content":"Ты здесь?"}]
            one=router.complete(msgs)
            two=router.complete(msgs)
            self.assertEqual(one,two)
            self.assertEqual(len(requests),1)
            self.assertEqual(router.budget.status()["remaining"]["gemini"],1)
            three=router.complete([{"role":"user","content":"Другой вопрос"}])
            self.assertEqual(len(requests),2)
            self.assertEqual(three.text,"Привет")

if __name__=="__main__":
    unittest.main()
