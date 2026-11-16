import tempfile
import unittest
from pathlib import Path
from hlw.world import World

class ScriptedStoriesTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.world=World(Path(self.tmp.name)/"story.sqlite")
    def tearDown(self):
        self.world.db.close()
        self.tmp.cleanup()

    def proposals(self,player,kind):
        return [p for p in self.world.pending(player,limit=100) if p["kind"]==kind]

    def test_three_unique_character_scenes(self):
        choices=[("sebastian","sebastian_undercroft_discussion"),
                 ("ominis","ominis_friendship_discussion"),
                 ("poppy","poppy_creatures_discussion")]
        for npc,expected_scene in choices:
            player="save_"+npc
            self.world.apply(player,npc,"meeting_attended","meet_1")
            scenes=self.proposals(player,"scene_proposal")
            self.assertEqual(len(scenes),1)
            self.assertEqual(scenes[0]["payload"]["scene_id"],expected_scene)
            self.assertTrue(scenes[0]["payload"]["requires_game_adapter"])
            self.assertFalse(scenes[0]["payload"]["game_action_performed"])
            self.world.apply(player,npc,"meeting_attended","meet_2")
            self.assertEqual(len(self.proposals(player,"scene_proposal")),1)
            self.assertIn(expected_scene.split("_")[0],npc)

    def test_refusal_then_apology_proposes_reconciliation_once(self):
        self.world.apply("save","sebastian","player_refused","one")
        self.world.apply("save","sebastian","apology_accepted","two")
        self.world.apply("save","sebastian","apology_accepted","three")
        recon=[e for e in self.proposals("save","social_reaction_proposal")
               if e["payload"].get("reaction_id")=="first_reconciliation"]
        self.assertEqual(len(recon),1)
        self.assertIn("first_reconciliation",
                      self.world.story_progress("save","sebastian")["completed_milestones"])

    def test_apology_without_conflict_does_not_create_fake_backstory(self):
        self.world.apply("save","poppy","apology_accepted","one")
        self.assertEqual(self.proposals("save","social_reaction_proposal"),[])

    def test_missed_meeting_produces_single_reminder(self):
        self.world.apply("save","poppy","meeting_missed","miss1")
        self.world.apply("save","poppy","meeting_missed","miss2")
        reminder=[e for e in self.proposals("save","owl_letter_proposal")
                  if e["payload"].get("letter_id")=="missed_meeting_followup"]
        self.assertEqual(len(reminder),1)

    def test_low_trust_does_not_trigger_warm_sebastian_scene(self):
        self.world.apply("save","sebastian","player_refused","ref1")
        self.world.apply("save","sebastian","player_refused","ref2")
        self.world.apply("save","sebastian","meeting_attended","meet1")
        self.assertEqual(self.proposals("save","scene_proposal"),[])

    def test_personas_dont_leak_across_saves(self):
        self.world.apply("a","poppy","meeting_attended","one")
        self.assertEqual(self.world.story_progress("b","poppy")["completed_milestones"],[])
        self.assertEqual(self.proposals("b","scene_proposal"),[])

if __name__=="__main__":
    unittest.main()
