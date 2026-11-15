import json
import tempfile
import unittest
from pathlib import Path
from hlw.world import World
from hlw.inbox import GameEventInbox

class InboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.world=World(self.root/"db.sqlite")
        self.path=self.root/"game-events.jsonl"
        self.inbox=GameEventInbox(self.path,self.world)

    def tearDown(self):
        self.inbox.stop()
        self.world.db.close()
        self.tmp.cleanup()

    def write(self,obj):
        with self.path.open("ab") as f:
            f.write(json.dumps(obj).encode("utf-8")+b"\n")

    def test_accepts_and_deduplicates_event(self):
        data={"player_id":"slot_1","npc_id":"sebastian","event":"player_helped","event_id":"task_a"}
        self.write(data)
        self.assertEqual(self.inbox.poll_once()["applied"],1)
        self.assertEqual(self.world.snapshot("slot_1","sebastian")["affinity"],12)
        self.assertEqual(self.inbox.poll_once()["applied"],0)
        self.write(data)
        self.assertEqual(self.inbox.poll_once()["duplicate"],1)
        self.assertEqual(self.world.snapshot("slot_1","sebastian")["affinity"],12)

    def test_incomplete_json_line_not_processed_until_complete(self):
        data={"player_id":"slot_1","npc_id":"poppy","event":"player_refused","event_id":"refused_a"}
        content=json.dumps(data).encode("utf-8")
        self.path.write_bytes(content)
        self.assertEqual(self.inbox.poll_once()["applied"],0)
        with self.path.open("ab") as f: f.write(b"\n")
        self.assertEqual(self.inbox.poll_once()["applied"],1)

    def test_rejects_unknown_event_and_keeps_working(self):
        self.write({"player_id":"slot_1","npc_id":"poppy","event":"spawn_dragon","event_id":"bad_a"})
        self.assertEqual(self.inbox.poll_once()["rejected"],1)
        self.write({"player_id":"slot_1","npc_id":"poppy","event":"gift_given","event_id":"good_a"})
        self.assertEqual(self.inbox.poll_once()["applied"],1)
        self.assertEqual(self.world.snapshot("slot_1","poppy")["affinity"],5)

    def test_oversized_completed_line_does_not_block_next_valid_event(self):
        self.path.write_bytes(b"x"*25000+b"\n")
        self.write({"player_id":"slot_1","npc_id":"poppy","event":"gift_given","event_id":"valid_after_long"})
        stats=self.inbox.poll_once()
        self.assertEqual(stats["rejected"],1)
        self.assertEqual(stats["applied"],1)
        self.assertEqual(self.world.snapshot("slot_1","poppy")["affinity"],5)

    def test_restart_preserves_file_cursor(self):
        self.write({"player_id":"slot_1","npc_id":"ominis","event":"player_helped","event_id":"a"})
        self.assertEqual(self.inbox.poll_once()["applied"],1)
        self.world.db.close()
        self.world=World(self.root/"db.sqlite")
        self.inbox=GameEventInbox(self.path,self.world)
        self.assertEqual(self.inbox.poll_once()["applied"],0)
        self.assertEqual(self.world.snapshot("slot_1","ominis")["affinity"],12)

if __name__=="__main__":
    unittest.main()
