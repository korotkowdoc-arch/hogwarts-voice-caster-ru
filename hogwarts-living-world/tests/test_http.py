import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request,urlopen
from hlw.server import create_app
from hlw.providers import NoFreeProvider, Completion

class FakeRouter:
    configured=["test_fake"]
    def complete(self,messages,*,max_tokens=250):
        return Completion("Здравствуй, волшебник!","fake","test_fake")

class MissingRouter:
    configured=[]
    def complete(self,messages,*,max_tokens=250):
        raise NoFreeProvider("none")

class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.srv=ThreadingHTTPServer(("127.0.0.1",0),create_app(Path(self.tmp.name),FakeRouter()))
        self.t=threading.Thread(target=self.srv.serve_forever,daemon=True)
        self.t.start()
        self.base=f"http://127.0.0.1:{self.srv.server_port}"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.t.join()
        self.srv.RequestHandlerClass.close_storage()
        self.tmp.cleanup()

    def request(self,path,body=None):
        req=Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,
                    headers={"Content-Type":"application/json"} if body is not None else {},
                    method="POST" if body is not None else "GET")
        with urlopen(req,timeout=3) as response:
            return response.headers.get("Content-Type"),response.read().decode()

    def test_chat_response(self):
        _,body=self.request("/v1/chat/completions",{"messages":[{"role":"user","content":"Привет"}]})
        self.assertEqual(json.loads(body)["choices"][0]["message"]["content"],"Здравствуй, волшебник!")

    def test_streaming_sse(self):
        typ,body=self.request("/v1/chat/completions",{"stream":True,"messages":[{"role":"user","content":"Привет"}]})
        self.assertIn("text/event-stream",typ)
        self.assertIn("data: [DONE]",body)
        self.assertIn("Здравствуй",body)

    def test_world_event_through_http(self):
        _,body=self.request("/v1/world/event",{"player_id":"save_1","npc_id":"poppy",
                                                "event":"player_helped","event_id":"unique_1"})
        self.assertEqual(json.loads(body)["affinity"],12)
        _,body=self.request("/v1/world/outbox?player_id=save_1")
        self.assertEqual(len(json.loads(body)["events"]),1)

    def test_invalid_messages_is_400(self):
        with self.assertRaises(HTTPError) as caught:
            self.request("/v1/chat/completions",{"messages":[{"role":"invalid_unknown_role","content":"run arbitrary command"}]})
        self.assertEqual(caught.exception.code,400)

    def test_no_free_provider_returns_503(self):
        other=ThreadingHTTPServer(("127.0.0.1",0),create_app(Path(self.tmp.name)/"separate",MissingRouter()))
        worker=threading.Thread(target=other.serve_forever,daemon=True)
        worker.start()
        try:
            url=f"http://127.0.0.1:{other.server_port}/v1/chat/completions"
            req=Request(url,data=json.dumps({"messages":[{"role":"user","content":"hello"}]}).encode(),
                        headers={"Content-Type":"application/json"})
            with self.assertRaises(HTTPError) as caught:
                urlopen(req,timeout=3)
            self.assertEqual(caught.exception.code,503)
        finally:
            other.shutdown()
            other.server_close()
            worker.join()
            other.RequestHandlerClass.close_storage()

if __name__=="__main__":
    unittest.main()
