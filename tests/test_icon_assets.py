import io
from pathlib import Path
import tempfile
import unittest
import zipfile
from PIL import Image

from hogwarts_voice.icon_assets import import_zip

class IconImportTest(unittest.TestCase):
    def test_game_icon_extracted_and_only_expected_files(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            png = io.BytesIO()
            Image.new("RGBA", (48, 48), (255, 255, 255, 255)).save(png, "PNG")
            archive = base / "icons.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("Spells/UI_T_lumos.png", png.getvalue())
                z.writestr("../../evil.txt", b"not allowed to extract")
            out = base / "data"
            found = import_zip(archive, out)
            self.assertEqual(found, ["Lumos"])
            self.assertTrue((out / "Lumos.png").exists())
            self.assertFalse((base / "evil.txt").exists())
            with Image.open(out / "Lumos.png") as icon:
                self.assertEqual(icon.size, (480, 480))
                self.assertEqual(icon.mode, "RGBA")

    def test_unknown_pack_not_a_false_success(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            archive = base / "wrong.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("other.png", b"x")
            self.assertEqual(import_zip(archive, base / "out"), [])

if __name__ == "__main__":
    unittest.main()
