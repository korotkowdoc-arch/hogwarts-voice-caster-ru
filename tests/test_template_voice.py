import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from hogwarts_voice.template_voice import PronunciationBank, SpeechSegmenter, extract

def synthetic(freq=260, seconds=0.8, amplitude=0.24):
    sr = 16000
    t = np.arange(round(sr * seconds)) / sr
    # Distinct temporal spectral patterns are preferable to a constant tone.
    wave = amplitude * (np.sin(2 * np.pi * freq * t) +
                         0.25 * np.sin(2 * np.pi * (freq + 90) * t))
    env = np.minimum(1.0, t * 22) * np.minimum(1.0, (seconds - t) * 22)
    return (np.clip(wave * env, -0.95, 0.95) * 32767).astype("<i2").tobytes()

class TemplateTests(unittest.TestCase):
    def test_silence_and_short_rejected(self):
        with self.assertRaises(ValueError):
            extract(b"\x00\x00" * 16000)
        with self.assertRaises(ValueError):
            extract(synthetic(seconds=0.09))

    def test_training_requires_three_and_never_saves_wav(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "patterns.json"
            bank = PronunciationBank()
            for i in range(2):
                self.assertEqual(bank.add("Accio", synthetic(280 + 3*i)), i+1)
            self.assertFalse(bank.trained("Accio"))
            self.assertEqual(bank.add("Accio", synthetic(282)), 3)
            self.assertTrue(bank.trained("Accio"))
            bank.save(path)
            raw = json.loads(path.read_text(encoding="utf8"))
            self.assertIn("features", raw["samples"]["Accio"][0])
            self.assertNotIn("pcm", str(raw))
            self.assertNotIn("wav", str(raw))
            loaded = PronunciationBank.load(path)
            self.assertEqual(loaded.count("Accio"), 3)
            self.assertTrue(loaded.match(synthetic(281), threshold=0.4)[0] == "Accio")

    def test_segmenter_keeps_phrase_and_ends_at_silence(self):
        seg = SpeechSegmenter()
        silence = b"\x00\x00" * 320
        phrase = synthetic(280, 0.6)
        for _ in range(5):
            self.assertIsNone(seg.feed(silence))
        ready = None
        for i in range(0, len(phrase), 640):
            possible = seg.feed(phrase[i:i+640])
            if possible: ready = possible
        for _ in range(8):
            possible = seg.feed(silence)
            if possible: ready = possible
        self.assertIsNotNone(ready)
        self.assertGreater(len(ready), 12000)

if __name__ == "__main__":
    unittest.main()
