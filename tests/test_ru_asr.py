"""No game, model weights or microphone required for strict routing tests."""
import json
import tempfile
from pathlib import Path
import unittest
import numpy as np

from hogwarts_voice.ru_asr import (
    match_incantation, normalized, load_spell_aliases, RussianASR, DEFAULT_ENABLED
)
class FakeResult:
    text = "Люмос"
class FakeStream:
    result = FakeResult()
    def accept_waveform(self, rate, samples):
        assert rate == 16000
        assert samples.ndim == 1
        assert len(samples) > 4000
class FakeRecognizer:
    def create_stream(self):
        return FakeStream()
    def decode_stream(self, stream):
        pass

class NeuralASRTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.book=load_spell_aliases()

    def test_old_spells_json_keeps_aliases_and_gets_new_actions(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "spells.json"
            file.write_text(json.dumps(
                {"Lumos": ["светлячок"], "Accio": ["акцио"]},
                ensure_ascii=False), encoding="utf-8")
            upgraded = load_spell_aliases(file)
            self.assertIn("Alohomora", upgraded)
            self.assertIn("Map", upgraded)
            self.assertIn("Finite", upgraded)
            self.assertEqual(upgraded["Lumos"], ["светлячок"])
            self.assertEqual(json.loads(file.read_text(encoding="utf-8")),
                             {"Lumos": ["светлячок"], "Accio": ["акцио"]})

    def test_lumos_is_exact(self):
        self.assertEqual(match_incantation("Люмос!", self.book)[0], "Lumos")
        self.assertEqual(match_incantation("люмус", self.book)[0], "Lumos")

    def test_accio(self):
        self.assertEqual(match_incantation("АКЦИО", self.book)[0], "Accio")

    def test_false_disillusionment_is_blocked(self):
        for text in ("невидимость", "моментум", "древняя", "древняя магия",
                     "к цели", "здравствуйте", "люмос пожалуйста", ""):
            self.assertIsNone(match_incantation(text, self.book)[0], text)

    def test_real_observed_neural_spelling(self):
        all_spells = list(self.book)
        self.assertEqual(match_incantation(
            "депульсо", self.book, enabled=all_spells)[0], "Depulso")
        self.assertEqual(match_incantation(
            "экспелярмус", self.book, enabled=all_spells)[0], "Expelliarmus")
        # Reject unrelated or generic ordinary Russian words even if all game
        # commands are enabled.
        for unrelated in ("невидимость", "моментум", "пожалуйста", "завтра"):
            self.assertIsNone(match_incantation(
                unrelated, self.book, enabled=all_spells)[0], unrelated)

    def test_enabled_spells_are_enforced_in_game(self):
        self.assertIsNone(match_incantation(
            "депульсо", self.book, enabled=["Lumos", "Accio"])[0])
        self.assertEqual(match_incantation(
            "депульсо", self.book, enabled=["Lumos", "Depulso"])[0], "Depulso")

    def test_explicit_whitelist_allows_other_names_but_not_generic(self):
        self.assertEqual(match_incantation("конфринго", self.book,
                         enabled=["Confringo"])[0], "Confringo")
        self.assertIsNone(match_incantation("невидимость", self.book,
                          enabled=["Disillusionment"])[0])

    def test_no_short_word_fuzzy_match(self):
        self.assertIsNone(match_incantation("люмоз", self.book)[0])
        self.assertIsNone(match_incantation("акция", self.book)[0])

    def test_fake_neural_decode_accepts_pcm(self):
        asr=RussianASR(recognizer=FakeRecognizer())
        wave=(np.ones(16000,dtype=np.int16)*2200).tobytes()
        self.assertEqual(asr.transcribe(wave), "Люмос")

    def test_empty_silence_never_dispatches(self):
        asr=RussianASR(recognizer=FakeRecognizer())
        wave=b"\x00\x00"*16000
        self.assertEqual(asr.transcribe(wave), "")

if __name__ == "__main__":
    unittest.main()
