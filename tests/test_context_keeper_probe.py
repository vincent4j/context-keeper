from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).parents[1] / "scripts" / "context_keeper_probe.py"
SPEC = importlib.util.spec_from_file_location("context_keeper_probe", SCRIPT)
assert SPEC and SPEC.loader
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)


class IsolatedProbeTestCase(unittest.TestCase):
    """Keep caches, user experience and session databases outside the real home."""

    def setUp(self):
        super().setUp()
        temporary = tempfile.TemporaryDirectory(prefix="context-keeper-test-")
        self.addCleanup(temporary.cleanup)
        self.test_home = Path(temporary.name)
        home_patch = patch.object(Path, "home", return_value=self.test_home)
        home_patch.start()
        self.addCleanup(home_patch.stop)


def _call(*args: str) -> tuple[int, str]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        result = PROBE.main(list(args))
    return result, stream.getvalue()


def _experience(title: str = "耗时分析", identifier: str = "CK-001", status: str = "已验证") -> str:
    return f"""# {title}

- **编号：** {identifier}
- **状态：** {status}
- **触发条件：** 再次分析生成耗时
- **已知事实：** 生成后整体处理较慢
- **证据位置：** worklogs/2026-08-17-test.md
- **建议动作：** 先检查已有计时
- **适用范围：** 当前生产流程
"""


def _write_valid_context(root: Path, *, legacy: bool = False, evolution: bool = False) -> Path:
    if legacy:
        worklog = root / "docs" / "worklog" / "2026-08-17-test.md"
        memory = root / "docs" / "memory-keeper.md"
        link = "worklog/2026-08-17-test.md"
    else:
        worklog = root / "docs" / "context-keeper" / "worklogs" / "2026-08-17-test.md"
        memory = root / "docs" / "context-keeper" / "memory-keeper.md"
        link = "worklogs/2026-08-17-test.md"
    worklog.parent.mkdir(parents=True)
    extra = """
## 自我进化

- **已沉淀：** 分析历史结论时必须保留证据位置，详见[耗时分析](../evolution/耗时分析.md)。
- **本次复用：** 复用了此前的耗时记录，没有猜测未测量的子阶段，详见[耗时分析](../evolution/耗时分析.md)。
""" if evolution else ""
    worklog.write_text(
        f"""<!-- context-keeper: session-id=session-a -->
# Test

## 给用户看的增量认知

- **盲点：** 把 Git 结果当作对话交付，会让真正有价值的复盘消失。
  - **影响：** 后续即使文件保存完整，用户仍无法获得增量认知。
- **决策影响：** 用户报告与供下次续接的快速摘要分离。
  - **影响：** 用户只看到盲点和隐患，不被已知进度淹没。
{extra}
## 快速摘要（用于下次对话）

**类型：** bugfix | 项目：Demo
**完成：** 修复保存输出遗漏。
**问题：** 推送后只报告 Git 结果。
**经验：** 增量认知必须作为完成门禁。
**下一步：** 观察下一次真实保存。
**文件：** SKILL.md
""",
        encoding="utf-8",
    )
    memory.parent.mkdir(parents=True, exist_ok=True)
    evolution_link = "\n## 进化经验入口\n\n- [进化经验索引](evolution/index.md)\n" if not legacy else ""
    memory.write_text(
        f"""# 项目记忆索引

## 未完成事项

- 完成真实保存复测；状态：进行中；触发：下次保存；完成：报告通过；证据：测试输出。
{evolution_link}
## 时间线（最新在前）

## 2026-08-17 - Test `bugfix`
- **任务：** 修复保存输出遗漏。
- **规则候选：** 保存时最终回复必须包含增量认知。
- **详见：** [{link}]({link})
""",
        encoding="utf-8",
    )
    if evolution and not legacy:
        evolution_file = root / "docs" / "context-keeper" / "evolution" / "耗时分析.md"
        evolution_file.parent.mkdir(parents=True, exist_ok=True)
        evolution_file.write_text(_experience(), encoding="utf-8")
        (evolution_file.parent / "index.md").write_text("# 索引\n\n- [耗时分析](耗时分析.md)\n", encoding="utf-8")
    elif not legacy:
        evolution_dir = root / "docs" / "context-keeper" / "evolution"
        evolution_dir.mkdir(parents=True, exist_ok=True)
        (evolution_dir / "index.md").write_text("# 索引\n", encoding="utf-8")
    if evolution and not legacy:
        with memory.open("a", encoding="utf-8") as handle:
            handle.write("\n## 主题摘要（按类型）\n- 当前采用[经验](evolution/耗时分析.md)，来源已关联。\n")
    PROBE._capture_baseline(root, "session-a")
    return worklog


def _save(root: Path, worklog: Path, *, legacy: bool = False) -> tuple[int, str]:
    args = ["save-report", "--root", str(root), "--worklog", str(worklog)]
    if not legacy:
        args.extend(["--session-id", "session-a"])
    return _call(*args)


