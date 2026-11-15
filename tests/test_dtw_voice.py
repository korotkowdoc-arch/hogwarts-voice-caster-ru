"""Offline DTW recognition tests: no Vosk model, no GPU, no cloud."""
import json
import tempfile
import time
import unittest
from pathlib import Path
import numpy as np
from hogwarts_voice.dtw_voice import DTWBank, extract, NUM_FRAMES, FEAT_DIM

def audio(f=220, seconds=.67):
    sr=16000
    t=np.arange(int(sr*seconds))/sr
    # Simple test signal; real spoken words still require real-user validation.
    phi=2*np.pi*(f*t + 45*t*t)
    env=np.minimum(1,t*20)*np.minimum(1,(seconds-t)*20)
    samples=0.32*np.sin(phi)*env
    # Include one quiet period before and after to verify trimming.
    pad=np.zeros(int(sr*.12))
    return (np.clip(np.concatenate((pad,samples,pad)),-.95,.95)*32767).astype("<i2").tobytes()

class DTWTests(unittest.TestCase):
    def test_silence_rejected(self):
        with self.assertRaises(ValueError):
            extract(b"\x00\x00"*16000)

    def test_quiet_realistic_signal_is_not_rejected(self):
        # 0.025 peak amplitude corresponds to quiet speech, which the
        # old 0.017-rms cutoff would reject after energy averaging.
        slow = audio(f=240, seconds=.53)
        pcm = np.frombuffer(slow, dtype="<i2").astype(np.float32)
        quiet = (pcm * .08).astype("<i2").tobytes()
        features, duration = extract(quiet)
        self.assertEqual(features.shape, (NUM_FRAMES, FEAT_DIM))
        self.assertGreater(duration, .19)

    def test_feature_shape(self):
        f,d=extract(audio())
        self.assertEqual(f.shape,(NUM_FRAMES,FEAT_DIM))
        self.assertGreater(d,.3)

    def test_enroll_and_recognize_exact_sample(self):
        bank=DTWBank()
        for freq in (219,220,221):
            bank.add("Lumos",audio(freq))
        self.assertTrue(bank.trained("Lumos"))
        self.assertIsNotNone(bank.quality("Lumos"))
        spell,score,_=bank.match(audio(220))
        self.assertEqual(spell,"Lumos")
        self.assertGreater(score,.72)

    def test_persistent_data_contains_no_raw_audio(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"samples.json"
            bank=DTWBank()
            for _ in range(3): bank.add("Lumos",audio())
            bank.save(path)
            data=json.loads(path.read_text(encoding="utf8"))
            self.assertEqual(data["version"],2)
            self.assertIn("features", data["samples"]["Lumos"][0])
            self.assertEqual(DTWBank.load(path).count("Lumos"),3)
            self.assertNotIn("pcm",str(data))

    def test_reset_only_one_spell(self):
        bank=DTWBank()
        bank.add("Lumos",audio())
        bank.add("Accio",audio(280))
        bank.clear("Lumos")
        self.assertEqual(bank.count("Lumos"),0)
        self.assertEqual(bank.count("Accio"),1)

if __name__=="__main__":
    unittest.main()
