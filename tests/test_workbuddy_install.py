"""WorkBuddy bridge ownership, compatibility and approval boundaries."""
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

INSTALLER = Path(__file__).parents[1] / "scripts/install.py"
spec = importlib.util.spec_from_file_location("workbuddy_installer", INSTALLER)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class WorkBuddyInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / "home"
        self.project = self.root / "project"
        self.home.mkdir()
        self.project.mkdir()
        self.bridge = self.project / ".workbuddy/memory/MEMORY.md"
        self.alias = self.project / ".workbuddy/skills/context-keeper"
        self.alias.parent.mkdir(parents=True)
        self.alias.symlink_to(INSTALLER.parents[1])

    def run_install(self, *args):
        return subprocess.run(["python3", str(INSTALLER), *args], text=True, capture_output=True,
                              env=dict(os.environ, HOME=str(self.home), PYTHONDONTWRITEBYTECODE="1"))

    def ensure(self, approved=False):
        args = ["--ensure-bridge", "--workbuddy", "--skill-dir", str(self.alias), "--root", str(self.project)]
        return self.run_install(*args, *(["--approved"] if approved else []))

    def write_bridge(self, data):
        self.bridge.parent.mkdir(parents=True, exist_ok=True)
        self.bridge.write_bytes(data)

    def test_preview_then_create_and_idempotent_ensure(self):
        preview = self.ensure()
        self.assertEqual(preview.returncode, 0, preview.stdout + preview.stderr)
        self.assertTrue(json.loads(preview.stdout)["approval_required"])
        self.assertFalse(self.bridge.exists())
        first = self.ensure(True)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assertEqual(json.loads(first.stdout)["action"], "created")
        before = self.bridge.read_bytes(), self.bridge.stat().st_mtime_ns
        again = self.ensure()
        self.assertEqual(json.loads(again.stdout)["action"], "unchanged")
        self.assertEqual((self.bridge.read_bytes(), self.bridge.stat().st_mtime_ns), before)
        self.assertFalse((self.home / ".workbuddy").exists())
        self.assertFalse((self.project / "docs").exists())

    def test_legacy_agm_block_adopted_without_rewrite(self):
        # Frozen legacy contract: the deployed marker-to-marker bytes have this hash.
        import hashlib
        block = installer.WORKBUDDY_BRIDGE.rstrip("\n").encode()
        self.assertEqual(hashlib.sha256(block).hexdigest(),
                         "5d464acc40d0bf2b30fc02dcffda1fdbf1cee80c5e3e742da9e85a1c871a8315")
        for suffix in (b"", b"\n\n# existing notes\r\nkeep bytes\r\n"):
            with self.subTest(suffix=suffix):
                self.write_bridge(block + suffix)
                before = self.bridge.read_bytes(), self.bridge.stat().st_mtime_ns
                result = self.ensure(True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(json.loads(result.stdout)["action"], "unchanged")
                self.assertEqual((self.bridge.read_bytes(), self.bridge.stat().st_mtime_ns), before)

    def test_prepend_and_update_preserve_external_bytes(self):
        tail = b"# notes\r\nkeep exact\r\n"
        self.write_bridge(tail)
        result = self.ensure(True)
        self.assertEqual(json.loads(result.stdout)["action"], "prepended")
        self.assertTrue(self.bridge.read_bytes().endswith(tail))
        old = (installer.WORKBUDDY_BRIDGE_START + "\nold rule\n" + installer.WORKBUDDY_BRIDGE_END).encode()
        self.write_bridge(b"prefix\r\n" + old + tail)
        preview = self.ensure()
        self.assertTrue(json.loads(preview.stdout)["approval_required"])
        self.assertIn(old, self.bridge.read_bytes())
        result = self.ensure(True)
        self.assertEqual(json.loads(result.stdout)["action"], "updated")
        data = self.bridge.read_bytes()
        self.assertTrue(data.startswith(installer.WORKBUDDY_BRIDGE.encode().rstrip(b"\n")))
        self.assertIn(b"prefix\r\n", data)
        self.assertTrue(data.endswith(tail))
        self.assertEqual(data.count(installer.WORKBUDDY_BRIDGE_START.encode()), 1)
        self.assertEqual(json.loads(self.ensure(True).stdout)["action"], "unchanged")

    def test_invalid_markers_stop_before_any_install_writes(self):
        first, last, _ = installer._bridge_spec("workbuddy")
        for text in (first, last, last + first, first + last + first + last):
            with self.subTest(text=text):
                self.write_bridge(text.encode())
                before = self.bridge.read_bytes()
                result = self.run_install("--project", str(self.project), "--codex", "--workbuddy", "--approved")
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertEqual(self.bridge.read_bytes(), before)
                self.assertFalse((self.project / "AGENTS.md").exists())
                self.assertFalse((self.project / ".agents").exists())
                self.assertEqual(self.ensure(True).returncode, 2)

    def test_project_bridge_only_preview_install_uninstall(self):
        self.write_bridge(b"# retained\r\n")
        args = ["--project", str(self.project), "--workbuddy", "--bridge-only"]
        preview = self.run_install(*args)
        self.assertEqual(json.loads(preview.stdout)["rule_files"], [str(self.bridge)])
        self.assertEqual(self.bridge.read_bytes(), b"# retained\r\n")
        result = self.run_install(*args, "--approved")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["bridges"][0]["action"], "prepended")
        result = self.run_install("--project", str(self.project), "--workbuddy", "--uninstall", "--approved")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self.bridge.read_bytes().endswith(b"# retained\r\n"))
        self.assertNotIn(installer.WORKBUDDY_BRIDGE_START, self.bridge.read_text())

    def test_unsupported_agents_still_rejected(self):
        for agent in ("cursor", "hermes", "opencode", "openclaw"):
            with self.subTest(agent=agent):
                self.assertEqual(self.run_install("--ensure-bridge", "--" + agent).returncode, 2)
                self.assertEqual(self.run_install("--bridge-only", "--" + agent).returncode, 2)
        self.assertFalse(self.bridge.exists())

    def test_user_alias_uses_user_entry_and_unknown_scope_is_rejected(self):
        self.alias.unlink()
        result = self.ensure(True)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        alias = self.home / ".workbuddy/skills/context-keeper"
        alias.parent.mkdir(parents=True)
        alias.symlink_to(INSTALLER.parents[1])
        result = self.run_install("--ensure-bridge", "--workbuddy", "--skill-dir", str(alias),
                                  "--root", str(self.project), "--approved")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["scope"], "user")
        self.assertEqual(data["bridge"], str(self.home / ".workbuddy/MEMORY.md"))
        self.assertFalse(self.bridge.exists())


if __name__ == "__main__":
    unittest.main()
