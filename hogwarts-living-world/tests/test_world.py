import tempfile
import unittest
from pathlib import Path
from hlw.world import World

class WorldTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.world = World(Path(self.temp.name)/"world.db")

    def tearDown(self):
        self.world.db.close()
        self.temp.cleanup()

    def test_decisions_persist_and_are_idempotent(self):
        result = self.world.apply("save_1", "sebastian", "player_refused", "event_1")
        self.assertEqual((result["affinity"],result["trust"]),(-9,-4))
        self.assertEqual(len(self.world.pending("save_1")),0)
        result = self.world.apply("save_1", "sebastian", "player_refused", "event_2")
        self.assertEqual((result["affinity"],result["trust"]),(-18,-8))
        self.assertEqual(len(self.world.pending("save_1")),1)
        duplicated = self.world.apply("save_1", "sebastian", "player_refused", "event_2")
        self.assertTrue(duplicated["duplicate"])
        self.assertEqual(len(self.world.pending("save_1")),1)
        self.assertEqual(self.world.snapshot("save_1","sebastian")["affinity"],-18)

    def test_save_and_npc_isolation_and_ack(self):
        self.world.apply("save_a","poppy","player_helped","one")
        self.assertEqual(self.world.snapshot("save_a","poppy")["affinity"],12)
        self.assertEqual(self.world.snapshot("save_b","poppy")["affinity"],0)
        self.assertEqual(self.world.snapshot("save_a","ominis")["affinity"],0)
        pending=self.world.pending("save_a")
        self.assertEqual(len(pending),1)
        self.assertEqual(self.world.acknowledge("save_a",[pending[0]["id"]]),1)
        self.assertEqual(self.world.pending("save_a"),[])

    def test_invalid_event_never_mutates(self):
        with self.assertRaises(ValueError):
            self.world.apply("save", "npc", "give_infinite_gold", "evt")
        self.assertEqual(self.world.snapshot("save","npc")["affinity"],0)

    def test_reused_event_id_with_different_payload_rejected(self):
        self.world.apply("save","npc","player_helped","evt")
        with self.assertRaises(ValueError):
            self.world.apply("save","npc","gift_given","evt")
        self.assertEqual(self.world.snapshot("save","npc")["affinity"],12)

if __name__ == "__main__":
    unittest.main()
