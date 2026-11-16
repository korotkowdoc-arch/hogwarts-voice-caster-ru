import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError

from hlw.compat import CompatibilityError, normalize_messages
from hlw.diagnostics import RequestHistory

class SonorusContextTests(unittest.TestCase):
    def test_accept_large_sonorus_character_bio(self):
        messages=[{"role":"system","content":"Школа магии: "+("история персонажа. "*2000)},
                  {"role":"user","content":"Почему вы прощаетесь?"}]
        normalized=normalize_messages(messages)
        self.assertEqual(len(normalized),2)
        self.assertGreater(len(normalized[0]["content"]),14000)

    def test_accept_conversation_with_more_than_64_turns(self):
        messages=[{"role":"user" if i%2==0 else "assistant","content":f"turn {i}"}
                  for i in range(80)]
        self.assertEqual(len(normalize_messages(messages)),80)

    def test_reject_unbounded_body(self):
        messages=[{"role":"user","content":"x"*100_001}]
        with self.assertRaises(CompatibilityError):
            normalize_messages(messages)
        many=[{"role":"user","content":"x"*90_000} for _ in range(6)]
        with self.assertRaises(CompatibilityError):
            normalize_messages(many)

class DiagnosticsTests(unittest.TestCase):
    def test_diagnostics_record_only_allowlisted_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/"events.jsonl"
            logs=RequestHistory(file)
            unsafe="gsk_abc-secret\nЭта секретная реплика игрока"
            logs.record(status=503,phase=unsafe,provider="gemini",code=unsafe,
                        duration_ms=1299,chars=35000,messages=66,streaming=True)
            on_disk=file.read_text(encoding="utf-8")
            self.assertNotIn("gsk_",on_disk)
            self.assertNotIn("секретная",on_disk)
            entries=logs.recent()
            self.assertEqual(entries[0]["phase"],"unknown")
            self.assertEqual(entries[0]["status"],503)
            self.assertEqual(entries[0]["message_count"],66)
            self.assertTrue(entries[0]["streaming"])
            reloaded=RequestHistory(file)
            self.assertEqual(reloaded.recent(),entries)

    def test_history_has_fixed_capacity(self):
        with tempfile.TemporaryDirectory() as tmp:
            logs=RequestHistory(Path(tmp)/"safe.jsonl",max_events=10)
            for i in range(55):
                logs.record(status=200,code="ok",chars=i)
            self.assertEqual(len(logs.recent()),10)
            self.assertEqual(logs.recent()[0]["prompt_chars"],54)

if __name__ == "__main__":
    unittest.main()
