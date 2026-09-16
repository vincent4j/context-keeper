#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1]
BRIDGE_START = "<!-- context-keeper:start -->"
BRIDGE_END = "<!-- context-keeper:end -->"
BRIDGE = f"""{BRIDGE_START}
## Context Keeper

- 调用本 Skill 时若脚本报告“需要迁移”（退出码 3），停止保存、续接和检索；先展示 migrate 预览并询问用户，只有明确确认才执行 migrate --approved，不绕过门禁直接读取旧目录。
- 用户提及以前、上次、重复问题，当前失败准备重试或换路线且本轮证据不足，或准备推翻旧决策且依据不清时，使用 Context Keeper 做一次限量历史检索；普通新需求不检索，同一问题本轮不重复检索。
- 用户明确纠正事实、行为或遗漏，或失败处理产生可核验新结果时，必须先调用 context-keeper（支持 Skill 工具时使用该工具，否则读取其 SKILL.md），加载保存路由 references/save.md；在自然收尾点把新事实沉淀到 evolution，已有同主题则补证据，不必等用户说保存。沉淀或实际复用后简短告知用户。
- 历史事实必须来自记录；区分原文、摘要和推断。未找到只说明当前未找到证据，不猜测或编造。
- 两级安装同时存在时按项目配置执行一次，不重复调用；新错误、新证据或路线变化可重新检索。
- plans 和 worklogs 只允许同一会话更新；跨会话新增记录，不改写历史。
{BRIDGE_END}
"""


def _home() -> Path:
    return Path(os.environ.get("HOME") or str(Path.home())).expanduser().resolve()


def _command_exists(command: str) -> bool:
    return shutil.which(command) is not None


def _detect_codex() -> bool:
    home = _home()
    return _command_exists("codex") or (home / ".codex").exists() or (home / ".agents").exists()


def _detect_claude() -> bool:
    home = _home()
    return _command_exists("claude") or (home / ".claude").exists()


def _copy_skill(target_root: Path) -> Path:
    target = target_root.expanduser().resolve() / "context-keeper"
    if target.exists() and target.resolve() == SOURCE.resolve():
        return target
    marker = target / "SKILL.md"
    if target.exists() and (not marker.is_file() or "name: context-keeper" not in marker.read_text(encoding="utf-8", errors="replace")):
        raise RuntimeError(f"拒绝覆盖无法确认归属的目录：{target}")
    target.mkdir(parents=True, exist_ok=True)
    for name in ("SKILL.md", "README.md"):
        shutil.copy2(SOURCE / name, target / name)
    for name in ("references", "scripts"):
        source_dir = SOURCE / name
        target_dir = target / name
        target_dir.mkdir(parents=True, exist_ok=True)
        for source_file in source_dir.glob("*"):
            if source_file.is_file() and source_file.suffix in (".md", ".py"):
                shutil.copy2(source_file, target_dir / source_file.name)
    return target


def _remove_skill(target_root: Path) -> tuple[str, str]:
    target = target_root.expanduser() / "context-keeper"
    if not target.exists() and not target.is_symlink():
        return str(target), "absent"
    if target.is_symlink():
        target.unlink()
        return str(target), "removed_symlink"
    if target.resolve() == SOURCE.resolve():
        raise RuntimeError(f"拒绝删除正在使用的源码目录：{target}")
    marker = target / "SKILL.md"
    if not marker.is_file() or "name: context-keeper" not in marker.read_text(encoding="utf-8", errors="replace"):
        raise RuntimeError(f"拒绝删除无法确认归属的目录：{target}")
    shutil.rmtree(target)
    return str(target), "removed"


