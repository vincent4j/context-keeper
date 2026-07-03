#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path


ENTRY_RE = re.compile(r"^## \d{4}-\d{2}-\d{2} .*$")


def _clip(text: str, limit: int = 220) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _worklog_files(root: Path, limit: int) -> list[Path]:
    worklog_dir = root / "docs" / "worklog"
    if not worklog_dir.exists():
        return []
    return sorted(worklog_dir.glob("*.md"))[-limit:]


def _quick_summary(path: Path, full: bool = False, details: bool = False, max_lines: int = 12) -> list[str]:
    lines = _read_text(path).splitlines()
    start = next((idx for idx, line in enumerate(lines) if line.strip() == "## 快速摘要（用于下次对话）"), None)
    if start is None:
        return []
    block = lines[start : start + max_lines]
    if full:
        return [_clip(line) for line in block]
    wanted = ("**类型：**", "**完成：**", "**下一步：**")
    if details:
        wanted = ("**类型：**", "**完成：**", "**问题：**", "**经验：**", "**下一步：**")
    return [_clip(line, 180) for line in block if line.startswith(wanted)]


def _theme_summary(memory_path: Path) -> list[str]:
    if not memory_path.exists():
        return []
    lines = _read_text(memory_path).splitlines()
    start = next((idx for idx, line in enumerate(lines) if line.strip() == "## 主题摘要（按类型）"), None)
    if start is None:
        return []
    out: list[str] = []
    for line in lines[start:]:
        if line.strip() == "---" and out:
            break
        out.append(_clip(line, 240))
    return [line for line in out if line.strip()][:6]


def _memory_entries(memory_path: Path) -> list[list[str]]:
    if not memory_path.exists():
        return []
    lines = _read_text(memory_path).splitlines()
    entries: list[list[str]] = []
    current: list[str] = []
    in_timeline = False
    for line in lines:
        if line.strip() == "## 时间线（最新在前）":
            in_timeline = True
            continue
        if not in_timeline:
            continue
        if ENTRY_RE.match(line):
            if current:
                entries.append(current)
            current = [line]
            continue
        if current:
            if line.strip() == "---":
                break
            current.append(line)
    if current:
        entries.append(current)
    return entries


def _entry_type(entry: list[str]) -> str | None:
    match = re.search(r"`([^`]+)`", entry[0])
    return match.group(1) if match else None


def _trim_entry(entry: list[str], max_lines: int = 8, line_limit: int = 220) -> list[str]:
    return [_clip(line, line_limit) for line in entry[:max_lines] if line.strip()]


def _entry_resume_line(entry: list[str]) -> str:
    title = _clip(entry[0].lstrip("# "), 90)
    wanted = []
    for prefix in ("- **任务：**", "- **关键经验：**"):
        line = next((item for item in entry if item.startswith(prefix)), "")
        if line:
            wanted.append(_clip(line.lstrip("- "), 110))
    return " | ".join([title, *wanted])


def cmd_resume(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    memory_path = root / "docs" / "memory-keeper.md"

    print("最近工作摘要：")
    worklogs = _worklog_files(root, args.worklogs)
    if not worklogs:
        print("- 未找到 docs/worklog/*.md")
    for idx, path in enumerate(worklogs, 1):
        print(f"\n[{idx}] {_rel(root, path)}")
        summary = _quick_summary(path, full=args.full, details=args.details)
        if summary:
            print("\n".join(summary))
        else:
            print("- 未找到快速摘要章节")

    theme = _theme_summary(memory_path)
    if theme:
        print("\n近期主题摘要：")
        print("\n".join(theme))

    entries = _memory_entries(memory_path)
    if args.kind:
        same_kind = [entry for entry in entries if _entry_type(entry) == args.kind][:3]
        others = [entry for entry in entries if _entry_type(entry) != args.kind]
        selected = (same_kind + others)[: args.entries]
    else:
        selected = entries[: args.entries]

    if selected:
        print("\n近期经验：")
        for entry in selected:
            print("- " + _entry_resume_line(entry))
    elif not memory_path.exists():
        print("\n近期经验：未找到 docs/memory-keeper.md")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    memory_path = root / "docs" / "memory-keeper.md"
    if not memory_path.exists():
        print("未找到 docs/memory-keeper.md")
        return 1

    try:
        pattern = re.compile(args.query, re.IGNORECASE)
    except re.error:
        pattern = re.compile(re.escape(args.query), re.IGNORECASE)

    matches: list[tuple[list[str], list[str]]] = []
    for entry in _memory_entries(memory_path):
        hit_lines = [_clip(line, 160) for line in entry if pattern.search(line)]
        if hit_lines:
            matches.append((entry, hit_lines[: args.hit_lines]))
        if len(matches) >= args.entries:
            break

    if not matches:
        print("未命中相似经验")
        return 0

    print(f"命中 {len(matches)} 条相似经验：")
    for idx, (entry, hit_lines) in enumerate(matches, 1):
        print(f"\n{idx}. {entry[0].lstrip('# ').strip()}")
        for line in _trim_entry(entry[1:], 6):
            print(line)
        print("命中线索：" + " / ".join(hit_lines))
    return 0


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return completed.stdout.strip()


def cmd_status(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    sections = [
        ("branch", _git(root, "status", "--short", "--branch")),
        ("name-status", _git(root, "diff", "--name-status", "HEAD")),
        ("stat", _git(root, "diff", "--stat", "HEAD")),
    ]
    for title, content in sections:
        print(f"## {title}")
        print(content or "(empty)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Context Keeper capped probes")
    sub = parser.add_subparsers(dest="command", required=True)

    resume = sub.add_parser("resume", help="输出轻量续接摘要")
    resume.add_argument("--root", default=".")
    resume.add_argument("--worklogs", type=int, default=3)
    resume.add_argument("--entries", type=int, default=3)
    resume.add_argument("--kind", choices=["feature", "bugfix", "refactor", "research", "config"])
    resume.add_argument("--details", action="store_true")
    resume.add_argument("--full", action="store_true")
    resume.set_defaults(func=cmd_resume)

    search = sub.add_parser("search", help="在 memory-keeper 中查找相似经验")
    search.add_argument("--root", default=".")
    search.add_argument("--query", required=True)
    search.add_argument("--entries", type=int, default=5)
    search.add_argument("--hit-lines", type=int, default=3)
    search.set_defaults(func=cmd_search)

    status = sub.add_parser("status", help="输出 git 状态、文件名和 stat")
    status.add_argument("--root", default=".")
    status.set_defaults(func=cmd_status)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
