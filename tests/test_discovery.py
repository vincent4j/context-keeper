import json
import tempfile
import unittest
from pathlib import Path

from test_context_keeper_probe import IsolatedProbeTestCase, PROBE, _call, _write_valid_context


def _make_store(path: Path, label: str = "发现测试") -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "worklogs").mkdir(exist_ok=True)
    (path / "evolution").mkdir(exist_ok=True)
    (path / "evolution" / "index.md").write_text("# 自我进化索引\n\n## 有效经验\n\n- 暂无\n", encoding="utf-8")
    (path / "worklogs" / "2026-09-17-测试.md").write_text(
        "<!-- context-keeper: session-id=test-session -->\n"
        "# 测试\n\n## 快速摘要（用于下次对话）\n\n**类型：** feature | 项目：测试\n**完成：** "
        + label + "\n**下一步：** 无\n**文件：** 无\n",
        encoding="utf-8",
    )
    (path / "memory-keeper.md").write_text(
        "# 项目记忆索引\n\n## 主题摘要（按类型）\n\n- **feature：** " + label + "。\n\n---\n\n"
        "## 进化经验入口\n\n- [进化经验索引](evolution/index.md)\n\n## 时间线（最新在前）\n\n"
        "## 2026-09-17 - 测试 `feature`\n- **任务：** " + label
        + "\n- **详见：** [worklogs/2026-09-17-测试.md](worklogs/2026-09-17-测试.md)\n",
        encoding="utf-8",
    )


