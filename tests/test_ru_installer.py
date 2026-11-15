import unittest
from pathlib import Path
from hogwarts_voice.ru_asr import model_directory, MODEL_FILE, TOKENS_FILE
from download_gigaam import MODEL_SHA256, PREFIX

class NeuralInstallerTests(unittest.TestCase):
    def test_file_names_and_pinned_revision(self):
        self.assertEqual(MODEL_FILE, "model.int8.onnx")
        self.assertEqual(TOKENS_FILE, "tokens.txt")
        self.assertEqual(len(MODEL_SHA256), 64)
        self.assertIn("/resolve/", PREFIX)
        self.assertIn("499bb8", PREFIX)

if __name__ == "__main__":
    unittest.main()
