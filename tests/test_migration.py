import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_context_keeper_probe import PROBE, _call, _write_valid_context


class MigrationTests(unittest.TestCase):
    def test_all_normal_commands_block_without_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _write_valid_context(root, legacy=True)
            before = {str(p): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            for argv in [('init',), ('status',), ('resume',), ('search','--query','事实'), ('history-search','--query','事实'), ('coverage',), ('record-path','--kind','plan','--title','需求','--session-id','new')]:
                rc, out = _call(*argv, '--root', d)
                self.assertEqual(rc, 3, out)
                self.assertIn('需要迁移', out)
            rc, out = _call('migrate', '--root', d)
            self.assertEqual(rc, 3, out)
            self.assertEqual(before, {str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()})

    def test_confirmed_migration_backup_links_and_new_features(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            old = _write_valid_context(root, legacy=True)
            (root/'evidence.json').write_text('{}')
            old.write_text(old.read_text()+'\n[证据](../../evidence.json)\n')
            (root/'README.md').write_text('[日志](docs/worklog/'+old.name+')\n[日志目录](docs/worklog/)\n')
            (root/'unrelated.md').write_text('[保留](./evidence.json)\n')
            original = old.read_bytes()
            expected = old.read_text().replace('../../evidence.json', '../../../evidence.json').encode()
            rc, out = _call('migrate', '--root', d, '--approved')
            self.assertEqual(rc, 0, out)
            store = root/'docs'/'context-keeper'
            migrated = store/'worklogs'/old.name
            self.assertFalse(old.exists())
            self.assertEqual((root/'unrelated.md').read_text(),'[保留](./evidence.json)\n')
            self.assertEqual(migrated.read_bytes(), expected)
            self.assertIn('docs/context-keeper/worklogs', (root/'README.md').read_text())
            self.assertNotIn('](docs/worklog', (root/'README.md').read_text())
            self.assertFalse((root/'context-keeper.json').exists())
            manifest = json.loads((store/'migration-manifest.json').read_text())
            self.assertEqual((Path(manifest['backup'])/'docs/worklog'/old.name).read_bytes(),original)
            self.assertTrue((store/'evolution/index.md').is_file())
            rc, out = _call('search','--root',d,'--query','增量认知')
            self.assertEqual(rc,0,out);self.assertIn('命中',out)
            rc,out = _call('coverage','--root',d)
            self.assertEqual(rc,0,out)
            rc,out = _call('resume','--root',d,'--query','真实保存')
            self.assertIn('尚未复核',out)
            self.assertIn('完成真实保存复测',out)
            rc,out = _call('record-guard','--root',d,'--path',str(migrated),'--session-id','session-a')
            self.assertEqual(rc,2,out)
            rc,out = _call('migrate','--root',d,'--approved')
            self.assertEqual(rc,0,out);self.assertIn('无需迁移',out)

    def test_custom_destination_rebases_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve();old = _write_valid_context(root,legacy=True)
            (root/'photo.png').write_bytes(b'original')
            old.write_text(old.read_text()+'\n![照片](../../photo.png)\n')
            rc,out = _call('migrate','--root',d,'--store-dir','notes/history','--approved')
            self.assertEqual(rc,0,out)
            self.assertIn('../../../photo.png',(root/'notes/history/worklogs'/old.name).read_text())
            self.assertEqual((root/'photo.png').read_bytes(),b'original')

    def test_conflicts_refuse_before_backup(self):
        for kind in ('mixed','duplicate','symlink'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as d:
                root=Path(d);old=_write_valid_context(root,legacy=True)
                if kind=='mixed':
                    (root/'docs'/'context-keeper').mkdir();(root/'docs'/'context-keeper/keep.md').write_text('keep')
                elif kind=='duplicate':
                    (root/'docs/worklogs').mkdir();(root/'docs/worklogs'/old.name).write_text('conflict')
                else:
                    (old.parent/'alias.md').symlink_to(old)
                original=old.read_bytes()
                rc,out=_call('migrate','--root',d,'--approved')
                self.assertEqual(rc,2,out)
                self.assertEqual(old.read_bytes(),original)
                self.assertFalse((root/'.context-keeper-backups').exists())

    def test_write_failure_restores_originals(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);old=_write_valid_context(root,legacy=True)
            original=old.read_bytes()
            with patch.object(PROBE,'_write_config',side_effect=OSError('simulated failure')):
                with self.assertRaises(OSError):
                    _call('migrate','--root',d,'--store-dir','notes/history','--approved')
            self.assertEqual(old.read_bytes(),original)
            self.assertFalse((root/'notes'/'history').exists())
            self.assertFalse((root/'context-keeper.json').exists())

    def test_empty_legacy_dirs_do_not_trigger(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'docs/worklog').mkdir(parents=True)
            rc,out=_call('init','--root',d,'--approved')
            self.assertEqual(rc,0,out)

    def test_historical_plan_is_not_rewritten_to_fake_new_requirements(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'docs/plans').mkdir(parents=True)
            old=root/'docs/plans/旧需求.md';original='# 原始诉求\n只修这个问题。\n';old.write_text(original)
            rc,out=_call('migrate','--root',d,'--approved')
            self.assertEqual(rc,0,out)
            self.assertEqual((root/'docs/context-keeper/plans/旧需求.md').read_text(),original)
            rc,out=_call('coverage','--root',d)
            self.assertEqual(rc,0,out)
            rc,out=_call('record-guard','--root',d,'--path','docs/context-keeper/plans/旧需求.md','--session-id','new')
            self.assertEqual(rc,2,out)
