"""Future profile generation protects the probe's default user experience root."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).parent/'evaluations'))
import evaluation_support as support


class RuntimeMemoryProfileTests(unittest.TestCase):
    def fixture(self,root):
        home=root/'synthetic-home';home.mkdir()
        canonical=root/'synthetic-canonical';canonical.mkdir()
        (home/'.context-keeper').symlink_to(canonical,target_is_directory=True)
        evolution=canonical/'evolution';evolution.mkdir()
        (evolution/'fake.md').write_text('SYNTHETIC PRIVATE\n')
        cap=root/'historical-cap';cap.mkdir()
        template=cap/'readonly-auth.sb'
        template.write_text('(version 1)\n(allow default)\n(deny file-read* (subpath '+json.dumps(str(root/'synthetic-old-memory'))+'))\n')
        return home,evolution,cap,template

    def test_planned_and_actual_profiles_match_without_mutating_template(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);home,evolution,cap,template=self.fixture(root)
            original=template.read_bytes()
            bootstrap=root/'bootstrap';(bootstrap/'skills').mkdir(parents=True)
            for name in ['installation_id','.sandbox_migration']:(bootstrap/name).write_text('SYNTHETIC RUNTIME')
            auth=root/'synthetic-auth';auth.write_text('SYNTHETIC AUTH')
            folder=root/'future-session';folder.mkdir();created=[]
            planned,protection=support.planned_runtime_profile(folder,template=template,template_root=cap,user_home=home)
            actual=support.prepare_runtime_node(folder,created,bootstrap=bootstrap,original=auth,template=template,template_root=cap,user_home=home)
            self.assertEqual((folder/'readonly-auth.sb').read_text(),planned)
            self.assertEqual(actual,protection)
            self.assertEqual(json.loads((folder/'runtime-before.json').read_text())['memory_protection'],protection)
            for path in [home/'.context-keeper/evolution',evolution.resolve()]:
                self.assertIn(str(path),protection['protected_roots'])
                self.assertIn('(deny file-read* (subpath '+json.dumps(str(path))+'))',planned)
            self.assertEqual(template.read_bytes(),original)
            self.assertTrue((folder/'codex-home/auth.json').is_symlink())
            self.assertEqual(len(created),1)

    @unittest.skipUnless(sys.platform=='darwin' and shutil.which('sandbox-exec'),'requires macOS seatbelt')
    def test_default_and_canonical_fake_memory_are_denied_but_other_file_reads(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);home,evolution,cap,template=self.fixture(root)
            original=template.read_bytes();allowed=root/'synthetic-allowed.txt';allowed.write_text('SYNTHETIC ALLOWED\n')
            profile,_=support.planned_runtime_profile(root/'future',template=template,template_root=cap,user_home=home)
            for target,success in [(allowed,True),(home/'.context-keeper/evolution/fake.md',False),(evolution/'fake.md',False)]:
                with self.subTest(target=target):
                    result=subprocess.run(['/usr/bin/sandbox-exec','-p',profile,sys.executable,'-c','from pathlib import Path; import sys; print(Path(sys.argv[1]).read_text(),end="")',str(target)],capture_output=True,text=True,timeout=10)
                    self.assertEqual(result.returncode==0,success)
                    self.assertEqual(result.stdout,'SYNTHETIC ALLOWED\n' if success else '')
            self.assertEqual(template.read_bytes(),original)
