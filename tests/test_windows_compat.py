"""Regress native Windows failures without requiring symlink privileges."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path, PureWindowsPath
import re
import tempfile
import unittest
from unittest.mock import patch

from test_context_keeper_probe import PROBE, _call, _write_valid_context

SPEC = importlib.util.spec_from_file_location('windows_installer', Path(__file__).parents[1] / 'scripts/install.py')
INSTALL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALL)


class PortableWindowsRegressionTests(unittest.TestCase):
    def test_new_bridge_is_current_and_legacy_crlf_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            for agent in INSTALL.AGENT_NAMES:
                with self.subTest(agent=agent):
                    path = Path(directory) / agent / 'rules.md'
                    self.assertEqual(INSTALL._upsert_bridge(path, agent), 'created')
                    self.assertTrue(INSTALL._bridge_is_current(path, agent))
                    self.assertNotIn(b'\r\n', path.read_bytes())
                    crlf = path.read_bytes().replace(b'\n', b'\r\n') + b'\r\nexternal text\r\n'
                    path.write_bytes(crlf)
                    self.assertTrue(INSTALL._bridge_is_current(path, agent))
                    self.assertEqual(INSTALL._upsert_bridge(path, agent), 'unchanged')
                    self.assertEqual(path.read_bytes(), crlf)

    def test_display_and_persisted_paths_use_forward_slashes(self):
        root = PureWindowsPath('C:/项目')
        self.assertEqual(PROBE._rel(root, root / 'docs/context-keeper/log.md'), 'docs/context-keeper/log.md')
        self.assertEqual(PROBE._configured_value(root, root / 'notes/history'), 'notes/history')

    def test_status_without_git_is_explicit_and_readonly(self):
        with tempfile.TemporaryDirectory() as directory:
            stream = io.StringIO()
            with patch.object(PROBE.shutil, 'which', return_value=None), \
                    patch.object(PROBE.subprocess, 'run', side_effect=AssertionError('must not launch a process')), \
                    contextlib.redirect_stdout(stream):
                rc = PROBE.main(['status', '--root', directory])
            self.assertEqual(rc, 0)
            self.assertIn('分支和差异未检查', stream.getvalue())
            self.assertIn('记录库操作可继续', stream.getvalue())
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_drive_paths_are_local_and_real_uri_schemes_remain_remote(self):
        for value in ['C:/项目/日志.md', r'C:\项目\日志.md', 'worklogs/日志.md']:
            self.assertFalse(PROBE._is_remote_link(value), value)
        for value in ['https://example.com/x.md', 'mailto:user@example.com', 'viking://~/x.md']:
            self.assertTrue(PROBE._is_remote_link(value), value)

    def test_remove_bridge_splices_out_block_and_keeps_external_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            for agent in [name for name in INSTALL.AGENT_NAMES if name != 'workbuddy']:
                with self.subTest(agent=agent):
                    path = Path(directory) / agent / 'rules.md'
                    self.assertEqual(INSTALL._upsert_bridge(path, agent), 'created')
                    # Embed the block trimmed to its END marker so the bytes
                    # around the splice point are exactly the ones asserted.
                    block = path.read_bytes().rstrip(b'\n')
                    path.write_bytes(b'keep me\n\n\n' + block + b'\n\nafter the block\n\n')
                    self.assertEqual(INSTALL._remove_bridge(path, agent), 'removed')
                    self.assertEqual(path.read_bytes(),
                                     b'keep me\n\n\n\n\nafter the block\n\n')
                    path.write_bytes(b'keep me\r\n\r\n' + block.replace(b'\n', b'\r\n')
                                     + b'\r\nafter the block\r\n')
                    self.assertEqual(INSTALL._remove_bridge(path, agent), 'removed')
                    self.assertEqual(path.read_bytes(),
                                     b'keep me\r\n\r\n\r\nafter the block\r\n')
                    path.write_bytes(b'  \n' + block + b'\n\t')
                    self.assertEqual(INSTALL._remove_bridge(path, agent), 'removed_file')
                    self.assertFalse(path.exists())

    def test_migrate_generated_links_and_manifest_use_posix_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _write_valid_context(root, legacy=True)
            rc, out = _call('migrate', '--root', str(root), '--approved')
            self.assertEqual(rc, 0, out)
            store = root / 'docs' / 'context-keeper'
            memory = (store / 'memory-keeper.md').read_text(encoding='utf-8')
            section = memory.split('## 迁移记录入口\n', 1)[1]
            entries = [line for line in section.splitlines() if line.startswith('- [')]
            self.assertTrue(entries)
            for line in entries:
                self.assertRegex(line, r'^- \[[^\]]+\]\((plans|worklogs)/[^\\)]+\)$')
            manifest = json.loads((store / 'migration-manifest.json').read_text(encoding='utf-8'))
            self.assertTrue(manifest['historical_records'])
            for item in manifest['historical_records']:
                self.assertRegex(item, r'^(plans|worklogs)/[^\\]+$')
            for entry in manifest['files']:
                self.assertNotIn('\\', entry['new'], entry['new'])


@unittest.skipUnless(os.name == 'nt', 'requires real Windows junctions')
class NativeWindowsAliasTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='ck-windows-alias-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "源 & ! ^ %CK_SKILL_SOURCE% [中文] '"
        self.source.mkdir()
        (self.source / '.git').mkdir()
        (self.source / 'SKILL.md').write_text('---\nname: context-keeper\n---\n', encoding='utf-8')
        self.source_bytes = (self.source / 'SKILL.md').read_bytes()
        source_patch = patch.object(INSTALL, 'SOURCE', self.source)
        source_patch.start()
        self.addCleanup(source_patch.stop)
        self.project = self.root / '中文 空格项目'
        self.project.mkdir()

    def call(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            rc = INSTALL.main(['--project', str(self.project), *args])
        return rc, output.getvalue()

    def test_all_agents_install_repeat_ensure_and_remove_without_copying(self):
        self.assertEqual(self.call('--all')[0], 0)
        self.assertEqual(list(self.project.iterdir()), [])
        self.assertEqual(self.call('--all', '--approved')[0], 0)
        aliases = [self.project / folder / 'skills/context-keeper'
                   for folder in ['.agents', '.codex', '.claude', '.workbuddy', '.zcode', '.dsh', '.opencode']]
        for alias in aliases:
            self.assertTrue(INSTALL._is_junction(alias), alias)
            self.assertEqual(alias.resolve(), self.source.resolve())
            self.assertEqual((alias / 'SKILL.md').read_bytes(), self.source_bytes)
        before = {p: p.stat().st_mtime_ns for p in self.project.rglob('*.md')}
        self.assertEqual(self.call('--all', '--approved')[0], 0)
        self.assertEqual(before, {p: p.stat().st_mtime_ns for p in self.project.rglob('*.md')})
        for agent, alias in [('codex', aliases[0]), ('workbuddy', aliases[3])]:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                rc = INSTALL.main(['--ensure-bridge', '--'+agent, '--root', str(self.project), '--skill-dir', str(alias)])
            self.assertEqual(rc, 0)
            self.assertIn('unchanged', output.getvalue())
        self.assertEqual(self.call('--all', '--uninstall', '--approved')[0], 0)
        self.assertTrue(all(not INSTALL._is_alias(p) and not p.exists() for p in aliases))
        self.assertEqual((self.source / 'SKILL.md').read_bytes(), self.source_bytes)

    def test_foreign_junction_is_not_replaced_or_removed(self):
        alias = INSTALL._link_skill(self.project / '.agents/skills')
        foreign = self.root / 'foreign'; foreign.mkdir()
        with patch.object(INSTALL, 'SOURCE', foreign):
            with self.assertRaisesRegex(RuntimeError, '其他来源'):
                INSTALL._check_install_target(alias.parent)
            with self.assertRaisesRegex(RuntimeError, '其他来源'):
                INSTALL._remove_skill(alias.parent)
        self.assertTrue(INSTALL._is_junction(alias))
        INSTALL._remove_skill(alias.parent)
        self.assertEqual((self.source / 'SKILL.md').read_bytes(), self.source_bytes)

    def test_install_failure_rolls_back_created_junctions(self):
        with patch.object(INSTALL, '_upsert_bridge', side_effect=OSError('injected bridge failure')):
            with self.assertRaisesRegex(OSError, 'injected'):
                self.call('--all', '--approved')
        self.assertFalse(any(INSTALL._is_alias(self.project / folder / 'skills/context-keeper')
                             for folder in ['.agents', '.codex', '.claude', '.workbuddy', '.zcode', '.dsh', '.opencode']))
        self.assertEqual((self.source / 'SKILL.md').read_bytes(), self.source_bytes)

    def test_absolute_drive_evidence_is_not_silently_dropped(self):
        path = self.project / '证据.md'; path.write_text('synthetic evidence', encoding='utf-8')
        self.assertEqual(PROBE._linked_records(f'[证据](<{path.as_posix()}>)', self.project), {str(path.resolve())})