def _upsert_bridge(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(BRIDGE + "\n", encoding="utf-8")
        return "created"
    text = path.read_text(encoding="utf-8")
    start = text.find(BRIDGE_START)
    end = text.find(BRIDGE_END)
    if text.count(BRIDGE_START) != text.count(BRIDGE_END) or text.count(BRIDGE_START) > 1 or (end >= 0 and end < start):
        raise RuntimeError(f"入口标记不完整或重复，停止修改：{path}")
    if start >= 0:
        end += len(BRIDGE_END)
        replacement = BRIDGE.rstrip("\n")
        if text[start:end] == replacement:
            return "unchanged"
        path.write_text(text[:start] + replacement + text[end:], encoding="utf-8")
        return "updated"
    path.write_text(text + ("\n" if text.endswith("\n") else "\n\n") + BRIDGE, encoding="utf-8")
    return "appended"


def _ensure_bridge(args: argparse.Namespace) -> int:
    if args.all or args.codex == args.claude or args.uninstall or args.project or args.codex_dir or args.claude_dir:
        raise RuntimeError("首次入口配置只接受一个当前 Agent（--codex 或 --claude），不混用安装/卸载选项。")
    agent = "codex" if args.codex else "claude"
    home = _home()
    roots = (".agents", ".codex") if agent == "codex" else (".claude", ".agents")
    loaded = Path(os.path.abspath(Path(args.skill_dir).expanduser()))
    if loaded.resolve() != SOURCE.resolve():
        raise RuntimeError("传入的 Skill 路径与正在运行的安装器不一致，停止配置。")

    def location(path: Path):
        if path.name != "context-keeper" or path.parent.name != "skills" or path.parent.parent.name not in roots:
            return None
        base = path.parent.parent.parent
        return ("user", home) if base.resolve() == home else ("project", base)

    selected = location(loaded)
    if selected is None:
        # An Agent may expose the resolved source path instead of its installed alias.
        current = Path(args.root).resolve()
        candidates = [parent / name / "skills/context-keeper" for parent in (current, *current.parents)
                      if parent != home for name in roots]
        candidates.extend(home / name / "skills/context-keeper" for name in roots)
        for path in candidates:
            if path.is_dir() and path.resolve() == SOURCE.resolve():
                selected = location(path)
                break
    if selected is None:
        raise RuntimeError("无法确认安装范围，未修改任何入口。请提供已安装 Skill 的路径，或按安装说明显式选择范围。")
    scope, base = selected
    if scope == "user":
        bridge = home / (".codex/AGENTS.md" if agent == "codex" else ".claude/CLAUDE.md")
    else:
        bridge = base / ("AGENTS.md" if agent == "codex" else "CLAUDE.md")
    action = _upsert_bridge(bridge)
    actual = bridge.read_text(encoding="utf-8")
    if actual.count(BRIDGE_START) != 1 or BRIDGE.rstrip("\n") not in actual:
        raise RuntimeError(f"入口读回校验失败：{bridge}")
    print(json.dumps({"scope": scope, "agent": agent, "bridge": str(bridge), "action": action}, ensure_ascii=False))
    return 0


def _remove_bridge(path: Path) -> str:
    if not path.exists():
        return "absent"
    original = path.read_text(encoding="utf-8")
    start = original.find(BRIDGE_START)
    end = original.find(BRIDGE_END)
    if start < 0 or end < start:
        return "absent"
    end += len(BRIDGE_END)
    updated = (original[:start].rstrip() + "\n\n" + original[end:].lstrip("\n")).strip()
    if updated:
        path.write_text(updated + "\n", encoding="utf-8")
        return "removed"
    path.unlink()
    return "removed_file"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="安装 Context Keeper Skill 和自动入口")
    parser.add_argument("--ensure-bridge", action="store_true", help="首次使用时按安装位置补齐当前 Agent 入口")
    parser.add_argument("--skill-dir", default=str(Path(__file__).absolute().parents[1]), help="当前加载 Skill 的目录，优先保留安装别名")
    parser.add_argument("--root", default=".", help="当前项目位置，仅用于查找已安装别名")
    parser.add_argument("--all", action="store_true", help="安装到 Codex 和 Claude Code")
    parser.add_argument("--codex", action="store_true", help="安装到 Codex")
    parser.add_argument("--claude", action="store_true", help="安装到 Claude Code")
    parser.add_argument("--project", help="项目级安装到指定仓库；省略时为用户级")
    parser.add_argument("--uninstall", action="store_true", help="移除 Skill 和自身入口区块")
    parser.add_argument("--bridge-only", action="store_true", help="只配置自动入口，不复制 Skill")
    parser.add_argument("--codex-dir", help="自定义 Codex skills 根目录")
    parser.add_argument("--claude-dir", help="自定义 Claude Code skills 根目录")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.ensure_bridge:
        return _ensure_bridge(args)
    explicit = args.all or args.codex or args.claude
    if args.all:
        args.codex = True
        args.claude = True
    elif not explicit:
        args.codex = _detect_codex()
        args.claude = _detect_claude()
        if not args.codex and not args.claude:
            args.codex = True
            args.claude = True

    project = Path(args.project).expanduser().resolve() if args.project else None
    home = _home()
    installed: list[str] = []
    removed: list[dict[str, str]] = []
    bridges: list[dict[str, str]] = []
    if args.codex:
        if args.codex_dir:
            skill_root = Path(args.codex_dir)
        elif project:
            skill_root = project / ".agents" / "skills"
        else:
            skill_root = home / ".agents" / "skills" if (home / ".agents").exists() else home / ".codex" / "skills"
        bridge = project / "AGENTS.md" if project else home / ".codex" / "AGENTS.md"
        if args.uninstall:
            skill, action = _remove_skill(skill_root)
            removed.append({"path": skill, "action": action})
            bridges.append({"file": str(bridge), "action": _remove_bridge(bridge)})
        else:
            if not args.bridge_only:
                installed.append(str(_copy_skill(skill_root)))
            bridges.append({"file": str(bridge), "action": _upsert_bridge(bridge)})
    if args.claude:
        if args.claude_dir:
            skill_root = Path(args.claude_dir)
        elif project:
            skill_root = project / ".claude" / "skills"
        else:
            skill_root = home / ".claude" / "skills"
        bridge = project / "CLAUDE.md" if project else home / ".claude" / "CLAUDE.md"
        if args.uninstall:
            skill, action = _remove_skill(skill_root)
            removed.append({"path": skill, "action": action})
            bridges.append({"file": str(bridge), "action": _remove_bridge(bridge)})
        else:
            if not args.bridge_only:
                installed.append(str(_copy_skill(skill_root)))
            bridges.append({"file": str(bridge), "action": _upsert_bridge(bridge)})
    print(json.dumps({
        "scope": "project" if project else "user",
        "project": str(project) if project else None,
        "installed": installed,
        "removed": removed,
        "bridges": bridges,
        "configured_agents": [name for name, enabled in (("Codex", args.codex), ("Claude Code", args.claude)) if enabled],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError) as exc:
        print(f"Context Keeper 配置失败：{exc}")
        raise SystemExit(2)
