import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile
import numpy as np
from hogwarts_voice.ru_asr import RussianTransducerASR, TRANSDUCER_FILES
from hogwarts_voice.transducer_install import FILES, REVISION, sha256_file

class _FakeResult:
    text="Люмос"
class _Stream:
    result=_FakeResult()
    def accept_waveform(self,sr,samples):
        assert sr==16000 and samples.ndim==1
class _Recognizer:
    def create_stream(self):return _Stream()
    def decode_stream(self,stream):pass

class TransducerTests(unittest.TestCase):
    def test_optional_weights_have_expected_sizes_and_hashes(self):
        self.assertEqual(len(REVISION),40)
        self.assertEqual(set(FILES),set(TRANSDUCER_FILES))
        for name,(size,checksum) in FILES.items():
            self.assertGreater(size,50)
            if checksum:self.assertEqual(len(checksum),64)
    def test_decode_uses_existing_spell_routing(self):
        asr=RussianTransducerASR(recognizer=_Recognizer())
        audio=(np.ones(16000,dtype=np.int16)*2500).tobytes()
        self.assertEqual(asr.transcribe(audio),"Люмос")
    def test_no_uninstalled_model_loaded_silently(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(FileNotFoundError):
                RussianTransducerASR(model_dir=Path(folder))
    def test_sha(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"fake"
            path.write_bytes(b"123")
            self.assertEqual(len(sha256_file(path)),64)

if __name__=="__main__":
    unittest.main()
