"""Verify committed release metadata and the package users actually extract."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("package_skill", ROOT / "scripts/package_skill.py")
PACKAGER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACKAGER)


class PackageTests(unittest.TestCase):
    def assert_install_preview(self, package, temporary):
        home = temporary / "home"
        home.mkdir()
        result = subprocess.run(
            [sys.executable, str(package / "scripts/install.py"), "--codex"],
            env=dict(os.environ, HOME=str(home)), text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)["approval_required"])
        self.assertEqual(list(home.iterdir()), [])

    def test_committed_manifest_allows_install_from_source_export(self):
        manifest = json.loads((ROOT / "manifest.json").read_text())
        self.assertEqual({entry["path"] for entry in manifest["files"]}, set(PACKAGER.FILES))
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            package = temporary / "export"
            for name in ("manifest.json", *PACKAGER.FILES):
                target = package / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / name, target)
            for entry in manifest["files"]:
                with self.subTest(path=entry["path"]):
                    self.assertEqual(hashlib.sha256((package / entry["path"]).read_bytes()).hexdigest(),
                                     entry["sha256"])
            self.assert_install_preview(package, temporary)

    def test_built_zip_keeps_document_links_and_installs_without_git(self):
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            staging = temporary / "staging"
            for name in ("manifest.json", *PACKAGER.FILES):
                target = staging / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / name, target)
            with patch.object(PACKAGER, "ROOT", staging), contextlib.redirect_stdout(io.StringIO()):
                archive_path = PACKAGER.build()
            package = temporary / "extracted"
            with ZipFile(archive_path) as archive:
                archive.extractall(package)
            self.assertEqual((package / "assets/context-keeper-icon.png").read_bytes(),
                             (ROOT / "assets/context-keeper-icon.png").read_bytes())
            self.assertTrue((package / "DESIGN.md").is_file())
            # Check the linked design/report documents too, so bundling a document
            # cannot merely move the broken-link problem one level deeper.
            for name in ("README.md", "DESIGN.md", "docs/verification/2026-10-29-cli/report.md"):
                document = package / name
                text = document.read_text()
                links = re.findall(r"\]\(([^)]+)\)", text)
                links.extend(re.findall(r'(?:src|href)="([^"]+)"', text))
                for link in links:
                    if link.startswith("#") or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", link):
                        continue
                    with self.subTest(document=document.relative_to(package), link=link):
                        self.assertTrue((document.parent / link.split("#", 1)[0]).exists())
            self.assert_install_preview(package, temporary)


if __name__ == "__main__":
    unittest.main()
