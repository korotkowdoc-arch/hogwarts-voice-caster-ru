import base64
import json
import tempfile
import unittest
from pathlib import Path
from hlw.speech import CloudSpeech, SpeechUnavailable, MODEL, URL

FAKE_WAV=b"RIFF"+b"\x00"*8+b"WAVE"+b"\x00"*40

class FakeResponse:
    def __init__(self,payload):
        self.bytes=json.dumps(payload).encode()
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self,max_bytes): return self.bytes[:max_bytes]

class SpeechTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
    def tearDown(self):
        self.tmp.cleanup()

    def test_cloud_tts_fixed_model_and_cache(self):
        requests=[]
        def transport(request,timeout):
            requests.append((request.full_url,json.loads(request.data),timeout))
            return FakeResponse({"steps":[{"type":"model_output","content":[
                {"type":"audio","data":base64.b64encode(FAKE_WAV).decode()}]}]})
        speech=CloudSpeech(Path(self.tmp.name),transport,{"GEMINI_API_KEY":"test_key"})
        self.assertEqual(speech.synthesize("Привет, волшебник!",voice="Kore",style="warm"),FAKE_WAV)
        self.assertEqual(speech.synthesize("Привет, волшебник!",voice="Kore",style="warm"),FAKE_WAV)
        self.assertEqual(len(requests),1)
        self.assertEqual(requests[0][0],URL)
        self.assertEqual(requests[0][1]["model"],MODEL)
        self.assertEqual(requests[0][1]["generation_config"]["speech_config"][0]["voice"],"Kore")

    def test_no_key_does_not_make_network_call(self):
        def forbidden(*args,**kwargs):
            self.fail("Must not send a cloud request without a free key")
        speech=CloudSpeech(Path(self.tmp.name),forbidden,{})
        with self.assertRaises(SpeechUnavailable):
            speech.synthesize("Привет")

    def test_rejects_unknown_custom_model_voice_and_too_long(self):
        speech=CloudSpeech(Path(self.tmp.name),lambda *args,**kwargs:None,{})
        with self.assertRaises(ValueError):
            speech.synthesize("Привет",voice="https://example.com")
        with self.assertRaises(ValueError):
            speech.synthesize("x"*1000)

if __name__=="__main__":
    unittest.main()
