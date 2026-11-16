import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request,urlopen
from hlw.server import create_app
from hlw.providers import NoFreeProvider, Completion

class FakeRouter:
    configured=["test_fake"]
    last_messages=[]
    def complete(self,messages,*,max_tokens=250,output_format="text"):
        self.last_messages=messages
        return Completion('{"ok":true}' if output_format=="json_object" else "Здравствуй, волшебник!","fake","test_fake")

class MissingRouter:
    configured=[]
    def complete(self,messages,*,max_tokens=250):
        raise NoFreeProvider("none")

class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.router=FakeRouter()
        self.srv=ThreadingHTTPServer(("127.0.0.1",0),create_app(Path(self.tmp.name),self.router))
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

    def test_openai_wav_speech_alias_never_calls_paid_model(self):
        class DummySpeech:
            called = []
            def synthesize(self,text,voice,style):
                self.called.append((text,voice,style))
                return b"RIFF" + b"\\x00"*8 + b"WAVE"
        dummy=DummySpeech()
        with patch.dict("os.environ",{"HLW_ENABLE_CLOUD_TTS":"1"}), patch("hlw.server.CloudSpeech",return_value=dummy):
            app=create_app(Path(self.tmp.name)/"tts",FakeRouter())
        srv=ThreadingHTTPServer(("127.0.0.1",0),app)
        worker=threading.Thread(target=srv.serve_forever,daemon=True)
        worker.start()
        try:
            base=f"http://127.0.0.1:{srv.server_port}/v1/audio/speech"
            payload={"model":"tts-1","input":"Привет","voice":"alloy","response_format":"wav"}
            req=Request(base,data=json.dumps(payload).encode(),headers={"Content-Type":"application/json"})
            with urlopen(req,timeout=3) as response:
                self.assertEqual(response.headers["Content-Type"],"audio/wav")
                self.assertTrue(response.read().startswith(b"RIFF"))
            self.assertEqual(dummy.called,[("Привет","Kore","neutral")])
            payload["response_format"]="mp3"
            req=Request(base,data=json.dumps(payload).encode(),headers={"Content-Type":"application/json"})
            with self.assertRaises(HTTPError) as caught:
                urlopen(req,timeout=3)
            self.assertEqual(caught.exception.code,400)
        finally:
            srv.shutdown();srv.server_close();worker.join();app.close_storage()

    def test_dashboard_is_local_and_never_contains_secrets(self):
        req=Request(self.base+"/")
        with urlopen(req,timeout=3) as response:
            html=response.read().decode("utf-8")
            self.assertIn("text/html",response.headers.get("Content-Type"))
            self.assertIn("Hogwarts Living World",html)
            self.assertIn("frame-ancestors 'none'",response.headers.get("Content-Security-Policy"))
            self.assertNotIn("GEMINI_API_KEY",html)

    def test_rejects_unsafe_cross_origin_post(self):
        req=Request(self.base+"/v1/chat/completions",data=b'{}',
                    headers={"Content-Type":"application/json","Origin":"https://random-site.example"})
        with self.assertRaises(HTTPError) as caught:
            urlopen(req,timeout=3)
        self.assertEqual(caught.exception.code,403)

    def test_rejects_simple_cross_site_content_type(self):
        req=Request(self.base+"/v1/chat/completions",data=b'{}',
                    headers={"Content-Type":"text/plain"})
        with self.assertRaises(HTTPError) as caught:
            urlopen(req,timeout=3)
        self.assertEqual(caught.exception.code,415)

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

    def test_system_marker_injects_save_aware_memory(self):
        self.request("/v1/world/event",{"player_id":"save_1","npc_id":"sebastian",
                                          "event":"player_refused","event_id":"decision_7"})
        self.request("/v1/chat/completions",{"messages":[
            {"role":"system","content":"You are Sebastian [HLW_CONTEXT player=save_1 npc=sebastian]"},
            {"role":"user","content":"Привет"}]})
        self.assertIn("отношение -9/100, доверие -4/100", self.router.last_messages[0]["content"])
        self.assertIn("Игрок отказался помогать", self.router.last_messages[0]["content"])
        self.assertIn("Себастьян", self.router.last_messages[0]["content"])

    def test_json_object_response_mode(self):
        _,body=self.request("/v1/chat/completions",{"response_format":{"type":"json_object"},
                              "messages":[{"role":"user","content":"Answer JSON"}]})
        self.assertEqual(json.loads(json.loads(body)["choices"][0]["message"]["content"]),{"ok":True})

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
