from __future__ import annotations

import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "context_keeper_probe.py"
SPEC = importlib.util.spec_from_file_location("context_keeper_probe", SCRIPT)
assert SPEC and SPEC.loader
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)


def _write_valid_context(root: Path) -> Path:
    worklog = root / "docs" / "worklog" / "2026-08-17-test.md"
    worklog.parent.mkdir(parents=True)
    worklog.write_text(
        """# Test

## 给用户看的增量认知

- **盲点：** 把 Git 结果当作 Context Keeper 的对话交付，会让真正有价值的复盘消失。
  - **影响：** 后续即使文件保存完整，用户仍无法获得增量认知。
- **决策影响：** 用户报告与供下次续接的快速摘要分离。
  - **影响：** 用户只看到盲点和隐患，不被已知进度淹没。

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
    (root / "docs" / "memory-keeper.md").write_text(
        """# 项目记忆索引

## 时间线（最新在前）

## 2026-08-17 - Test `bugfix`
- **任务：** 修复保存输出遗漏。
- **合同候选：** 保存并推送时最终回复必须包含增量认知。
- **详见：** [worklog/2026-08-17-test.md](worklog/2026-08-17-test.md)
""",
        encoding="utf-8",
    )
    return worklog


def _run(root: Path, worklog: Path) -> tuple[int, str]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        result = PROBE.main(["save-report", "--root", str(root), "--worklog", str(worklog)])
    return result, stream.getvalue()


class SaveReportTests(unittest.TestCase):
    def test_validates_and_renders_only_incremental_insight(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            worklog = _write_valid_context(root)

            result, output = _run(root, worklog)

        self.assertEqual(result, 0)
        self.assertIn("你可能还没意识到", output)
        self.assertIn("[盲点] 把 Git 结果当作", output)
        self.assertIn("[决策影响] 用户报告与供下次续接的快速摘要分离", output)
        self.assertIn("影响：后续即使文件保存完整", output)
        self.assertNotIn("修复保存输出遗漏", output)
        self.assertIn("工作日志：[worklog/2026-08-17-test.md]", output)

    def test_blocks_when_quick_summary_is_incomplete(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            worklog = _write_valid_context(root)
            text = worklog.read_text(encoding="utf-8").replace("**类型：** bugfix | 项目：Demo\n", "")
            worklog.write_text(text, encoding="utf-8")

            result, output = _run(root, worklog)

        self.assertEqual(result, 2)
        self.assertIn("快速摘要缺少字段", output)

    def test_blocks_when_incremental_insight_is_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            worklog = _write_valid_context(root)
            text = worklog.read_text(encoding="utf-8").replace("## 给用户看的增量认知", "## 普通章节")
            worklog.write_text(text, encoding="utf-8")

            result, output = _run(root, worklog)

        self.assertEqual(result, 2)
        self.assertIn("缺少“给用户看的增量认知”", output)

    def test_allows_explicit_no_new_insight_without_filler(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            worklog = _write_valid_context(root)
            text = worklog.read_text(encoding="utf-8")
            start = text.index("## 给用户看的增量认知")
            end = text.index("## 快速摘要", start)
            text = text[:start] + "## 给用户看的增量认知\n\n本轮未发现需要额外提醒的盲点或隐患。\n\n" + text[end:]
            worklog.write_text(text, encoding="utf-8")

            result, output = _run(root, worklog)

        self.assertEqual(result, 0)
        self.assertIn("本轮未发现需要额外提醒的盲点或隐患", output)
        self.assertNotIn("你可能还没意识到", output)


if __name__ == "__main__":
    unittest.main()
