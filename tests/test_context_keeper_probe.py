from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "context_keeper_probe.py"
SPEC = importlib.util.spec_from_file_location("context_keeper_probe", SCRIPT)
assert SPEC and SPEC.loader
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)


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
        worklog = root / "context-keeper" / "worklogs" / "2026-08-17-test.md"
        memory = root / "context-keeper" / "memory-keeper.md"
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
        evolution_file = root / "context-keeper" / "evolution" / "耗时分析.md"
        evolution_file.parent.mkdir(parents=True, exist_ok=True)
        evolution_file.write_text(_experience(), encoding="utf-8")
        (evolution_file.parent / "index.md").write_text("# 索引\n\n- [耗时分析](耗时分析.md)\n", encoding="utf-8")
    elif not legacy:
        evolution_dir = root / "context-keeper" / "evolution"
        evolution_dir.mkdir(parents=True, exist_ok=True)
        (evolution_dir / "index.md").write_text("# 索引\n", encoding="utf-8")
    PROBE._capture_baseline(root, "session-a")
    return worklog


def _save(root: Path, worklog: Path, *, legacy: bool = False) -> tuple[int, str]:
    args = ["save-report", "--root", str(root), "--worklog", str(worklog)]
    if not legacy:
        args.extend(["--session-id", "session-a"])
    return _call(*args)


