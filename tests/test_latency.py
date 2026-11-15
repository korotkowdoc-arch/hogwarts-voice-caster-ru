import struct
import unittest
from hogwarts_voice.latency import AudioDelayMeter

class AudioDelayMeterTests(unittest.TestCase):
    def test_onset_and_quiet_reset(self):
        m = AudioDelayMeter(rms_threshold=700, release_ms=300)
        quiet = struct.pack("<h", 10) * 320
        loud = struct.pack("<h", 4000) * 320
        self.assertIsNone(m.observe(quiet, 1.0))
        self.assertEqual(m.observe(loud, 1.10), 1.10)
        self.assertEqual(m.observe(loud, 1.14), 1.10)
        self.assertEqual(m.observe(quiet, 1.19), 1.10)
        self.assertIsNone(m.observe(quiet, 1.50))
        self.assertEqual(m.observe(loud, 1.80), 1.80)

if __name__ == "__main__":
    unittest.main()
