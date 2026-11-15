import tempfile
from pathlib import Path
import unittest
from hogwarts_voice.model_storage import (
    MODEL_NAME, installed_model_path, legacy_model_path, migrate_legacy,
    model_layout_ok, REQUIRED_FILES,
)

def write_minimal_model(root: Path):
    for name in REQUIRED_FILES:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"test-file")
    return root

class ModelStorageTests(unittest.TestCase):
    def test_windows_nonascii_project_is_not_used_for_vosk(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            appdata = base / "Данные"
            public = base / "Public"
            # The fake Windows environment offers a Cyrillic LOCALAPPDATA,
            # but an ASCII PUBLIC directory. This must pick the latter.
            env = {"LOCALAPPDATA": str(appdata), "PUBLIC": str(public)}
            desired = installed_model_path(base / "Проект", environ=env, windows=True)
            self.assertTrue(str(desired).isascii())
            self.assertEqual(desired, public / "HogwartsVoiceCasterRU" / "models" / MODEL_NAME)

    def test_prefer_ascii_localappdata(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            env = {"LOCALAPPDATA": str(base / "Local"), "PUBLIC": str(base / "Public")}
            desired = installed_model_path(base / "папка", environ=env, windows=True)
            self.assertEqual(desired, base / "Local" / "HogwartsVoiceCasterRU" / "models" / MODEL_NAME)

    def test_migrate_legacy_model_without_deleting_original(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            source = write_minimal_model(legacy_model_path(base))
            destination = base / "new" / MODEL_NAME
            self.assertTrue(migrate_legacy(base, destination))
            self.assertTrue(model_layout_ok(destination))
            self.assertTrue(model_layout_ok(source))

    def test_incomplete_model_not_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            source = legacy_model_path(base)
            (source / "am").mkdir(parents=True)
            (source / "am" / "final.mdl").write_bytes(b"not-enough")
            self.assertFalse(model_layout_ok(source))
            self.assertFalse(migrate_legacy(base, base / "new" / MODEL_NAME))

if __name__ == "__main__":
    unittest.main()
