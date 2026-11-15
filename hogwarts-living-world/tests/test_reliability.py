import sqlite3
import tempfile
import unittest
from pathlib import Path

from hlw.inbox import GameEventInbox
from hlw.world import World

class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.world=World(self.root / "world.sqlite3")
    def tearDown(self):
        self.world.db.close()
        self.tmp.cleanup()

    def test_probe_is_not_an_npc_action(self):
        before=self.world.snapshot("ue4ss_probe","bridge_probe")
        ping=self.world.apply("ue4ss_probe","bridge_probe","probe_ping","test_ping_1")
        self.assertTrue(ping["probe"])
        self.assertFalse(ping["duplicate"])
        self.assertEqual(self.world.snapshot("ue4ss_probe","bridge_probe"),before)
        self.assertEqual(self.world.pending("ue4ss_probe"),[])
        self.assertEqual(self.world.last_probe()["source"],"ue4ss_probe")
        self.assertTrue(self.world.apply("ue4ss_probe","bridge_probe","probe_ping","test_ping_1")["duplicate"])

    def test_online_backup_is_valid_and_recoverable(self):
        self.world.apply("slot","poppy","player_helped","event_a")
        self.world.apply("slot","poppy","player_helped","event_b")
        backup=self.world.backup(self.root / "backups", keep=2)
        self.assertTrue(backup.is_file())
        b=sqlite3.connect(backup)
        try:
            self.assertEqual(b.execute("PRAGMA integrity_check").fetchone()[0],"ok")
            self.assertEqual(b.execute("SELECT affinity FROM relations WHERE player='slot' AND npc='poppy'").fetchone()[0],24)
            self.assertEqual(b.execute("SELECT count(*) FROM milestones").fetchone()[0],2)
        finally:
            b.close()
        self.assertEqual(self.world.integrity_check(),"ok")

    def test_proposals_only_once_after_repeated_help(self):
        for n in range(10):
            self.world.apply("save1","sebastian","player_helped",f"quest_{n}")
        queued=self.world.pending("save1", limit=100)
        self.assertEqual(sum(x["kind"]=="owl_letter_proposal" for x in queued),1)
        self.assertEqual(sum(x["kind"]=="npc_note" for x in queued),1)

    def test_probe_via_file_inbox(self):
        path=self.root / "game-events.jsonl"
        path.write_text('{"player_id":"ue4ss_probe","npc_id":"bridge_probe","event":"probe_ping","event_id":"test001"}\n',encoding="utf-8")
        inbox=GameEventInbox(path,self.world)
        self.assertEqual(inbox.poll_once()["applied"],1)
        self.assertIsNotNone(self.world.last_probe()["received_at"])
        self.assertEqual(self.world.snapshot("ue4ss_probe","bridge_probe")["affinity"],0)
        self.assertEqual(inbox.poll_once()["applied"],0)

if __name__=="__main__":
    unittest.main()