class DiscoveryTests(IsolatedProbeTestCase):
    def test_custom_store_history_is_protected_by_both_entry_points(self):
        for entry in ("record-path", "record-guard"):
            for remove in (False, True):
                with self.subTest(entry=entry, remove=remove), tempfile.TemporaryDirectory() as d:
                    root = Path(d)
                    _make_store(root / "docs/context-keeper", "默认库")
                    store = root / "notes/history"
                    _make_store(store, "自定义库")
                    old = store / "worklogs/2026-09-17-测试.md"
                    current = store / "worklogs/2026-09-22-本轮.md"
                    current.write_text("<!-- context-keeper: session-id=new -->\n# 本轮\n")
                    extra = (("--kind", "worklog", "--title", "本轮") if entry == "record-path"
                             else ("--path", str(current)))
                    rc, out = _call(entry, "--root", d, "--store-dir", "notes/history",
                                    "--session-id", "new", *extra)
                    self.assertEqual(rc, 0, out)
                    if remove:
                        old.unlink()
                    else:
                        old.write_text("改写旧会话")
                    rc, out = _call("save-report", "--root", d, "--store-dir", "notes/history",
                                    "--worklog", str(current), "--session-id", "new")
                    self.assertEqual(rc, 2, out)
                    self.assertIn("历史记录被改写或删除", out)

    def test_baselines_are_separate_for_stores_in_the_same_session(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for location in ("context-keeper", "docs/context-keeper"):
                _make_store(root / location)
                rc, out = _call("record-path", "--root", d, "--store-dir", location,
                                "--kind", "worklog", "--title", "本轮", "--session-id", "new")
                self.assertEqual(rc, 0, out)
            first = PROBE._baseline_path(root, "new", "context-keeper")
            second = PROBE._baseline_path(root, "new", "docs/context-keeper")
            self.assertNotEqual(first, second)
            self.assertEqual(first, PROBE._baseline_path(root, "new", str(root / "context-keeper")))
            (root / "context-keeper/worklogs/2026-09-17-测试.md").unlink()
            self.assertTrue(PROBE._check_baseline(root, "new", "context-keeper"))
            self.assertEqual(PROBE._check_baseline(root, "new", "docs/context-keeper"), [])

    def test_docs_location_is_discovered_from_repo_root(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _make_store(root / "docs" / "context-keeper")
            rc, out = _call("resume", "--root", d)
            self.assertEqual(rc, 0, out)
            self.assertIn("发现测试", out)
            rc, out = _call("search", "--root", d, "--query", "发现")
            self.assertEqual(rc, 0, out)
            self.assertIn("命中", out)

    def test_record_path_writes_into_discovered_store_without_second_store(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _make_store(root / "docs" / "context-keeper")
            rc, out = _call("record-path", "--root", d, "--kind", "worklog", "--title", "新记录", "--session-id", "s1")
            self.assertEqual(rc, 0, out)
            self.assertTrue((root / out.strip()).is_file())
            self.assertTrue(out.strip().startswith("docs/context-keeper/"))
            self.assertFalse((root / "context-keeper").exists())

    def test_root_location_still_works(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _make_store(root / "context-keeper")
            rc, out = _call("resume", "--root", d)
            self.assertEqual(rc, 0, out)
            self.assertIn("发现测试", out)

    def test_ambiguous_stores_raise_clear_error(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _make_store(root / "context-keeper")
            _make_store(root / "docs" / "context-keeper")
            rc, out = _call("resume", "--root", d)
            self.assertEqual(rc, 2, out)
            self.assertIn("多个记录库", out)

    def test_ambiguity_can_be_resolved_by_store_dir_on_any_command(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _make_store(root / "context-keeper", "根目录内容")
            _make_store(root / "docs" / "context-keeper", "docs 内容")
            rc, out = _call("resume", "--root", d, "--store-dir", "context-keeper")
            self.assertEqual(rc, 0, out)
            self.assertIn("根目录内容", out)
            self.assertNotIn("docs 内容", out)
            rc, out = _call("search", "--root", d, "--store-dir", "docs/context-keeper", "--query", "docs")
            self.assertEqual(rc, 0, out)
            self.assertIn("docs 内容", out)

    def test_read_commands_accept_any_custom_store_dir(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _make_store(root / "notes" / "history", "自定义位置")
            for argv in (
                ("resume", "--root", d, "--store-dir", "notes/history"),
                ("search", "--root", d, "--store-dir", "notes/history", "--query", "自定义"),
                ("coverage", "--root", d, "--store-dir", "notes/history"),
            ):
                rc, out = _call(*argv)
                self.assertEqual(rc, 0, out)
            rc, out = _call("record-path", "--root", d, "--store-dir", "notes/history",
                            "--kind", "worklog", "--title", "新记录", "--session-id", "s1")
            self.assertEqual(rc, 0, out)
            self.assertTrue(out.strip().startswith("notes/history/"))

    def test_empty_directory_is_not_discovered(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "docs" / "context-keeper").mkdir(parents=True)
            rc, out = _call("resume", "--root", d)
            self.assertEqual(rc, 0, out)
            self.assertIn("未找到", out)

    def test_no_store_falls_back_to_default_and_legacy_still_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            rc, out = _call("resume", "--root", d)
            self.assertEqual(rc, 0, out)
            _write_valid_context(root, legacy=True)
            rc, out = _call("resume", "--root", d)
            self.assertEqual(rc, 3, out)
            self.assertIn("需要迁移", out)

    def test_json_fallback_still_works_for_custom_location(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _make_store(root / "notes" / "history")
            (root / "context-keeper.json").write_text(
                json.dumps({"directory": "notes/history", "schema_version": 2}), encoding="utf-8"
            )
            rc, out = _call("resume", "--root", d)
            self.assertEqual(rc, 0, out)
            self.assertIn("发现测试", out)

    def test_init_into_candidates_writes_no_json_and_custom_still_writes(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            rc, out = _call("init", "--root", d, "--store-dir", "docs/context-keeper", "--approved")
            self.assertEqual(rc, 0, out)
            self.assertFalse((root / "context-keeper.json").exists())
            self.assertTrue((root / "docs" / "context-keeper" / "memory-keeper.md").is_file())
            rc, out = _call("init", "--root", d, "--store-dir", "notes/history", "--migrate", "--approved")
            self.assertEqual(rc, 0, out)
            config = json.loads((root / "context-keeper.json").read_text())
            self.assertEqual(config["directory"], "notes/history")

    def test_migrate_accepts_docs_context_keeper_target(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            old = _write_valid_context(root, legacy=True)
            rc, out = _call("migrate", "--root", d, "--store-dir", "docs/context-keeper", "--approved")
            self.assertEqual(rc, 0, out)
            self.assertTrue((root / "docs" / "context-keeper" / "worklogs" / old.name).is_file())
            self.assertFalse((root / "context-keeper.json").exists())
            rc, out = _call("resume", "--root", d)
            self.assertEqual(rc, 0, out)


if __name__ == "__main__":
    unittest.main()
