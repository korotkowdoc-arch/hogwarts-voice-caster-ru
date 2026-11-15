import tempfile
import unittest
from pathlib import Path
from hlw.compat import CompatibilityError, extract_context, normalize_messages, response_type
from hlw.world import World

class SonorusCompatTests(unittest.TestCase):
    def test_simple_text_and_user_content_parts(self):
        m=normalize_messages([{"role":"system","content":"Be a wizard"},
                              {"role":"user","content":[{"type":"text","text":"Привет!"}]}])
        self.assertEqual(m[1]["content"],"Привет!")

    def test_tool_result_readable_not_executable(self):
        m=normalize_messages([{"role":"assistant","tool_calls":[{"id":"x","function":{"name":"SpawnItem"}}]},
                              {"role":"tool","content":"Observed a spell cast"}])
        self.assertEqual(len(m),1)
        self.assertEqual(m[0]["role"],"user")
        self.assertIn("Untrusted",m[0]["content"])
        self.assertNotIn("SpawnItem",m[0]["content"])

    def test_disable_vision_instead_of_silent_degradation(self):
        with self.assertRaises(CompatibilityError):
            normalize_messages([{"role":"user","content":[{"type":"image_url","image_url":{"url":"data:image/png;base64,..."}}]}])

    def test_context_marker_only_in_system(self):
        marker="[HLW_CONTEXT player=save_3 npc=sebastian]"
        self.assertIsNone(extract_context([{"role":"user","content":marker}]))
        self.assertEqual(extract_context([{"role":"system","content":marker}]),
                         {"player_id":"save_3","npc_id":"sebastian"})
        self.assertEqual(extract_context([{"role":"user","content":"hi"}],
                         {"player_id":"save_4","npc_id":"poppy"}),
                         {"player_id":"save_4","npc_id":"poppy"})

    def test_conflicting_markers_rejected(self):
        with self.assertRaises(CompatibilityError):
            extract_context([{"role":"system","content":
                              "[HLW_CONTEXT player=save npc=poppy] [HLW_CONTEXT player=save npc=sebastian]"}])

    def test_unknown_format_rejected(self):
        with self.assertRaises(CompatibilityError):
            response_type({"type":"json_schema"})
        self.assertEqual(response_type({"type":"json_object"}),"json_object")

class DirectorTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/"world.sqlite"
        self.world=World(self.path)
    def tearDown(self):
        self.world.db.close()
        self.temp.cleanup()

    def test_invitation_once_only_after_two_helps(self):
        self.world.apply("save_1","sebastian","player_helped","quest_1")
        self.assertFalse(any(x["kind"]=="owl_letter_proposal" for x in self.world.pending("save_1")))
        self.world.apply("save_1","sebastian","player_helped","quest_2")
        invitations=[x for x in self.world.pending("save_1") if x["kind"]=="owl_letter_proposal"]
        self.assertEqual(len(invitations),1)
        self.assertTrue(invitations[0]["payload"]["requires_game_adapter"])
        self.world.apply("save_1","sebastian","player_helped","quest_3")
        invitations=[x for x in self.world.pending("save_1") if x["kind"]=="owl_letter_proposal"]
        self.assertEqual(len(invitations),1)

    def test_game_event_proposal_is_not_applied_directly(self):
        result=self.world.apply("save_1","poppy","meeting_accepted","meeting_1")
        self.assertEqual(result["affinity"],4)
        meetings=[x for x in self.world.pending("save_1") if x["kind"]=="meeting_proposal"]
        self.assertEqual(len(meetings),1)
        self.assertEqual(meetings[0]["payload"]["location"],"Beasts classroom")
        self.assertTrue(meetings[0]["payload"]["requires_game_adapter"])

    def test_restart_does_not_duplicate_milestone(self):
        self.world.apply("save_1","ominis","player_helped","one")
        self.world.apply("save_1","ominis","player_helped","two")
        self.world.db.close()
        self.world=World(self.path)
        self.world.apply("save_1","ominis","player_helped","three")
        self.assertEqual(sum(x["kind"]=="owl_letter_proposal" for x in self.world.pending("save_1")),1)

if __name__=="__main__":
    unittest.main()