class InitTests(unittest.TestCase):
    def test_initializes_default_visible_directory_and_index_link(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result, output = _call("init", "--root", str(root))
            self.assertEqual(result, 0)
            self.assertIn("默认记录位置：context-keeper", output)
            self.assertTrue((root / "context-keeper" / "plans").is_dir())
            self.assertTrue((root / "context-keeper" / "worklogs").is_dir())
            self.assertTrue((root / "context-keeper" / "evolution" / "index.md").is_file())
            self.assertIn("evolution/index.md", (root / "context-keeper" / "memory-keeper.md").read_text())

    def test_remembers_custom_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            result, _ = _call("init", "--root", str(root), "--store-dir", "project-notes/context")
            self.assertEqual(result, 0)
            config = json.loads((root / "context-keeper.json").read_text())
            self.assertEqual(config["directory"], "project-notes/context")

    def test_switch_requires_explicit_migration_and_can_return_to_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _call("init", "--root", str(root), "--store-dir", "project-notes/context")
            blocked, output = _call("init", "--root", str(root), "--store-dir", "context-keeper")
            self.assertEqual(blocked, 2)
            self.assertIn("--migrate", output)
            moved, output = _call("init", "--root", str(root), "--store-dir", "context-keeper", "--migrate")
            self.assertEqual(moved, 0)
            self.assertIn("已迁移记录", output)
            config = json.loads((root / "context-keeper.json").read_text())
            self.assertEqual(config["directory"], "context-keeper")
            self.assertFalse((root / "project-notes" / "context").exists())


class RecordBoundaryTests(unittest.TestCase):
    def test_record_path_creates_session_owned_file_and_other_session_appends(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _call("init", "--root", str(root))
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
            _call("init", "--root", str(root))
            _, path = _call("record-path", "--root", str(root), "--kind", "worklog", "--title", "测试", "--session-id", "a")
            ok, _ = _call("record-guard", "--root", str(root), "--path", path.strip(), "--session-id", "a")
            blocked, output = _call("record-guard", "--root", str(root), "--path", path.strip(), "--session-id", "b")
            self.assertEqual(ok, 0)
            self.assertEqual(blocked, 2)
            self.assertIn("跨会话修改已阻止", output)


class ResumeAndSearchTests(unittest.TestCase):
    def test_resume_defaults_to_five_entries_and_three_plus_two(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _call("init", "--root", str(root))
            memory = root / "context-keeper" / "memory-keeper.md"
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
            _call("init", "--root", str(root))
            memory = root / "context-keeper" / "memory-keeper.md"
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
            _call("init", "--root", str(root))
            worklog = root / "context-keeper" / "worklogs" / "2026-09-16-缺摘要.md"
            worklog.write_text("<!-- context-keeper: session-id=a -->\n# 标题\n\n这里记录了集中审核的真实耗时。\n")
            result, output = _call("resume", "--root", str(root))
            self.assertEqual(result, 0)
            self.assertIn("有限提取", output)

    def test_search_falls_back_to_unindexed_plan_and_worklog(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _call("init", "--root", str(root))
            (root / "context-keeper/plans/2026-09-16-整体复盘.md").write_text("用户要求整体核账。")
            (root / "context-keeper/worklogs/2026-09-16-耗时.md").write_text("集中审核耗时 9 分 16 秒。")
            _, plans = _call("search", "--root", str(root), "--query", "整体核账")
            _, logs = _call("search", "--root", str(root), "--query", "9 分 16 秒")
            self.assertIn("[需求与计划]", plans)
            self.assertIn("[工作日志]", logs)

    def test_search_excludes_replaced_and_caps_evolution_at_three(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _call("init", "--root", str(root))
            evolution = root / "context-keeper/evolution"
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
            _call("init", "--root", str(root))
            user.mkdir()
            (user / "通用经验.md").write_text(_experience("通用经验").replace("生成耗时", "跨项目线索"))
            result, output = _call("search", "--root", str(root), "--query", "跨项目线索", "--user-evolution-dir", str(user))
            self.assertEqual(result, 0)
            self.assertIn("用户级", output)

    def test_zero_hit_does_not_claim_history_never_existed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _call("init", "--root", str(root))
            _, output = _call("search", "--root", str(root), "--query", "不存在的关键词")
            self.assertIn("不代表历史上从未发生", output)


class RawHistoryTests(unittest.TestCase):
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


class EvolutionPromotionTests(unittest.TestCase):
    def test_requires_approval_and_promotes_valid_experience(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "project"
            user = Path(temp_dir) / "user"
            root.mkdir()
            _call("init", "--root", str(root))
            source = root / "context-keeper/evolution/耗时分析.md"
            source.write_text(_experience())
            blocked, _ = _call("promote-evolution", "--root", str(root), "--source", str(source), "--user-evolution-dir", str(user))
            ok, output = _call("promote-evolution", "--root", str(root), "--source", str(source), "--user-evolution-dir", str(user), "--approved")
            self.assertEqual(blocked, 2)
            self.assertEqual(ok, 0)
            self.assertTrue((user / "耗时分析.md").is_file())
            self.assertIn("已晋升", output)


class CoverageTests(unittest.TestCase):
    def test_default_output_is_compact_and_details_are_optional(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _call("init", "--root", str(root))
            worklog = root / "context-keeper/worklogs/2026-09-16-遗漏.md"
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
            _call("init", "--root", str(root))
            evolution = root / "context-keeper/evolution"
            (evolution / "a.md").write_text(_experience("A", "CK-001"))
            (evolution / "b.md").write_text(_experience("B", "CK-001"))
            (evolution / "bad.md").write_text("# bad\n- **状态：** unknown\n")
            memory = root / "context-keeper/memory-keeper.md"
            memory.write_text("# 索引\n\n## 未完成事项\n- 不完整事项\n\n[坏链接](missing.md)\n")
            result, output = _call("coverage", "--root", str(root), "--details")
            self.assertEqual(result, 1)
            self.assertIn("duplicate_ids=1", output)
            self.assertIn("broken_links=1", output)
            self.assertIn("pending_invalid=1", output)


class SaveReportTests(unittest.TestCase):
    def test_validates_new_layout_and_renders_evolution_notice(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            worklog = _write_valid_context(root, evolution=True)
            result, output = _save(root, worklog)
            self.assertEqual(result, 0, output)
            self.assertIn("自我进化：", output)

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

    def test_blocks_evolution_notice_without_persisted_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            worklog = _write_valid_context(root)
            text = worklog.read_text().replace("## 快速摘要", "## 自我进化\n\n- **已沉淀：** 已经学会了。\n\n## 快速摘要")
            worklog.write_text(text)
            result, output = _save(root, worklog)
            self.assertEqual(result, 2)
            self.assertNotIn("已保存上下文", output)

    def test_blocks_incomplete_evolution_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            worklog = _write_valid_context(root, evolution=True)
            (root / "context-keeper/evolution/耗时分析.md").write_text("# 不完整\n")
            result, output = _save(root, worklog)
            self.assertEqual(result, 2)
            self.assertIn("字段不完整", output)

    def test_blocks_repeated_visible_insight(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            worklog = _write_valid_context(root)
            previous = worklog.parent / "2026-08-16-old.md"
            previous.write_text("把 Git 结果当作对话交付，会让真正有价值的复盘消失。")
            result, output = _save(root, worklog)
            self.assertEqual(result, 2)
            self.assertIn("完全重复", output)

    def test_blocks_incomplete_summary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            worklog = _write_valid_context(root)
            worklog.write_text(worklog.read_text().replace("**类型：** bugfix | 项目：Demo\n", ""))
            result, _ = _save(root, worklog)
            self.assertEqual(result, 2)

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
