import tempfile
import unittest
from pathlib import Path
from hogwarts_voice.silence_mod import (
    install_nonverbal, set_nonverbal_enabled, nonverbal_status, pak_directory,
)

class SilenceModTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.game = self.root / "Hogwarts Legacy"
        self.paks = self.game / "Phoenix" / "Content" / "Paks"
        self.paks.mkdir(parents=True)
        self.source = self.root / "nonverbal_P.pak"
        self.source.write_bytes(b"not-real-PAK-fixture")
    def tearDown(self):
        self.temp.cleanup()
    def test_infers_folder_from_install_or_paks(self):
        self.assertEqual(pak_directory(self.game), self.paks)
        self.assertEqual(pak_directory(self.paks), self.paks)
    def test_safe_copy_and_reversible_disable(self):
        copied=install_nonverbal(self.source, self.game)
        self.assertEqual(copied.parent, self.paks / "~mods")
        self.assertEqual(copied.read_bytes(), self.source.read_bytes())
        self.assertEqual(nonverbal_status(copied, self.game), "enabled")
        disabled=set_nonverbal_enabled(copied,self.game,False)
        self.assertTrue(disabled.is_file())
        self.assertEqual(nonverbal_status(copied,self.game),"disabled")
        restored=set_nonverbal_enabled(copied,self.game,True)
        self.assertEqual(restored,copied)
        self.assertEqual(nonverbal_status(copied,self.game),"enabled")
    def test_never_overwrite_existing_game_mod(self):
        copied=install_nonverbal(self.source,self.game)
        with self.assertRaises(FileExistsError):
            install_nonverbal(self.source,self.game)
        self.assertEqual(copied.read_bytes(),b"not-real-PAK-fixture")
    def test_reject_non_pak_and_wrong_install(self):
        with self.assertRaises(ValueError):
            install_nonverbal(self.root/"other.zip", self.game)
        with self.assertRaises(FileNotFoundError):
            install_nonverbal(self.source, self.root/"missing")
        copied=install_nonverbal(self.source,self.game)
        with self.assertRaises(FileNotFoundError):
            set_nonverbal_enabled(copied,self.root/"unrelated",False)
    def test_does_not_remove_unrelated_mods(self):
        other=self.paks / "~mods" / "other.pak"
        other.parent.mkdir()
        other.write_bytes(b"other mod")
        copied=install_nonverbal(self.source, self.game)
        set_nonverbal_enabled(copied,self.game,False)
        self.assertEqual(other.read_bytes(),b"other mod")

if __name__ == "__main__":
    unittest.main()
