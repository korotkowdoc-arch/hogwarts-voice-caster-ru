import unittest
from hogwarts_voice.recognition_policy import route_spells

class RoutingTests(unittest.TestCase):
    def test_unrelated_vosk_hallucination_never_overrides_failed_training(self):
        self.assertEqual(route_spells(
            trained_spells={"Lumos", "Accio"},
            acoustic_spell=None,
            vosk_candidates=["Disillusionment"]), [])

    def test_correct_acoustic_match_wins(self):
        self.assertEqual(route_spells(
            trained_spells={"Lumos", "Accio"},
            acoustic_spell="Lumos",
            vosk_candidates=["Disillusionment"]), ["Lumos"])

    def test_no_trained_examples_preserve_legacy_vosk_behavior(self):
        self.assertEqual(route_spells(
            trained_spells=set(),
            acoustic_spell=None,
            vosk_candidates=["Lumos"]), ["Lumos"])

    def test_explicit_fallback_opt_in(self):
        self.assertEqual(route_spells(
            trained_spells={"Lumos"},
            acoustic_spell=None,
            vosk_candidates=["Disillusionment"],
            allow_untrained_fallback=True), ["Disillusionment"])

    def test_never_duplicate_trained_spell_after_failed_acoustic_match(self):
        self.assertEqual(route_spells(
            trained_spells={"Lumos"},
            acoustic_spell=None,
            vosk_candidates=["Lumos"],
            allow_untrained_fallback=True), [])

if __name__ == "__main__":
    unittest.main()
