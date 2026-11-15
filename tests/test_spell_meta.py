import unittest
from hogwarts_voice.spell_meta import READINGS, PALETTE, group_of, palette_of
from hogwarts_voice.spellbook import DEFAULT_SPELLS

class MetaTests(unittest.TestCase):
    def test_every_spell_has_localized_display(self):
        self.assertEqual(set(READINGS), set(DEFAULT_SPELLS))
        for spell in DEFAULT_SPELLS:
            self.assertIn(group_of(spell), PALETTE)
            self.assertTrue(all(palette_of(spell)))
if __name__ == "__main__":
    unittest.main()
