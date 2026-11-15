import unittest
import sys
from types import SimpleNamespace
from unittest.mock import patch
from hogwarts_voice.dtw_voice import DTWBank
from hogwarts_voice.dtw_listener import run

class ListenerTests(unittest.TestCase):
    def test_no_model_fails_closed(self):
        with patch.dict(sys.modules, {"sounddevice": SimpleNamespace()}):
            with patch("hogwarts_voice.dtw_listener.DTWBank.load",
                       return_value=DTWBank()):
                self.assertEqual(run(SimpleNamespace(dry_run=True), {}), 2)
if __name__=="__main__":
    unittest.main()
