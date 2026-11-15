import io
import tempfile
from pathlib import Path
import unittest
import zipfile
from hogwarts_voice.update_client import version_tuple, parse_version, unpack_source_archive
from hogwarts_voice.update_helper import install_source

def archive(files):
    bio=io.BytesIO()
    with zipfile.ZipFile(bio,"w") as z:
        for path,body in files.items():
            z.writestr(path,body)
    return bio.getvalue()

class UpdateTests(unittest.TestCase):
    def test_versions(self):
        self.assertGreater(version_tuple("1.3.0"),version_tuple("1.2.9"))
        self.assertEqual(parse_version('__version__ = "1.3.0"'),"1.3.0")
        with self.assertRaises(ValueError):version_tuple("main")
    def test_extract_source_but_not_config_or_traversal(self):
        with tempfile.TemporaryDirectory() as d:
            stage=Path(d)
            b=archive({
                "project-abc/src/hogwarts_voice/__init__.py":'__version__="1.3.0"',
                "project-abc/src/hogwarts_voice/ru_asr_listener.py":"#stub",
                "project-abc/config.json":"OVERRIDE",
                "project-abc/src/../config.json":"PATH TRAVERSAL",
            })
            root=unpack_source_archive(b,stage)
            self.assertTrue((root/"hogwarts_voice"/"__init__.py").exists())
            self.assertFalse((stage/"config.json").exists())
    def test_success_and_rollback_keep_user_config(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/"config.json").write_text("PERSONAL")
            original=root/"src"/"hogwarts_voice"
            original.mkdir(parents=True)
            (original/"__init__.py").write_text("old")
            stage=root/".hvc-stage-abc"/"src"/"hogwarts_voice"
            stage.mkdir(parents=True)
            (stage/"__init__.py").write_text("new")
            with self.assertRaises(RuntimeError):
                install_source(stage.parent.parent,root,
                               verify=lambda p:(_ for _ in ()).throw(RuntimeError("bad")))
            self.assertEqual((original/"__init__.py").read_text(),"old")
            self.assertEqual((root/"config.json").read_text(),"PERSONAL")
            (stage/"__init__.py").write_text("new")
            backup=install_source(stage.parent.parent,root,verify=lambda p:None)
            self.assertEqual((original/"__init__.py").read_text(),"new")
            self.assertEqual((backup/"src"/"hogwarts_voice"/"__init__.py").read_text(),"old")

if __name__=="__main__":
    unittest.main()
