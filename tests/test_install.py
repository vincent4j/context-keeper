from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


INSTALLER = Path(__file__).parents[1] / "scripts" / "install.py"


class InstallTests(unittest.TestCase):
    def test_first_use_project_and_user_symlink(self):
        for agent in ('codex', 'claude'):
            for scope in ('user', 'project'):
                with self.subTest(agent=agent,scope=scope), tempfile.TemporaryDirectory() as d:
                    root = Path(d)
                    home = root / 'home';home.mkdir()
                    project = root / 'project';project.mkdir()
                    base = home if scope == 'user' else project
                    folder = '.agents' if agent == 'codex' else '.claude'
                    skill = base / folder / 'skills/context-keeper'
                    skill.parent.mkdir(parents=True)
                    skill.symlink_to(INSTALLER.parents[1])
                    bridge = (home / ('.codex/AGENTS.md' if agent=='codex' else '.claude/CLAUDE.md')
                              if scope=='user' else project / ('AGENTS.md' if agent=='codex' else 'CLAUDE.md'))
                    bridge.parent.mkdir(parents=True,exist_ok=True)
                    bridge.write_text('# 用户内容\n\n不要修改。\n')
                    cmd = ['python3',str(skill/'scripts/install.py'),'--ensure-bridge','--'+agent,'--skill-dir',str(skill),'--root',str(project)]
                    env = dict(os.environ, HOME=str(home))
                    result = subprocess.run(cmd,env=env,text=True,capture_output=True)
                    self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                    self.assertEqual(json.loads(result.stdout)['scope'],scope)
                    self.assertTrue(bridge.read_text().startswith('# 用户内容\n\n不要修改。\n'))
                    before = bridge.stat().st_mtime_ns
                    result = subprocess.run(cmd,env=env,text=True,capture_output=True)
                    self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                    self.assertEqual(json.loads(result.stdout)['action'],'unchanged')
                    self.assertEqual(bridge.stat().st_mtime_ns,before)
                    other = project/'CLAUDE.md' if agent=='codex' else project/'AGENTS.md'
                    self.assertFalse(other.exists())
                    self.assertFalse((project/'context-keeper').exists())

    def test_first_use_rejects_copied_skill_without_git_checkout(self):
        import shutil
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);home=root/'home';home.mkdir();project=root/'project';project.mkdir()
            skill=home/'.agents/skills/context-keeper';skill.parent.mkdir(parents=True)
            shutil.copytree(INSTALLER.parents[1],skill,ignore=shutil.ignore_patterns('.git','__pycache__'))
            result=subprocess.run(
                ['python3',str(skill/'scripts/install.py'),'--ensure-bridge','--codex','--skill-dir',str(skill),'--root',str(project)],
                env=dict(os.environ,HOME=str(home)),capture_output=True,text=True)
            self.assertEqual(result.returncode,2)
            self.assertIn('Git 源码仓库',result.stdout)
            self.assertFalse((home/'.codex/AGENTS.md').exists())

    def test_first_use_resolved_source_prefers_project_alias(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d)/'home';project=home/'project';project.mkdir(parents=True)
            for base in (home,project):
                skill=base/'.agents/skills/context-keeper';skill.parent.mkdir(parents=True)
                skill.symlink_to(INSTALLER.parents[1])
            result=subprocess.run(['python3',str(INSTALLER),'--ensure-bridge','--codex','--root',str(project)],env=dict(os.environ,HOME=str(home)),capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(json.loads(result.stdout)['scope'],'project')
            self.assertFalse((home/'.codex/AGENTS.md').exists())

    def test_first_use_unknown_scope_does_not_write(self):
        with tempfile.TemporaryDirectory() as d:
            result=subprocess.run(['python3',str(INSTALLER),'--ensure-bridge','--codex','--root',d],env=dict(os.environ,HOME=d),capture_output=True,text=True)
            self.assertEqual(result.returncode,2,result.stdout+result.stderr)
            self.assertEqual(list(Path(d).iterdir()),[])

    def test_bridge_update_preserves_surroundings_and_rejects_bad_markers(self):
        spec=importlib.util.spec_from_file_location('installer_bootstrap',INSTALLER)
        installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'AGENTS.md'
            prefix='\n# Before  \n\n';suffix='\n\n# After  \n\n'
            p.write_text(prefix+installer.BRIDGE_START+'\nold\n'+installer.BRIDGE_END+suffix)
            self.assertEqual(installer._upsert_bridge(p),'updated')
            self.assertEqual(p.read_text(),prefix+installer.BRIDGE.rstrip('\n')+suffix)
            for malformed in (installer.BRIDGE_START,installer.BRIDGE_END,installer.BRIDGE*2):
                p.write_text(malformed)
                with self.assertRaises(RuntimeError):installer._upsert_bridge(p)
                self.assertEqual(p.read_text(),malformed)

    def test_uninstall_refuses_real_source_but_unlinks_installed_alias(self):
        spec = importlib.util.spec_from_file_location('installer_under_test', INSTALLER)
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = root / 'context-keeper'
            source.mkdir()
            marker = source / 'SKILL.md'
            marker.write_text('name: context-keeper')
            with patch.object(installer, 'SOURCE', source):
                with self.assertRaisesRegex(RuntimeError, '源码目录'):
                    installer._remove_skill(root)
                self.assertTrue(marker.exists())
                installed = root / 'installed'
                installed.mkdir()
                (installed / 'context-keeper').symlink_to(source)
                installer._remove_skill(installed)
                self.assertTrue(marker.exists())
                self.assertFalse((installed / 'context-keeper').is_symlink())

    def test_install_refuses_unowned_target(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            target = root / '.agents/skills/context-keeper'
            target.mkdir(parents=True)
            marker = target / 'SKILL.md'
            marker.write_text('name: another-skill')
            result = subprocess.run(['python3', str(INSTALLER), '--project', d, '--codex'], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(marker.read_text(), 'name: another-skill')
            self.assertFalse((root / 'AGENTS.md').exists())

    def test_source_does_not_name_external_skill(self):
        source = INSTALLER.parents[1]
        forbidden = "p" + "rd"
        checked = [source / "SKILL.md", source / "README.md"]
        checked.extend((source / "references").glob("*.md"))
        checked.extend((source / "scripts").glob("*.py"))
        checked.extend((source / "tests").glob("*.py"))
        for path in checked:
            self.assertNotIn(forbidden, path.read_text(encoding="utf-8").lower(), str(path))

    def test_project_install_is_idempotent_symlink_and_preserves_user_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir) / "project"
            project.mkdir()
            (project / "AGENTS.md").write_text("# Existing\n", encoding="utf-8")
            command = ["python3", str(INSTALLER), "--project", str(project), "--all"]
            first = subprocess.run(command, text=True, capture_output=True, check=False)
            second = subprocess.run(command, text=True, capture_output=True, check=False)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertTrue((project / ".agents" / "skills" / "context-keeper" / "SKILL.md").is_file())
            self.assertTrue((project / ".codex" / "skills" / "context-keeper" / "SKILL.md").is_file())
            self.assertTrue((project / ".claude" / "skills" / "context-keeper" / "SKILL.md").is_file())
            self.assertTrue((project / ".agents" / "skills" / "context-keeper").is_symlink())
            self.assertTrue((project / ".codex" / "skills" / "context-keeper").is_symlink())
            self.assertTrue((project / ".claude" / "skills" / "context-keeper").is_symlink())
            self.assertEqual((project / ".agents" / "skills" / "context-keeper").resolve(), INSTALLER.parents[1].resolve())
            self.assertEqual((project / ".codex" / "skills" / "context-keeper").resolve(), INSTALLER.parents[1].resolve())
            self.assertEqual((project / ".claude" / "skills" / "context-keeper").resolve(), INSTALLER.parents[1].resolve())
            agents = (project / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("# Existing", agents)
            self.assertEqual(agents.count("<!-- context-keeper:start -->"), 1)
            self.assertEqual((project / "CLAUDE.md").read_text(encoding="utf-8").count("<!-- context-keeper:start -->"), 1)

    def test_user_install_reports_skill_and_bridge_separately(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir) / "home"
            env = dict(os.environ, HOME=str(home))
            result = subprocess.run(
                ["python3", str(INSTALLER), "--all"],
                text=True,
                capture_output=True,
                check=False,
                env=env,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["scope"], "user")
            self.assertEqual(len(payload["installed"]), 3)
            self.assertEqual(len(payload["bridges"]), 2)
            self.assertTrue((home / ".agents" / "skills" / "context-keeper").is_symlink())
            self.assertTrue((home / ".codex" / "skills" / "context-keeper").is_symlink())
            self.assertTrue((home / ".claude" / "skills" / "context-keeper").is_symlink())
            self.assertTrue((home / ".codex" / "AGENTS.md").is_file())
            self.assertTrue((home / ".claude" / "CLAUDE.md").is_file())

    def test_uninstall_removes_only_managed_files_and_blocks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir) / "project"
            project.mkdir()
            (project / "AGENTS.md").write_text("# Keep me\n", encoding="utf-8")
            install = ["python3", str(INSTALLER), "--project", str(project), "--all"]
            subprocess.run(install, text=True, capture_output=True, check=True)
            result = subprocess.run(
                [*install, "--uninstall"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((project / ".agents" / "skills" / "context-keeper").exists())
            self.assertFalse((project / ".codex" / "skills" / "context-keeper").exists())
            self.assertFalse((project / ".claude" / "skills" / "context-keeper").exists())
            agents = (project / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("# Keep me", agents)
            self.assertNotIn("context-keeper:start", agents)

    def test_bridge_only_does_not_link_skill(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir) / "project"
            project.mkdir()
            result = subprocess.run(
                ["python3", str(INSTALLER), "--project", str(project), "--all", "--bridge-only"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["installed"], [])
            self.assertFalse((project / ".agents" / "skills" / "context-keeper").exists())
            self.assertTrue((project / "AGENTS.md").is_file())

    def test_install_keeps_link_when_target_resolves_to_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir) / "project"
            skill_root = project / ".agents" / "skills"
            skill_root.mkdir(parents=True)
            (skill_root / "context-keeper").symlink_to(INSTALLER.parents[1], target_is_directory=True)
            result = subprocess.run(
                ["python3", str(INSTALLER), "--project", str(project), "--codex"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((skill_root / "context-keeper").is_symlink())

    def test_install_refuses_to_delete_managed_copy_with_possible_local_changes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project = Path(temp_dir) / "project"
            target = project / ".agents" / "skills" / "context-keeper"
            target.mkdir(parents=True)
            (target / "SKILL.md").write_text("---\nname: context-keeper\ndescription: local\n---\n")
            result = subprocess.run(
                ["python3", str(INSTALLER), "--project", str(project), "--codex"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("复制目录", result.stdout)
            self.assertFalse(target.is_symlink())
            self.assertEqual((target / "SKILL.md").read_text(), "---\nname: context-keeper\ndescription: local\n---\n")


if __name__ == "__main__":
    unittest.main()