class InitTests(IsolatedProbeTestCase):
    def test_default_init_asks_for_approval_and_does_not_create(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result, output = _call("init", "--root", str(root))
            self.assertEqual(result, 5)
            self.assertIn("确认请加 --approved", output)
            self.assertIn("改用其他位置", output)
            self.assertFalse((root / "docs" / "context-keeper").exists())
            self.assertFalse((root / "context-keeper.json").exists())

    def test_init_reports_existing_store_as_ready(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "docs" / "context-keeper" / "plans").mkdir(parents=True)
            (root / "docs" / "context-keeper" / "memory-keeper.md").write_text("# 项目记忆\n", encoding="utf-8")
            result, output = _call("init", "--root", str(root))
            self.assertEqual(result, 0)
            self.assertIn("已就绪", output)
            self.assertIn("docs/context-keeper", output)

    def test_init_store_dir_alone_asks_for_approval(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result, output = _call("init", "--root", str(root), "--store-dir", "notes/history")
            self.assertEqual(result, 5)
            self.assertIn("来自 --store-dir", output)
            self.assertIn("确认请加 --approved", output)
            self.assertFalse((root / "notes" / "history").exists())

    def test_initializes_default_visible_directory_and_index_link(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result, output = _call("init", "--root", str(root), "--approved")
            self.assertEqual(result, 0)
            self.assertIn("默认记录位置：docs/context-keeper", output)
            self.assertTrue((root / "docs" / "context-keeper" / "plans").is_dir())
            self.assertTrue((root / "docs" / "context-keeper" / "worklogs").is_dir())
            self.assertTrue((root / "docs" / "context-keeper" / "evolution" / "index.md").is_file())
            self.assertIn("evolution/index.md", (root / "docs" / "context-keeper" / "memory-keeper.md").read_text())

    def test_remembers_custom_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result, _ = _call("init", "--root", str(root), "--store-dir", "project-notes/context", "--approved")
            self.assertEqual(result, 0)
            config = json.loads((root / "context-keeper.json").read_text())
            self.assertEqual(config["directory"], "project-notes/context")

    def test_switch_requires_explicit_migration_and_can_return_to_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _call("init", "--root", str(root), "--store-dir", "project-notes/context", "--approved")
            blocked, output = _call("init", "--root", str(root), "--store-dir", "context-keeper")
            self.assertEqual(blocked, 2)
            self.assertIn("--migrate", output)
            moved, output = _call("init", "--root", str(root), "--store-dir", "context-keeper", "--migrate", "--approved")
            self.assertEqual(moved, 0)
            self.assertIn("已迁移记录", output)
            self.assertFalse((root / "context-keeper.json").exists())
            self.assertFalse((root / "project-notes" / "context").exists())


class RecordBoundaryTests(IsolatedProbeTestCase):
    def test_record_path_creates_session_owned_file_and_other_session_appends(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _call("init", "--root", str(root), "--approved")
            args = ("record-path", "--root", str(root), "--kind", "plan", "--title", "上下文优化需求", "--date", "2026-09-16")
            _, first = _call(*args, "--session-id", "session-a")
            first_path = root / first.strip()
            self.assertIn("session-id=session-a", first_path.read_text())
            _, same = _call(*args, "--session-id", "session-a")
            _, other = _call(*args, "--session-id", "session-b")
            self.assertEqual(first.strip(), same.strip())
            self.assertTrue(other.strip().endswith("-2.md"))
            self.assertIn("session-id=session-b", (root / other.strip()).read_text())

    def test_guard_blocks_cross_session_write(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _call("init", "--root", str(root), "--approved")
            _, path = _call("record-path", "--root", str(root), "--kind", "worklog", "--title", "测试", "--session-id", "a")
            ok, _ = _call("record-guard", "--root", str(root), "--path", path.strip(), "--session-id", "a")
            blocked, output = _call("record-guard", "--root", str(root), "--path", path.strip(), "--session-id", "b")
            self.assertEqual(ok, 0)
            self.assertEqual(blocked, 2)
            self.assertIn("跨会话修改已阻止", output)


class StoreCreationGateTests(IsolatedProbeTestCase):
    def test_record_path_refuses_uninitialized_store(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rc, output = _call("record-path", "--root", str(root), "--kind", "worklog", "--title", "测试", "--session-id", "a")
            self.assertEqual(rc, 2)
            self.assertIn("记录库尚未初始化", output)
            self.assertFalse((root / "docs" / "context-keeper").exists())


class TokenBoundaryTests(IsolatedProbeTestCase):
    def _store(self) -> Path:
        temporary = tempfile.TemporaryDirectory(prefix="context-keeper-token-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        _call("init", "--root", str(root), "--approved")
        return root

    def test_quick_summary_default_window_is_tight(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "worklog.md"
            filler = "\n".join(f"填充行{i}" for i in range(6))
            path.write_text(
                "# 主题\n\n## 快速摘要（用于下次对话）\n\n**类型：** feature\n**完成：** 完成\n"
                + filler + "\n**下一步：** 继续\n",
                encoding="utf-8",
            )
            default = PROBE._quick_summary(path)
            self.assertEqual(default, ["**类型：** feature", "**完成：** 完成"])
            detailed = PROBE._quick_summary(path, details=True)
            self.assertIn("**下一步：** 继续", detailed)

    def test_status_output_is_capped(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            subprocess.run(["git", "-C", str(root), "init"], check=True, capture_output=True)
            for index in range(40):
                (root / f"f{index}.txt").write_text(str(index), encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t",
                            "commit", "-m", "init"], check=True, capture_output=True)
            for index in range(40):
                (root / f"f{index}.txt").write_text("changed", encoding="utf-8")
            rc, output = _call("status", "--root", str(root))
            self.assertEqual(rc, 0)
            self.assertIn("其余 10 行省略", output)
            # 未封顶应为 3 个标题 + 41 + 40 + 40 = 124 行；封顶后三个区块各 ≤31 行
            self.assertLessEqual(len(output.splitlines()), 100)

    def test_search_dedups_linked_records(self):
        root = self._store()
        linked = root / "docs/context-keeper/worklogs/2026-09-01-验收.md"
        unlinked = root / "docs/context-keeper/worklogs/2026-09-02-另一主题.md"
        linked.parent.mkdir(parents=True, exist_ok=True)
        linked.write_text("<!-- context-keeper: session-id=a -->\n# 验收\n正文提到关键词\n", encoding="utf-8")
        unlinked.write_text("<!-- context-keeper: session-id=b -->\n# 其他\n这里也有关键词\n", encoding="utf-8")
        memory = root / "docs/context-keeper/memory-keeper.md"
        memory.write_text(
            "# 索引\n\n## 时间线（最新在前）\n\n"
            "## 2026-09-01 - 验收 `feature`\n- **任务：** 关键词任务\n"
            "- **详见：** [日志](worklogs/2026-09-01-验收.md)\n\n---\n",
            encoding="utf-8",
        )
        rc, output = _call("search", "--root", str(root), "--query", "关键词")
        self.assertEqual(rc, 0)
        self.assertIn("命中 2 条记录", output)
        self.assertIn("另一主题", output)
        self.assertNotIn("2026-09-01-验收", output)

    def test_compact_previews_then_archives_with_links(self):
        root = self._store()
        memory = root / "docs/context-keeper/memory-keeper.md"
        blocks = []
        for index in range(1, 19):
            day = f"2026-09-{index:02d}"
            blocks.append(f"## {day} - 主题{index} `feature`\n- **任务：** 任务{index}\n- **详见：** [日志](worklogs/{day}-主题{index}.md)\n")
        memory.write_text(
            "# 项目记忆索引\n\n## 未完成事项\n\n- 暂无\n\n## 时间线（最新在前）\n\n"
            + "\n".join(reversed(blocks)) + "\n---\n",
            encoding="utf-8",
        )
        rc, output = _call("compact", "--root", str(root))
        self.assertEqual(rc, PROBE.RC_NEEDS_CONFIRMATION)
        self.assertIn("保留最近 15 条", output)
        self.assertIn("归档 3 条", output)
        rc, output = _call("compact", "--root", str(root), "--approved")
        self.assertEqual(rc, 0)
        text = memory.read_text(encoding="utf-8")
        self.assertIn("## 时间线归档", text)
        self.assertIn("(worklogs/2026-09-01-主题1.md)", text)
        self.assertEqual(len(PROBE._memory_entries(memory)), 15)
        rc, output = _call("compact", "--root", str(root))
        self.assertEqual(rc, 0)
        self.assertIn("无需压缩", output)

    def test_compact_noop_below_threshold(self):
        root = self._store()
        rc, output = _call("compact", "--root", str(root))
        self.assertEqual(rc, 0)
        self.assertIn("无需压缩", output)


class CompactReminderTests(IsolatedProbeTestCase):
    def _store(self) -> Path:
        temporary = tempfile.TemporaryDirectory(prefix="context-keeper-remind-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        _call("init", "--root", str(root), "--approved")
        return root

    def test_compact_level_ladder(self):
        self.assertIsNone(PROBE._compact_level(15000, 0))
        self.assertEqual(PROBE._compact_level(25000, 0), 20480)
        self.assertEqual(PROBE._compact_level(31000, 0), 30720)
        self.assertIsNone(PROBE._compact_level(31000, 30720))
        self.assertEqual(PROBE._compact_level(45000, 30720), 40960)
        self.assertEqual(PROBE._compact_level(210 * 1024, 0), 215040)
        self.assertIsNone(PROBE._compact_level(210 * 1024, 215040))
        self.assertEqual(PROBE._compact_level(221 * 1024, 215040), 225280)

    def test_save_report_reminds_then_snooze_then_next_threshold(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            worklog = _write_valid_context(root)
            memory = root / "docs/context-keeper/memory-keeper.md"
            with memory.open("a", encoding="utf-8") as handle:
                handle.write("x" * 21000 + "\n")
            rc, output = _save(root, worklog)
            self.assertEqual(rc, 0)
            self.assertIn("体积提醒", output)
            self.assertIn("20KB 阈值", output)
            self.assertIn("回复 1 或 2", output)

            rc, output = _call("compact", "--root", str(root), "--snooze")
            self.assertEqual(rc, 0)
            self.assertIn("增长到约 30KB 后会再次提醒", output)
            rc, output = _save(root, worklog)
            self.assertEqual(rc, 0)
            self.assertNotIn("体积提醒", output)

            with memory.open("a", encoding="utf-8") as handle:
                handle.write("y" * 21000 + "\n")
            rc, output = _save(root, worklog)
            self.assertEqual(rc, 0)
            self.assertIn("40KB 阈值", output)

    def test_compact_settles_state_at_new_size(self):
        root = self._store()
        memory = root / "docs/context-keeper/memory-keeper.md"
        blocks = []
        for index in range(1, 19):
            day = f"2026-09-{index:02d}"
            blocks.append(f"## {day} - 主题{index} `feature`\n- **任务：** {'任务内容' * 20}\n- **详见：** [日志](worklogs/{day}-主题{index}.md)\n")
        memory.write_text(
            "# 项目记忆索引\n\n## 未完成事项\n\n- 暂无\n\n## 时间线（最新在前）\n\n"
            + "\n".join(reversed(blocks)) + "\n---\n",
            encoding="utf-8",
        )
        _call("compact", "--root", str(root), "--approved")
        settled = PROBE._read_compact_settled(PROBE._compact_state_path(root))
        self.assertEqual(settled, memory.stat().st_size)
        self.assertIsNone(PROBE._compact_level(memory.stat().st_size, settled))


class ResumeAndSearchTests(IsolatedProbeTestCase):
    def test_resume_defaults_to_five_entries_and_three_plus_two(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _call("init", "--root", str(root), "--approved")
            memory = root / "docs" / "context-keeper" / "memory-keeper.md"
            entries = []
            for index, kind in enumerate(("research", "research", "research", "bugfix", "feature"), 1):
                entries.append(f"## 2026-09-{20-index:02d} - Item {index} `{kind}`\n- **任务：** task {index}\n- **关键经验：** lesson {index}\n")
            memory.write_text("# 项目记忆索引\n\n## 时间线（最新在前）\n\n" + "\n".join(entries))
            result, output = _call("resume", "--root", str(root), "--kind", "research")
            self.assertEqual(result, 0)
            self.assertEqual(output.count("- 2026-09-"), 5)

    def test_resume_query_filters_pending_and_experience(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _call("init", "--root", str(root), "--approved")
            memory = root / "docs" / "context-keeper" / "memory-keeper.md"
            memory.write_text("""# 索引

## 未完成事项
- 整体复盘；状态：进行中；触发：整组验收；完成：核账完成；证据：报告。
- 邮件发送；状态：进行中；触发：批准；完成：已发送；证据：邮件。

## 时间线（最新在前）
## 2026-09-16 - 复盘 `feature`
- **任务：** 完成整体复盘
- **关键经验：** 单品完成不等于整组完成
## 2026-09-15 - 邮件 `feature`
- **任务：** 发送邮件
""")
            result, output = _call("resume", "--root", str(root), "--query", "整体|整组")
            self.assertEqual(result, 0)
            self.assertIn("整体复盘", output)
            self.assertNotIn("邮件发送", output)

    def test_resume_uses_bounded_fallback_when_summary_is_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _call("init", "--root", str(root), "--approved")
            worklog = root / "docs" / "context-keeper" / "worklogs" / "2026-09-16-缺摘要.md"
            worklog.write_text("<!-- context-keeper: session-id=a -->\n# 标题\n\n这里记录了集中审核的真实耗时。\n")
            result, output = _call("resume", "--root", str(root))
            self.assertEqual(result, 0)
            self.assertIn("有限提取", output)

    def test_search_falls_back_to_unindexed_plan_and_worklog(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _call("init", "--root", str(root), "--approved")
            (root / "docs/context-keeper/plans/2026-09-16-整体复盘.md").write_text("用户要求整体核账。")
            (root / "docs/context-keeper/worklogs/2026-09-16-耗时.md").write_text("集中审核耗时 9 分 16 秒。")
            _, plans = _call("search", "--root", str(root), "--query", "整体核账")
            _, logs = _call("search", "--root", str(root), "--query", "9 分 16 秒")
            self.assertIn("[需求与计划]", plans)
            self.assertIn("[工作日志]", logs)

    def test_search_excludes_replaced_and_caps_evolution_at_three(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _call("init", "--root", str(root), "--approved")
            evolution = root / "docs/context-keeper/evolution"
            (evolution / "旧经验.md").write_text(_experience("旧经验", "CK-000", "已替代"))
            for index in range(4):
                text = _experience(f"有效经验{index}", f"CK-{index + 1:03d}").replace("生成耗时", "共同触发词")
                (evolution / f"有效经验{index}.md").write_text(text)
            result, output = _call("search", "--root", str(root), "--query", "共同触发词|再次分析")
            self.assertEqual(result, 0)
            self.assertNotIn("旧经验", output)
            self.assertEqual(output.count("[进化经验]"), 3)

    def test_search_reads_approved_user_level_experience(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            user = Path(temp_dir) / "user-evolution"
            root.mkdir()
            _call("init", "--root", str(root), "--approved")
            user.mkdir()
            (user / "通用经验.md").write_text(_experience("通用经验").replace("生成耗时", "跨项目线索"))
            result, output = _call("search", "--root", str(root), "--query", "跨项目线索", "--user-evolution-dir", str(user))
            self.assertEqual(result, 0)
            self.assertIn("用户级", output)

    def test_zero_hit_does_not_claim_history_never_existed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _call("init", "--root", str(root), "--approved")
            _, output = _call("search", "--root", str(root), "--query", "不存在的关键词")
            self.assertIn("不代表历史上从未发生", output)


class RawHistoryTests(IsolatedProbeTestCase):
    def test_finds_codex_original_for_matching_project_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            project = base / "project"
            project.mkdir()
            history = base / "sessions"
            history.mkdir()
            rows = [
                {"type": "session_meta", "payload": {"cwd": str(project)}},
                {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "整体审核耗时 9 分 16 秒"}]}},
            ]
            (history / "session.jsonl").write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows))
            result, output = _call("history-search", "--root", str(project), "--query", "9 分 16 秒", "--agent", "codex", "--codex-history", str(history))
            self.assertEqual(result, 0)
            self.assertIn("[Codex 原文]", output)
            self.assertIn("9 分 16 秒", output)

    def test_finds_claude_original_for_matching_project(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            project = base / "project"
            project.mkdir()
            history = base / "projects"
            history.mkdir()
            row = {
                "type": "assistant",
                "cwd": str(project),
                "message": {"role": "assistant", "content": [{"type": "text", "text": "历史事实来自原始记录"}]},
            }
            (history / "session.jsonl").write_text(json.dumps(row, ensure_ascii=False))
            result, output = _call("history-search", "--root", str(project), "--query", "原始记录", "--agent", "claude", "--claude-history", str(history))
            self.assertEqual(result, 0)
            self.assertIn("[Claude Code 原文]", output)

    def test_raw_history_zero_hit_keeps_fact_boundary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            history = root / "empty"
            history.mkdir()
            _, output = _call("history-search", "--root", str(root), "--query", "missing", "--codex-history", str(history), "--claude-history", str(history))
            self.assertIn("不代表历史上从未发生", output)


class EvolutionPromotionTests(IsolatedProbeTestCase):
    def test_requires_approval_and_promotes_valid_experience(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            user = Path(temp_dir) / "user"
            root.mkdir()
            _call("init", "--root", str(root), "--approved")
            source = root / "docs/context-keeper/evolution/耗时分析.md"
            source.write_text(_experience())
            blocked, _ = _call("promote-evolution", "--root", str(root), "--source", str(source), "--user-evolution-dir", str(user))
            ok, output = _call("promote-evolution", "--root", str(root), "--source", str(source), "--user-evolution-dir", str(user), "--approved")
            self.assertEqual(blocked, 2)
            self.assertEqual(ok, 0)
            self.assertTrue((user / "耗时分析.md").is_file())
            self.assertIn("已晋升", output)


class CoverageTests(IsolatedProbeTestCase):
    def test_default_output_is_compact_and_details_are_optional(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _call("init", "--root", str(root), "--approved")
            worklog = root / "docs/context-keeper/worklogs/2026-09-16-遗漏.md"
            worklog.write_text("# 未被索引\n")
            result, output = _call("coverage", "--root", str(root))
            self.assertEqual(result, 1)
            self.assertEqual(len(output.splitlines()), 1)
            self.assertIn("worklogs_unindexed=1", output)
            _, details = _call("coverage", "--root", str(root), "--details")
            self.assertIn("2026-09-16-遗漏.md", details)

    def test_detects_invalid_experience_duplicate_id_broken_link_and_pending(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _call("init", "--root", str(root), "--approved")
            evolution = root / "docs/context-keeper/evolution"
            (evolution / "a.md").write_text(_experience("A", "CK-001"))
            (evolution / "b.md").write_text(_experience("B", "CK-001"))
            (evolution / "bad.md").write_text("# bad\n- **状态：** unknown\n")
            memory = root / "docs/context-keeper/memory-keeper.md"
            memory.write_text("# 索引\n\n## 未完成事项\n- 不完整事项\n\n[坏链接](missing.md)\n")
            result, output = _call("coverage", "--root", str(root), "--details")
            self.assertEqual(result, 1)
            self.assertIn("duplicate_ids=1", output)
            self.assertIn("broken_links=1", output)
            self.assertIn("pending_invalid=1", output)


class CurrentMemoryTests(IsolatedProbeTestCase):
    def context(self):
        temporary = tempfile.TemporaryDirectory(prefix="current-memory-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        log = _write_valid_context(root)
        return root, log, log.parent.parent / "memory-keeper.md"

    def add_current(self, memory, body):
        with memory.open("a", encoding="utf-8") as output:
            output.write("\n## 主题摘要（按类型）\n" + body + "\n")

    def test_resume_current_b_precedes_historical_a_and_filters_before_limit(self):
        root, log, memory = self.context()
        log.write_text(log.read_text().replace("修复保存输出遗漏。", "方案 A 当时有效。"))
        filler = "".join(f"- **其他主题{i}：** 不相关。\n" for i in range(8))
        self.add_current(memory, filler + "- **接口修复：** 方案 A 已失败，当前采用方案 B。\n  下一步：等待权限后验证。\n  来源：[日志](worklogs/" + log.name + ")。")
        result, output = _call("resume", "--root", str(root), "--query", "接口")
        self.assertEqual(result, 0, output)
        self.assertIn("方案 B", output)
        self.assertIn("等待权限", output)
        self.assertIn("来源：", output)
        self.assertNotIn("其他主题0", output)
        self.assertLess(output.index("方案 B"), output.index("方案 A 当时有效"))
        self.assertIn("首次记录快照，不代表当前状态", output)

    def test_multi_keyword_query_recalls_latest_contract_before_old_snapshot(self):
        root, log, memory = self.context()
        log.write_text(log.read_text().replace("修复保存输出遗漏。", "早期只保留编号，3 项测试通过。"))
        self.add_current(memory, "- **订单导入：** 当前空字符串抛出 ValueError，首尾空格原样保留，5 项测试通过。\n  来源：[日志](worklogs/" + log.name + ")。")
        memory.write_text(memory.read_text().replace("完成真实保存复测；状态：进行中；触发：下次保存；完成：报告通过；证据：测试输出。",
                                                    "真实样本验收；状态：未开始；触发：获得样本；完成：核验原文；证据：日志。"))
        for command in ("resume", "search"):
            with self.subTest(command=command):
                result, output = _call(command, "--root", str(root), "--query",
                                       "订单 编号 导入 空字符串 首尾空格 验收")
                self.assertEqual(result, 0, output)
                self.assertIn("当前空字符串抛出 ValueError", output)
                self.assertIn("首尾空格原样保留，5 项测试通过", output)
                self.assertNotIn("未找到相关当前主题", output)
                if command == "resume":
                    self.assertIn("真实样本验收", output)
                    self.assertLess(output.index("5 项测试通过"), output.index("3 项测试通过"))

    def test_keyword_queries_preserve_regex_and_do_not_widen_zero_hits(self):
        root, _, memory = self.context()
        self.add_current(memory, "- 订单 order_ids.py：保留原文。\n- 客户 customer_ids.py：保留原文。\n- 误匹配 order_idsXpy：不应命中点号文件名词项。")
        for command in ("resume", "search"):
            for query, present, absent in (
                ("  order_ids.py\t不存在的词  ", "订单 order_ids.py", "误匹配"),
                (r"^- (订单|客户)\b", "客户 customer_ids.py", "误匹配"),
                (r"订单 order_ids\.py", "订单 order_ids.py", "客户 customer_ids.py"),
                (r"订单.*保留|客户.*保留", "客户 customer_ids.py", "误匹配"),
                ("不存在甲 不存在乙", None, "保留原文"),
                ("  \t  ", None, "保留原文"),
            ):
                with self.subTest(command=command, query=query):
                    result, output = _call(command, "--root", str(root), "--query", query)
                    self.assertEqual(result, 0, output)
                    if present:
                        self.assertIn(present, output)
                    self.assertNotIn(absent, output)

    def test_search_requirement_only_section_keeps_continuation_and_cap(self):
        root, log, memory = self.context()
        with memory.open("a") as output:
            output.write("\n## 项目要求\n- 生产变更只允许预览。\n  下一步：取得批准再部署。\n  来源：[日志](worklogs/" + log.name + ")。\n")
        result, output = _call("search", "--root", str(root), "--query", "生产变更", "--entries", "1")
        self.assertEqual(result, 0, output)
        self.assertIn("命中 1 条记录", output)
        self.assertIn("[当前主题与要求]", output)
        self.assertIn("取得批准", output)
        self.assertIn("来源：", output)
        self.assertNotIn("[工作日志]", output)

    def test_no_matching_current_theme_does_not_show_irrelevant_theme(self):
        root, log, memory = self.context()
        self.add_current(memory, "- **邮件：** 已发送。")
        _, output = _call("resume", "--root", str(root), "--query", "接口")
        self.assertIn("未找到相关当前主题", output)
        self.assertNotIn("已发送", output)

    def test_long_current_item_is_bounded_but_keeps_source_and_next_step(self):
        root, log, memory = self.context()
        detail = "".join(f"  过程{i}：不应全部展开。\n" for i in range(100))
        self.add_current(memory, "- **接口：** 当前采用 B。\n" + detail + "  下一步：取得权限。\n  来源：[日志](worklogs/" + log.name + ")。")
        _, output = _call("resume", "--root", str(root), "--query", "接口")
        self.assertIn("仅显示有限内容", output)
        self.assertIn("取得权限", output)
        self.assertIn("来源：", output)
        self.assertNotIn("过程99", output)
        self.assertLess(len(output.splitlines()), 35)

    def test_query_keeps_late_matching_constraint_and_source_within_budget(self):
        root, log, memory = self.context()
        detail = "".join(f"  过程{i}：普通说明。\n" for i in range(10))
        self.add_current(memory, "- **发布：** 当前要求。\n" + detail + "  必须禁止自动发布，先征得明确批准。\n  下一步：等待批准。\n  来源：[日志](worklogs/" + log.name + ")。")
        for command in ("resume", "search"):
            with self.subTest(command=command):
                _, output = _call(command, "--root", str(root), "--query", "禁止自动发布")
                self.assertIn("必须禁止自动发布，先征得明确批准", output)
                self.assertIn("来源：", output)
                self.assertIn("下一步：等待批准", output)
                self.assertNotIn("过程5", output)
                self.assertLess(len(output.splitlines()), 35)

    def test_subheading_context_keeps_child_constraint_not_empty_heading(self):
        root, log, memory = self.context()
        self.add_current(memory, "### 接口约束\n- 禁止自动发布。\n  来源：[日志](worklogs/" + log.name + ")。\n### 其他约束\n- 忽略其他主题。")
        items = PROBE._current_memory_items(memory)
        self.assertEqual(len(items), 2)
        for command in ("resume", "search"):
            with self.subTest(command=command):
                _, output = _call(command, "--root", str(root), "--query", "接口约束")
                self.assertIn("接口约束", output)
                self.assertIn("禁止自动发布", output)
                self.assertIn("来源：", output)
                self.assertNotIn("忽略其他主题", output)

    def test_code_example_is_not_current_requirement(self):
        root, log, memory = self.context()
        with memory.open("a") as output:
            output.write("\n```markdown\n## 项目要求\n- 虚构关键词要求。\n```\n")
        self.assertEqual(PROBE._current_memory_items(memory), [])
        _, output = _call("search", "--root", str(root), "--query", "虚构关键词")
        self.assertNotIn("[当前主题与要求]", output)

    def test_nested_fence_examples_do_not_displace_real_requirements(self):
        for opening, inner, closing in (
            ("````markdown", "```markdown", "````"),
            ("~~~~markdown", "~~~markdown", "~~~~"),
            ("````markdown", "````not-a-closing-fence", "`````"),
            ("````markdown", "~~~markdown", "````"),
        ):
            with self.subTest(opening=opening, inner=inner):
                root, _, memory = self.context()
                with memory.open("a") as output:
                    output.write(
                        f"\n{opening}\n{inner}\n## 项目要求\n"
                        "- 示例中的虚构要求：自动部署生产。\n"
                        f"{inner.split()[0]}\n{closing}\n\n## 项目要求\n"
                        "- 真实要求：禁止自动部署。\n"
                    )
                self.assertEqual(PROBE._current_memory_items(memory),
                                 [("项目要求", "- 真实要求：禁止自动部署。")])
                for command in ("resume", "search"):
                    result, output = _call(command, "--root", str(root),
                                           "--query", "自动部署", "--entries", "1")
                    self.assertEqual(result, 0, output)
                    self.assertIn("真实要求：禁止自动部署", output)
                    self.assertNotIn("示例中的虚构要求", output)

    def test_save_no_experience_does_not_replay_old_log_feedback(self):
        root, log, memory = self.context()
        before = log.read_bytes()
        self.add_current(memory, "- **接口：** 已采用方案 B；来源：[日志](worklogs/" + log.name + ")。")
        result, output = _save(root, log)
        self.assertEqual(result, 0, output)
        self.assertIn("当前关联经验：0 份", output)
        self.assertNotIn("把 Git 结果当作对话交付", output)
        self.assertNotIn("**已沉淀：**", output)
        self.assertEqual(log.read_bytes(), before)

    def test_save_rejects_non_markdown_current_source(self):
        root, log, memory = self.context()
        self.add_current(memory, "- **接口：** 验证数据见[结果](missing.json)。")
        result, output = _save(root, log)
        self.assertEqual(result, 2, output)
        self.assertIn("来源链接失效", output)

    def test_save_rejects_broken_current_source(self):
        root, log, memory = self.context()
        self.add_current(memory, "- **接口：** 采用 B；来源：[缺失](worklogs/missing.md)。")
        result, output = _save(root, log)
        self.assertEqual(result, 2, output)
        self.assertIn("失效链接", output)

    def test_save_validates_only_directly_referenced_current_experience(self):
        root, log, memory = self.context()
        evo = log.parent.parent / "evolution"
        experience = evo / "接口.md"
        experience.write_text(_experience("接口", "CK-002").replace("worklogs/2026-08-17-test.md", "[日志](../worklogs/" + log.name + ")"))
        (evo / "index.md").write_text("# 索引\n- [接口](接口.md)\n")
        self.add_current(memory, "- **接口：** 采用[接口经验](evolution/接口.md)。")
        result, output = _save(root, log)
        self.assertEqual(result, 0, output)
        self.assertIn("当前关联经验：1 份", output)
        experience.write_text("# 接口\n")
        result, output = _save(root, log)
        self.assertEqual(result, 2, output)
        self.assertIn("字段不完整", output)

    def test_save_rejects_broken_experience_source_and_missing_index(self):
        root, log, memory = self.context()
        evo = log.parent.parent / "evolution"
        experience = evo / "接口.md"
        experience.write_text(_experience("接口", "CK-002").replace("worklogs/2026-08-17-test.md", "[缺失](../worklogs/missing.md)"))
        self.add_current(memory, "- **接口：** 采用[经验](evolution/接口.md)。")
        result, output = _save(root, log)
        self.assertEqual(result, 2, output)
        self.assertIn("来源链接失效", output)
        experience.write_text(_experience("接口", "CK-002"))
        result, output = _save(root, log)
        self.assertEqual(result, 2, output)
        self.assertIn("缺少索引入口", output)



class SaveReportTests(IsolatedProbeTestCase):
    def test_validates_current_experience_without_replaying_log_notice(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            worklog = _write_valid_context(root, evolution=True)
            result, output = _save(root, worklog)
            self.assertEqual(result, 0, output)
            self.assertIn("当前关联经验：1 份", output)
            self.assertNotIn("自我进化：", output)
            self.assertNotIn("分析历史结论时必须保留证据位置", output)

    def test_legacy_layout_requires_migration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            worklog = _write_valid_context(root, legacy=True)
            result, output = _save(root, worklog, legacy=True)
            self.assertEqual(result, 3, output)
            self.assertIn("需要迁移", output)

    def test_blocks_wrong_session_for_new_layout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            worklog = _write_valid_context(root)
            result, output = _call("save-report", "--root", str(root), "--worklog", str(worklog), "--session-id", "session-b")
            self.assertEqual(result, 2)
            self.assertIn("其他会话", output)

    def test_ignores_historical_notice_without_claiming_new_experience(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            worklog = _write_valid_context(root)
            text = worklog.read_text().replace("## 快速摘要", "## 自我进化\n\n- **已沉淀：** 旧日志中的判断。\n\n## 快速摘要")
            worklog.write_text(text)
            result, output = _save(root, worklog)
            self.assertEqual(result, 0, output)
            self.assertIn("当前关联经验：0 份", output)
            self.assertNotIn("旧日志中的判断", output)

    def test_blocks_incomplete_evolution_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            worklog = _write_valid_context(root, evolution=True)
            (root / "docs/context-keeper/evolution/耗时分析.md").write_text("# 不完整\n")
            result, output = _save(root, worklog)
            self.assertEqual(result, 2)
            self.assertIn("字段不完整", output)

    def test_blocks_evolution_growth_and_coverage_reports_same_reason(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            worklog = _write_valid_context(root, evolution=True)
            experience = root / "docs/context-keeper/evolution/耗时分析.md"
            text = _experience() + "\n" + "重复过程" * 600
            experience.write_text(text)
            result, output = _save(root, worklog)
            self.assertEqual(result, 2, output)
            self.assertIn("2000", output)
            self.assertNotIn("已保存上下文", output)
            self.assertEqual(experience.read_text(), text)
            result, output = _call("coverage", "--root", str(root), "--details")
            self.assertEqual(result, 1)
            self.assertIn("evolution_invalid=1", output)
            self.assertIn("2000", output)

    def test_blocks_dated_appendices_but_allows_date_in_evidence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            worklog = _write_valid_context(root, evolution=True)
            experience = root / "docs/context-keeper/evolution/耗时分析.md"
            for heading in ("## 2026-10-07 第一轮测试", "### 2026-10-07 第二轮纠正"):
                with self.subTest(heading=heading):
                    experience.write_text(_experience() + "\n" + heading + "\n新增过程\n")
                    result, output = _save(root, worklog)
                    self.assertEqual(result, 2, output)
                    self.assertIn("逐日期", output)
            experience.write_text(_experience().replace("生成后整体处理较慢", "2026-10-07验证：生成后整体处理较慢"))
            result, output = _save(root, worklog)
            self.assertEqual(result, 0, output)

    def test_historical_feedback_not_replayed_or_revalidated_as_current(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            worklog = _write_valid_context(root)
            previous = worklog.parent / "2026-08-16-old.md"
            previous.write_text("把 Git 结果当作对话交付，会让真正有价值的复盘消失。")
            result, output = _save(root, worklog)
            self.assertEqual(result, 0, output)
            self.assertNotIn("把 Git 结果当作对话交付", output)

    def test_old_library_without_machine_summary_still_checks_structure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            worklog = _write_valid_context(root)
            worklog.write_text("<!-- context-keeper: session-id=session-a -->\n# 实际过程\n执行 A，失败，等待权限。\n")
            result, output = _save(root, worklog)
            self.assertEqual(result, 0, output)
            self.assertIn("本次未验证当前状态", output)
            self.assertNotIn("你可能还没意识到", output)
            result, output = _call("coverage", "--root", str(root))
            self.assertEqual(result, 0, output)
            self.assertIn("missing_summary=1", output)

    def test_allows_explicit_no_new_insight(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            worklog = _write_valid_context(root)
            text = worklog.read_text()
            start = text.index("## 给用户看的增量认知")
            end = text.index("## 快速摘要", start)
            worklog.write_text(text[:start] + "## 给用户看的增量认知\n\n本轮未发现需要额外提醒的盲点或隐患。\n\n" + text[end:])
            result, output = _save(root, worklog)
            self.assertEqual(result, 0, output)


if __name__ == "__main__":
    unittest.main()
