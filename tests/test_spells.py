import unittest
from hogwarts_voice.spellbook import Spellbook, DEFAULT_SPELLS
from hogwarts_voice.stream import StreamGate

class SpellbookTests(unittest.TestCase):
    def setUp(self):
        self.book = Spellbook(DEFAULT_SPELLS)

    def test_basic(self):
        self.assertEqual(self.book.parse("ЛЮМОС!"), ["Lumos"])
        self.assertEqual(self.book.parse("авада кедавра"), ["AvadaKedavra"])
        self.assertEqual(self.book.parse("акцио инсендио"), ["Accio", "Incendio"])
        self.assertEqual(self.book.parse("Ну, КРУЦИО."), ["Crucio"])

    def test_no_partial_multiword(self):
        self.assertEqual(self.book.parse("авада"), [])

    def test_alias_collision(self):
        with self.assertRaises(ValueError):
            Spellbook({"Lumos": ["люмос"], "Revelio": ["ЛЮМОС"]})

    def test_partial_stable(self):
        gate = StreamGate(self.book, 2, 150, 600)
        self.assertEqual(gate.feed("люмос", now=1.0), [])
        self.assertEqual(gate.feed("люмос", now=1.04), ["Lumos"])
        self.assertEqual(gate.feed("люмос", now=1.07), [])
        self.assertEqual(gate.feed("люмос", final=True, now=1.12), [])

    def test_combo_and_reset(self):
        gate = StreamGate(self.book, 2, 0, 500)
        self.assertEqual(gate.feed("акцио", now=1.0), [])
        self.assertEqual(gate.feed("акцио", now=1.05), ["Accio"])
        self.assertEqual(gate.feed("акцио инсендио", now=1.10), [])
        self.assertEqual(gate.feed("акцио инсендио", now=1.15), ["Incendio"])
        self.assertEqual(gate.feed("акцио инсендио", final=True, now=1.20), [])
        self.assertEqual(gate.feed("инсендио", final=True, now=2.0), ["Incendio"])

    def test_combo_from_single_final_no_gap(self):
        gate = StreamGate(self.book, 2, 0, 500)
        self.assertEqual(gate.feed("акцио инсендио", final=True, now=1.0),
                         ["Accio", "Incendio"])

    def test_same_spell_throttled(self):
        gate = StreamGate(self.book, 1, 0, 500)
        self.assertEqual(gate.feed("люмос", final=True, now=1.0), ["Lumos"])
        self.assertEqual(gate.feed("люмос", final=True, now=1.2), [])
        self.assertEqual(gate.feed("люмос", final=True, now=1.6), ["Lumos"])

    def test_final_fast(self):
        gate = StreamGate(self.book, 4, 0, 0)
        self.assertEqual(gate.feed("протего", final=True, now=5.0), ["Protego"])


class WrongGoalAliasRegressionTests(unittest.TestCase):
    def test_accio_not_turned_into_goal_phrase(self):
        book = Spellbook(DEFAULT_SPELLS)
        self.assertEqual(book.parse('акцио'), ['Accio'])
        self.assertEqual(book.parse('к цели'), [])
        self.assertNotIn('путь к цели', book.grammar())

if __name__ == "__main__":
    unittest.main()
