"""Press/hold/release semantics independent of Windows hardware."""
import unittest
from hogwarts_voice.ptt import PushToTalkCapture, key_code

def audio(ms=20):
    return b"\x55\x0f" * int(ms * 16)

class PTTTests(unittest.TestCase):
    def test_exactly_one_phrase_for_one_hold(self):
        ptt = PushToTalkCapture()
        self.assertTrue(ptt.press())
        self.assertFalse(ptt.press())
        for _ in range(30):
            ptt.add(audio())
        captured, ms, reason = ptt.release()
        self.assertEqual(reason, "captured")
        self.assertEqual(round(ms), 600)
        self.assertEqual(captured, audio() * 30)
        self.assertEqual(ptt.release()[0], None)
        self.assertTrue(ptt.press())
        self.assertEqual(ptt.release()[2], "too short")

    def test_short_hold_does_not_cast(self):
        ptt = PushToTalkCapture()
        ptt.press()
        for _ in range(4):
            ptt.add(audio())
        self.assertEqual(ptt.release()[2], "too short")
        self.assertFalse(ptt.held)

    def test_long_hold_is_rejected_not_truncated(self):
        ptt = PushToTalkCapture()
        ptt.press()
        for _ in range(130):
            ptt.add(audio())
        pcm, ms, reason = ptt.release()
        self.assertIsNone(pcm)
        self.assertEqual(reason, "too long")
        self.assertGreater(ms, 2500)

    def test_audio_never_leaks_between_holds(self):
        ptt = PushToTalkCapture()
        ptt.add(audio(200))
        ptt.press()
        ptt.add(audio(300))
        phrase, _, _ = ptt.release()
        self.assertEqual(phrase, audio(300))
        ptt.press()
        ptt.add(audio(210))
        phrase, _, _ = ptt.release()
        self.assertEqual(phrase, audio(210))

    def test_hotkey_whitelist(self):
        self.assertEqual(key_code("F9"),0x78)
        self.assertEqual(key_code("Mouse4"),0x05)
        self.assertEqual(key_code("Mouse5"),0x06)
        with self.assertRaises(ValueError):
            key_code("F8")
        with self.assertRaises(ValueError):
            key_code("Alt+F4")

if __name__ == "__main__":
    unittest.main()
