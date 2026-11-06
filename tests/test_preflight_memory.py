from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/preflight_memory.py"
SPEC = importlib.util.spec_from_file_location("preflight_memory", SCRIPT)
PREFLIGHT = importlib.util.module_from_spec(SPEC)
with patch.object(sys, "path", [str(SCRIPT.parent), *sys.path]):
    SPEC.loader.exec_module(PREFLIGHT)


class PreflightMemoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="context-keeper-preflight-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.store = self.root / "docs/context-keeper"
        self.evolution = self.store / "evolution"
        self.evolution.mkdir(parents=True)
        self.worklog = self.store / "worklogs/2026-11-06-卸载验证.md"
        self.worklog.parent.mkdir()
        self.worklog.write_text("# OpenCode 项目卸载验证\n两个宿主的加载检查均通过。\n")
        (self.store / "memory-keeper.md").write_text("# 项目记忆\n")
        self.index = self.evolution / "index.md"
        self.index.write_text("# 经验索引\n\n## 有效经验\n")

    def experience(self, name="卸载验证", *, identifier="CK-001", status="已验证",
                   selector="uninstall-skill | opencode | project", evidence=None):
        if evidence is None:
            evidence = "[验证日志](../worklogs/2026-11-06-卸载验证.md)"
        document = self.evolution / f"{name}.md"
        document.write_text(
            f"# {name}\n\n"
            f"- **编号：** {identifier}\n"
            f"- **状态：** {status}\n"
            "- **触发条件：** 当前项目准备卸载 OpenCode 的 Context Keeper\n"
            "- **已知事实：** 另一宿主的加载检查在卸载前后均通过\n"
            f"- **证据位置：** {evidence}\n"
            "- **建议动作：** 核对项目既有的另一宿主加载检查是否仍适用\n"
            "- **适用范围：** 本项目、OpenCode、项目级安装\n"
            f"- **操作前提示：** {selector}\n",
            encoding="utf-8",
        )
        with self.index.open("a") as stream:
            stream.write(f"- [{name}]({name}.md)\n")
        return document

    def find(self, **kwargs):
        return PREFLIGHT.find_hint(self.root, "uninstall-skill", "opencode", "project", **kwargs)

    def snapshot(self):
        return {str(path.relative_to(self.root)): path.read_bytes()
                for path in self.root.rglob("*") if path.is_file()}

    def test_returns_one_exact_matching_experience_with_relative_evidence(self):
        self.experience("第一条")
        self.experience("第二条", identifier="CK-002")
        before = self.snapshot()
        hint = self.find()
        self.assertEqual(hint["id"], "CK-001")
        self.assertEqual(hint["experience"], "docs/context-keeper/evolution/第一条.md")
        self.assertEqual(hint["evidence"], ["docs/context-keeper/worklogs/2026-11-06-卸载验证.md"])
        self.assertIn("检查是否仍适用", hint["check"])
        self.assertEqual(self.find(), hint)
        self.assertEqual(self.snapshot(), before)

    def test_status_and_selector_must_both_match(self):
        for index, (status, selector) in enumerate((
            ("待验证", "uninstall-skill | opencode | project"),
            ("已替代", "uninstall-skill | opencode | project"),
            ("", "uninstall-skill | opencode | project"),
            ("已验证", "uninstall-skill | zcode | project"),
            ("已验证", "uninstall-skill | opencode | user"),
            ("已验证", "install-skill | opencode | project"),
            ("已验证", "uninstall-skill | * | project"),
            ("已验证", ""),
        )):
            self.experience(str(index), status=status, selector=selector)
        self.assertIsNone(self.find())
        self.experience("有效条目")
        self.assertEqual(self.find()["experience"], "docs/context-keeper/evolution/有效条目.md")

    def test_missing_required_field_or_excessive_body_is_skipped(self):
        entry = self.experience()
        original = entry.read_text()
        entry.write_text(original.replace("- **建议动作：** 核对项目既有的另一宿主加载检查是否仍适用\n", ""))
        self.assertIsNone(self.find())
        entry.write_text(original + "长" * PREFLIGHT.probe.EVOLUTION_MAX_CHARS)
        self.assertIsNone(self.find())
        entry.write_text(original + "x" * 9000)
        self.assertIsNone(self.find())

    def test_missing_external_or_experience_only_evidence_is_rejected(self):
        for evidence in (
            "[缺失](../worklogs/缺失.md)",
            "[外部](https://example.com/proof.md)",
            "[自身](卸载验证.md)",
            "[索引](index.md)",
            "只有一句没有链接的声明",
            "[有效](../worklogs/2026-11-06-卸载验证.md) [外部](https://example.com/proof.md)",
        ):
            with self.subTest(evidence=evidence):
                self.experience(evidence=evidence)
                self.assertIsNone(self.find())

    def test_external_source_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            outside = Path(directory) / "outside.md"
            outside.write_text("外部证据")
            self.worklog.unlink()
            self.worklog.symlink_to(outside)
            self.experience()
            self.assertIsNone(self.find())

    def test_external_experience_symlink_is_rejected(self):
        entry = self.experience()
        with tempfile.TemporaryDirectory() as directory:
            outside = Path(directory) / "outside.md"
            outside.write_text(entry.read_text())
            entry.unlink()
            entry.symlink_to(outside)
            self.assertIsNone(self.find())

    def test_nested_or_unindexed_experience_is_not_scanned(self):
        entry = self.experience()
        self.index.write_text("# 经验索引\n")
        self.assertIsNone(self.find())
        nested = self.evolution / "nested"
        nested.mkdir()
        entry.rename(nested / entry.name)
        self.index.write_text("# 经验索引\n- [嵌套](nested/卸载验证.md)\n")
        self.assertIsNone(self.find())

    def test_replaced_index_section_is_not_scanned(self):
        self.index.write_text("# 经验索引\n## 已替代经验\n")
        self.experience()
        self.assertIsNone(self.find())

    def test_index_byte_and_candidate_limits(self):
        for number in range(PREFLIGHT.MAX_CANDIDATES):
            self.experience(f"旧{number}", selector="uninstall-skill | zcode | project")
        self.experience("超出候选预算")
        self.assertIsNone(self.find())
        self.index.write_text("# 索引\n" + "x" * PREFLIGHT.INDEX_BYTES + "\n- [超出](超出候选预算.md)\n")
        self.assertIsNone(self.find())

    def test_no_store_is_quiet_and_does_not_create_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                rc = PREFLIGHT.main(["--root", str(root), "--action", "uninstall-skill",
                                     "--host", "opencode", "--scope", "project"])
            self.assertEqual(rc, 0)
            self.assertEqual(stream.getvalue(), "")
            self.assertEqual(list(root.iterdir()), [])

    def test_invalid_config_legacy_or_ambiguous_store_is_skipped(self):
        self.experience()
        config = self.root / PREFLIGHT.probe.CONFIG_FILE
        config.write_text("invalid JSON")
        # Discovery takes precedence over config in the existing probe, so a
        # recognized store still works and no alternate path is inferred.
        self.assertIsNotNone(self.find())
        config.unlink()
        legacy = self.root / "docs/memory-keeper.md"
        legacy.write_text("# 旧版记忆\n")
        self.assertIsNone(self.find())
        legacy.unlink()
        other = self.root / "context-keeper"
        other.mkdir()
        (other / "memory-keeper.md").write_text("# 另一个库\n")
        self.assertIsNone(self.find())
        self.assertIsNotNone(self.find(store_dir="docs/context-keeper"))

    def test_external_store_config_and_index_symlinks_are_rejected(self):
        self.experience()
        with tempfile.TemporaryDirectory() as directory:
            outside = Path(directory)
            self.assertIsNone(self.find(store_dir=str(outside)))
            external_index = outside / "index.md"
            external_index.write_text(self.index.read_text())
            self.index.unlink()
            self.index.symlink_to(external_index)
            self.assertIsNone(self.find())
        self.index.unlink()
        self.index.write_text("# 经验索引\n- [有效](卸载验证.md)\n")
        config = self.root / PREFLIGHT.probe.CONFIG_FILE
        config.symlink_to(self.index)
        self.assertIsNone(self.find())

    def test_cli_emits_one_json_and_never_executes_suggested_action(self):
        entry = self.experience()
        sentinel = self.root / "should-not-exist"
        original = entry.read_text()
        entry.write_text(original.replace("核对项目既有的另一宿主加载检查是否仍适用", f"touch '{sentinel}'"))
        before = self.snapshot()
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(self.root), "--action", "uninstall-skill",
             "--host", "opencode", "--scope", "project"],
            text=True, capture_output=True, check=True,
        )
        self.assertEqual(json.loads(result.stdout)["id"], "CK-001")
        self.assertEqual(result.stderr, "")
        self.assertFalse(sentinel.exists())
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
