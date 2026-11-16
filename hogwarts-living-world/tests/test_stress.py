import json
import random
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from hlw.providers import DailyBudget
from hlw.world import World

class StressTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.world=World(self.root/"world.sqlite3")
    def tearDown(self):
        self.world.db.close()
        self.tmp.cleanup()

    def test_repeat_same_event_in_parallel_is_applied_once(self):
        def send(_):
            return self.world.apply("save","poppy","player_helped","unique_concurrent")
        with ThreadPoolExecutor(max_workers=8) as ex:
            results=list(ex.map(send,range(24)))
        self.assertEqual(sum(not r["duplicate"] for r in results),1)
        self.assertEqual(self.world.snapshot("save","poppy")["affinity"],12)

    def test_randomized_400_events_and_replay_are_stable(self):
        rng=random.Random(94312)
        npcs=["sebastian","poppy","ominis"]
        event_kinds=["player_helped","player_refused","player_ignored",
                     "apology_accepted","gift_given","meeting_attended","meeting_missed"]
        batch=[(rng.choice(npcs),rng.choice(event_kinds),f"event_{i}") for i in range(400)]
        for npc,kind,eid in batch:
            self.world.apply("save_stress",npc,kind,eid)
        state={npc:self.world.snapshot("save_stress",npc) for npc in npcs}
        outbox_count=len(self.world.pending("save_stress",limit=100))
        for npc,kind,eid in batch:
            self.assertTrue(self.world.apply("save_stress",npc,kind,eid)["duplicate"])
        self.assertEqual(state,{npc:self.world.snapshot("save_stress",npc) for npc in npcs})
        self.assertEqual(outbox_count,len(self.world.pending("save_stress",limit=100)))
        for value in state.values():
            self.assertLessEqual(abs(value["affinity"]),100)
            self.assertLessEqual(abs(value["trust"]),100)

    def test_corrupt_budget_fails_closed_instead_of_reissuing_calls(self):
        path=self.root/"counts.json"
        path.write_text("[]",encoding="utf-8")
        budget=DailyBudget(path,{"gemini":2})
        self.assertFalse(budget.consume("gemini"))
        self.assertEqual(budget.status()["state"],"locked_corrupt_counter")
        path.unlink()  # Explicit manual recovery, not automatic quota bypass.
        self.assertTrue(budget.consume("gemini"))
        self.assertTrue(budget.consume("gemini"))
        self.assertFalse(budget.consume("gemini"))
        self.assertEqual(budget.status()["remaining"]["gemini"],0)
        path.write_text(json.dumps({"date":"invalid","counts":{"gemini":-999}}),encoding="utf-8")
        self.assertFalse(budget.consume("gemini"))

    def test_small_capacity_does_not_invoke_second_time(self):
        budget=DailyBudget(self.root/"budget.json",{"gemini":1})
        self.assertTrue(budget.consume("gemini"))
        self.assertFalse(budget.consume("gemini"))

if __name__=="__main__":
    unittest.main()
