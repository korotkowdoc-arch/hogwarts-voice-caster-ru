import unittest
from concurrent.futures import Future
from hogwarts_voice.early_decode import EarlyDecode

def pcm(level,n=320):
    return int(level).to_bytes(2,"little",signed=True)*n

class EarlyDecodeTests(unittest.TestCase):
    def setUp(self):
        self.g=EarlyDecode(minimum_ms=300,quiet_ms=100,speech_rms=360)
        self.frames=[]
        self.count=0
    def feed(self,p):
        self.frames.append(p)
        def submit(audio):
            self.count+=1
            f=Future()
            f.set_result(("люмос",12.5))
            return f
        self.g.feed(p,snapshot=lambda:b"".join(self.frames),submit=submit)
    def test_one_preview_and_reuse_after_silence(self):
        for _ in range(22):self.feed(pcm(2000)) # 440ms voice
        for _ in range(8):self.feed(pcm(0)) # 160ms silence
        self.assertEqual(self.count,1)
        f=self.g.release_future(b"".join(self.frames))
        self.assertEqual(f.result()[0],"люмос")
        self.assertEqual(self.count,1)
    def test_resumed_speech_requires_full_decode(self):
        for _ in range(22):self.feed(pcm(2000))
        for _ in range(8):self.feed(pcm(0))
        self.feed(pcm(2000))
        self.assertIsNone(self.g.release_future(b"".join(self.frames)))
    def test_short_noise_no_preview(self):
        for _ in range(25):self.feed(pcm(10))
        self.assertEqual(self.count,0)
        self.assertIsNone(self.g.release_future(b"".join(self.frames)))
    def test_no_early_dispatched_result(self):
        for _ in range(20):self.feed(pcm(2000))
        self.assertEqual(self.count,0)
        self.assertIsNone(self.g.release_future(b"".join(self.frames)))

if __name__=="__main__":
    unittest.main()
