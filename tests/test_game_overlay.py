import unittest
from hogwarts_voice.game_overlay import classify_line

class OverlayTests(unittest.TestCase):
    def test_real_log_status_is_distinguished(self):
        self.assertEqual(classify_line("[sent] Lumos -> Lumos | 99ms")[0],
                         "Отправлено в игру: Lumos")
        self.assertEqual(classify_line("[game:cast] Lumos | confirmed")[0],
                         "✦ Применено: Lumos")
        self.assertIn("Без подтверждения", classify_line(
            "[game:unverified] Lumos | no response")[0])
        self.assertIn("Не сработало", classify_line(
            "[game:failed] Accio | unknown")[0])
    def test_unrelated_lines_never_pop_overlay(self):
        for line in ("[ptt] RECORDING", "[mic] RMS=34",
                     "[heard] невидимость", "whatever"):
            self.assertIsNone(classify_line(line))

if __name__=="__main__":
    unittest.main()
