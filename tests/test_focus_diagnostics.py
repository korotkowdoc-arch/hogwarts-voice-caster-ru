"""Game-focus and diagnostics regressions without Windows dependencies."""
import os
import unittest
from hogwarts_voice.windows import is_game_process, foreground_process_name
from hogwarts_voice.__main__ import load_config, DEFAULT_CONFIG

class FocusTests(unittest.TestCase):
    def test_known_game_processes(self):
        for name in ("HogwartsLegacy.exe", "Phoenix-Win64-Shipping.exe",
                     "HogwartsLegacy-Win64-Shipping.exe"):
            self.assertTrue(is_game_process(name), name)
        self.assertFalse(is_game_process("explorer.exe"))
        self.assertFalse(is_game_process("SpellCaster.exe"))

    def test_diagnostics_on_by_default(self):
        config = load_config(DEFAULT_CONFIG)
        self.assertTrue(config["show_partials"])
        self.assertTrue(config["mic_diagnostics"])
        self.assertFalse(config["speaker_verification"])

    def test_non_windows_foreground_is_empty(self):
        if os.name != "nt":
            self.assertEqual(foreground_process_name(), "")

if __name__ == "__main__":
    unittest.main()
