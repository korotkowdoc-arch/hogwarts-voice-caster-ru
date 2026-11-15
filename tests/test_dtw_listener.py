import unittest
from types import SimpleNamespace
from unittest.mock import patch
from hogwarts_voice.dtw_voice import DTWBank
from hogwarts_voice.dtw_listener import run

class ListenerTests(unittest.TestCase):
    def test_no_model_fails_closed(self):
        with patch("hogwarts_voice.dtw_listener.DTWBank.load",
                   return_value=DTWBank()):
            # Requires sounddevice installed on CI, not a game or microphone.
            self.assertEqual(run(SimpleNamespace(dry_run=True), {}), 2)
if __name__=="__main__":
    unittest.main()
