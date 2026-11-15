"""Fast-mode regression tests with no microphone or Windows dependency."""
import unittest
from hogwarts_voice.spellbook import Spellbook, DEFAULT_SPELLS
from hogwarts_voice.stream import StreamGate
from hogwarts_voice.__main__ import load_config, DEFAULT_CONFIG

class FastModeTests(unittest.TestCase):
    def test_default_no_speaker_identification(self):
        cfg = load_config(DEFAULT_CONFIG)
        self.assertFalse(cfg["speaker_verification"])
        self.assertEqual(cfg["stable_partial_updates"], 1)
        self.assertEqual(cfg["block_ms"], 10)

    def test_first_partial_is_enough(self):
        gate = StreamGate(Spellbook(DEFAULT_SPELLS), stable_updates=1,
                          min_gap_ms=0, repeat_gap_ms=450)
        self.assertEqual(gate.feed("экспеллиармус", final=False, now=10.0),
                         ["Expelliarmus"])
        self.assertEqual(gate.feed("экспеллиармус", final=True, now=10.1), [])
        self.assertEqual(gate.feed("акцио", final=False, now=10.2), ["Accio"])

if __name__ == "__main__":
    unittest.main()
