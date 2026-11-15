import unittest
from hogwarts_voice.game_interactions import (
    ACTION_IDS, interact_with_lock, validate_interact_key,
)
class GameActionsTests(unittest.TestCase):
    def test_alohomora_is_contextual_not_wand_cast(self):
        self.assertIn("Alohomora", ACTION_IDS)
    def test_game_focus_required(self):
        events = []
        ok, msg = interact_with_lock(
            key="F", focus_check=lambda: False, sender=events.append)
        self.assertFalse(ok)
        self.assertEqual(events, [])
        self.assertIn("foreground", msg)
    def test_one_physical_key_pair_per_action(self):
        events=[]
        ok, msg=interact_with_lock(
            key="f", focus_check=lambda: True, sender=events.append)
        self.assertTrue(ok)
        self.assertEqual(events, ["F"])
        self.assertEqual(msg, "interact")
    def test_bogus_key_never_sent(self):
        for key in ("", "F9", "CTRL+F", " ", "Mouse5", None):
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_interact_key(key)
    def test_action_error_is_not_cast(self):
        def fail(key):
            raise OSError("input blocked")
        ok, reason=interact_with_lock(
            key="F", focus_check=lambda: True, sender=fail)
        self.assertFalse(ok)
        self.assertIn("failed", reason)
if __name__ == "__main__":
    unittest.main()
