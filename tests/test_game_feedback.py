"""Mod log feedback must never confuse sending with casting."""
import tempfile
import unittest
from pathlib import Path
from hogwarts_voice.game_feedback import ModLogMonitor, find_log

class GameFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.file=Path(self.tmp.name)/"UE4SS.log"
        self.file.write_text("old: Successfully cast: Lumos\n",encoding="utf-8")
        self.now=10.0
        self.feedback=ModLogMonitor(self.file,clock=lambda:self.now)
        self.feedback.begin()
    def tearDown(self):
        self.tmp.cleanup()
    def add(self,text):
        with self.file.open("a",encoding="utf-8") as out:out.write(text+"\n")
    def test_ignores_old_logs_and_only_confirm_exact(self):
        self.feedback.record_sent("Lumos","Lumos")
        self.assertEqual(self.feedback.poll(),[])
        self.add("[SpellCaster] === Attempting to cast: Lumos ===")
        self.add("[SpellCaster] ✓ Successfully cast: Lumos")
        events=self.feedback.poll()
        self.assertEqual([(e.state,e.spell) for e in events],[("cast","Lumos")])
        self.assertEqual(self.feedback.poll(),[])
    def test_busy_does_not_mark_cast(self):
        self.feedback.record_sent("Expelliarmus","Expelliarmus")
        self.add("[SpellCaster] Expelliarmus still not available after cancel (spell tool busy)")
        self.assertEqual(self.feedback.poll()[0].state,"busy")
        self.assertEqual(len(self.feedback.pending),1)
        self.add("[SpellCaster] ✓ Successfully cast: Expelliarmus")
        self.assertEqual(self.feedback.poll()[0].state,"cast")
    def test_error_and_wrong_command(self):
        self.feedback.record_sent("Stupefy","Stupefy")
        self.add("[SpellCaster] Unknown spell 'Protego' - discarding")
        self.assertEqual(self.feedback.poll(),[])
        self.add("[SpellCaster] === Attempting to cast: Stupefy ===")
        self.add("[SpellCaster] ✗ Failed to execute cast")
        self.assertEqual(self.feedback.poll()[0].state,"failed")
    def test_special_spell(self):
        self.feedback.record_sent("Finite","Finite")
        self.add("[SpellCaster] Finite - cancelled active spell and closed menu")
        self.assertEqual(self.feedback.poll()[0].state,"cast")
    def test_timeout_does_not_claim_failed_cast(self):
        self.feedback.record_sent("Lumos","Lumos")
        self.now+=5.1
        ev=self.feedback.poll()
        self.assertEqual(ev[0].state,"unverified")
    def test_finds_log_from_exe_dir_and_root(self):
        root=Path(self.tmp.name)
        folder=root/"Phoenix"/"Binaries"/"Win64"/"UE4SS_Logs"
        folder.mkdir(parents=True)
        log=folder/"UE4SS.log"
        log.write_text("")
        self.assertEqual(find_log(game_folder=root),log)
        self.assertEqual(find_log(game_executable=folder.parent/"Phoenix-Win64-Shipping.exe"),log)

if __name__=="__main__":
    unittest.main()
