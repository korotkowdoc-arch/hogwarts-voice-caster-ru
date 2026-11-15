import json
import math
import tempfile
from pathlib import Path
import unittest

from hogwarts_voice.voice_profile import VoiceProfile, VECTOR_DIM, similarity, normalize_vector

def vector(i=0):
    v = [0.0] * VECTOR_DIM
    v[i] = 1.0
    return v

class VoiceProfileTests(unittest.TestCase):
    def test_default_closed(self):
        p = VoiceProfile()
        self.assertFalse(p.ready())
        ok, score = p.match(vector(0))
        self.assertFalse(ok)

    def test_training_and_same_other_voice(self):
        p = VoiceProfile()
        for _ in range(3):
            p.add_take("Lumos", vector(0))
            p.add_take("Accio", vector(0))
        self.assertTrue(p.ready())
        self.assertEqual(p.match(vector(0), 0.7), (True, 1.0))
        self.assertEqual(p.match(vector(1), 0.7), (False, 0.0))

    def test_save_load_and_no_audio(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "user.json"
            p = VoiceProfile()
            p.add_take("Revelio", vector(1))
            p.save(path)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["version"], 1)
            self.assertIn("Revelio", data["takes"])
            self.assertNotIn("wav", data)
            self.assertEqual(VoiceProfile.load(path).count("Revelio"), 1)

    def test_voice_alias_confirmation(self):
        from hogwarts_voice.spellbook import Spellbook, DEFAULT_SPELLS
        book = Spellbook(DEFAULT_SPELLS)
        p = VoiceProfile()
        p.add_alias("Lumos", "люмосик", book)
        self.assertEqual(p.merged_book(book).parse("люмосик"), ["Lumos"])
        with self.assertRaises(ValueError):
            p.add_alias("Accio", "люмосик", book)

    def test_invalid_features(self):
        with self.assertRaises(ValueError):
            normalize_vector([0]*VECTOR_DIM)
        with self.assertRaises(ValueError):
            normalize_vector([math.nan]+[1]*(VECTOR_DIM-1))

if __name__ == "__main__":
    unittest.main()
