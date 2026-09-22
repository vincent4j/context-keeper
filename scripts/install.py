#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath


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


def _skill_roots(agent: str, home: Path, project: Path | None) -> list[Path]:
    """Return documented Skill roots without creating a second source copy."""
    if project:
        roots = {
            "codex": [project / ".agents/skills", project / ".codex/skills"],
            "claude": [project / ".claude/skills"],
            "cursor": [project / ".cursor/skills"],
            "workbuddy": [project / ".workbuddy/skills"],
            "hermes": [project / ".agents/skills"],
            "opencode": [project / ".opencode/skills"],
            "openclaw": [project / ".agents/skills"],
        }
    else:
        roots = {
            "codex": [home / ".agents/skills", home / ".codex/skills"],
            "claude": [home / ".claude/skills"],
            "cursor": [home / ".cursor/skills"],
            "workbuddy": [home / ".workbuddy/skills"],
            "hermes": [home / ".hermes/skills"],
            "opencode": [home / ".config/opencode/skills"],
            "openclaw": [home / ".agents/skills"],
        }
    return roots[agent]


def _require_source_checkout() -> None:
    manifest_path = SOURCE / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        files = manifest["files"]
        if manifest["type"] != "skill" or manifest["code"] != "context-keeper" or not isinstance(files, list):
            raise ValueError("manifest 格式错误")
        declared = set()
        for entry in files:
            path = PurePosixPath(entry["path"])
            if path.is_absolute() or ".." in path.parts or str(path) in declared:
                raise ValueError("manifest 路径无效或重复")
            declared.add(str(path))
            source_file = SOURCE.joinpath(*path.parts)
            if source_file.is_symlink() or not source_file.is_file():
                raise ValueError("声明文件缺失或为别名")
            if hashlib.sha256(source_file.read_bytes()).hexdigest() != entry["sha256"]:
                raise ValueError("声明文件哈希不匹配")
        if not {"SKILL.md", "scripts/install.py"} <= declared:
            raise ValueError("缺少必要文件")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"安装器只能从哈希校验通过的 SkillHub 包运行：{SOURCE}（{exc}）") from exc


def _check_install_target(target_root: Path) -> Path:
    target = target_root.expanduser().resolve() / "context-keeper"
    if target.is_symlink() and target.resolve() == SOURCE.resolve():
        return target
    if target.is_symlink():
        raise RuntimeError(f"检测到其他来源的 Context Keeper 配置，拒绝静默替换：{target} → {target.resolve()}；请先核对后手动替换")
    marker = target / "SKILL.md"
    if target.exists():
        if not marker.is_file() or "name: context-keeper" not in marker.read_text(encoding="utf-8", errors="replace"):
            raise RuntimeError(f"拒绝覆盖无法确认归属的目录：{target}")
        raise RuntimeError(f"检测到 Context Keeper 复制目录，拒绝自动删除可能存在的本地修改：{target}；请先核对差异，再恢复为从源码目录加载")
    return target


def _link_skill(target_root: Path) -> Path:
    target = _check_install_target(target_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        return target
    target.symlink_to(SOURCE, target_is_directory=True)
    if not target.is_symlink() or target.resolve() != SOURCE.resolve():
        raise RuntimeError(f"Skill 安装读回校验失败：{target}")
    return target


def _remove_skill(target_root: Path) -> tuple[str, str]:
    target = _check_remove_target(target_root)
    if not target.exists() and not target.is_symlink():
        return str(target), "absent"
    target.unlink()
    return str(target), "removed_symlink"


def _check_remove_target(target_root: Path) -> Path:
    target = target_root.expanduser() / "context-keeper"
    if not target.exists() and not target.is_symlink():
        return target
    if target.is_symlink():
        if target.resolve() != SOURCE.resolve():
            raise RuntimeError(f"拒绝删除其他来源的 Context Keeper 配置：{target} → {target.resolve()}")
        return target
    if target.resolve() == SOURCE.resolve():
        raise RuntimeError(f"拒绝删除正在使用的源码目录：{target}")
    raise RuntimeError(f"拒绝删除无法确认由安装器创建的目录：{target}；请先核对其中的本地修改")


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


def _check_bridge(path: Path) -> None:
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    start = text.find(BRIDGE_START)
    end = text.find(BRIDGE_END)
    if text.count(BRIDGE_START) != text.count(BRIDGE_END) or text.count(BRIDGE_START) > 1 or (end >= 0 and end < start):
        raise RuntimeError(f"入口标记不完整或重复，停止修改：{path}")


def _bridge_is_current(path: Path) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    start = text.find(BRIDGE_START)
    end = text.find(BRIDGE_END)
    return start >= 0 and end >= start and text[start:end + len(BRIDGE_END)] == BRIDGE.rstrip("\n")


def _ensure_bridge(args: argparse.Namespace) -> int:
    agents = ("codex", "claude", "cursor", "workbuddy", "hermes", "opencode", "openclaw")
    selected_agents = [agent for agent in agents if getattr(args, agent)]
    if args.all or len(selected_agents) != 1 or args.uninstall or args.project or args.codex_dir or args.claude_dir:
        raise RuntimeError("首次入口配置只接受一个当前 Agent，不混用安装、卸载或项目级选项。")
    agent = selected_agents[0]
    if agent not in ("codex", "claude"):
        raise RuntimeError(f"{agent} 当前只安装原生 Skill 目录；自动入口尚未完成运行时验证，停止写入规则文件。")
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
    _check_bridge(bridge)
    if _bridge_is_current(bridge):
        print(json.dumps({"scope": scope, "agent": agent, "bridge": str(bridge), "action": "unchanged"}, ensure_ascii=False))
        return 0
    if not args.approved:
        print(json.dumps({"approval_required": True, "operation": "配置自动入口", "file": str(bridge),
                          "effect": "新增或更新 Context Keeper 受控规则区块；保留文件中的其他内容"}, ensure_ascii=False))
        return 0
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
    parser.add_argument("--approved", action="store_true", help="已向用户展示本次影响并取得明确确认后执行写入")
    parser.add_argument("--skill-dir", default=str(Path(__file__).absolute().parents[1]), help="当前加载 Skill 的目录，优先保留安装别名")
    parser.add_argument("--root", default=".", help="当前项目位置，仅用于查找已安装别名")
    parser.add_argument("--all", action="store_true", help="安装到所有已支持的 Agent")
    parser.add_argument("--codex", action="store_true", help="安装到 Codex")
    parser.add_argument("--claude", action="store_true", help="安装到 Claude Code")
    parser.add_argument("--cursor", action="store_true", help="安装到 Cursor")
    parser.add_argument("--workbuddy", action="store_true", help="安装到 WorkBuddy")
    parser.add_argument("--hermes", action="store_true", help="安装到 Hermes")
    parser.add_argument("--opencode", action="store_true", help="安装到 OpenCode")
    parser.add_argument("--openclaw", action="store_true", help="安装到 OpenClaw")
    parser.add_argument("--project", help="项目级安装到指定仓库；省略时为用户级")
    parser.add_argument("--uninstall", action="store_true", help="移除 Skill 和自身入口区块")
    parser.add_argument("--bridge-only", action="store_true", help="只配置自动入口，不安装 Skill")
    parser.add_argument("--codex-dir", help="自定义 Codex skills 根目录")
    parser.add_argument("--claude-dir", help="自定义 Claude Code skills 根目录")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _require_source_checkout()
    if args.ensure_bridge:
        return _ensure_bridge(args)
    agents = ("codex", "claude", "cursor", "workbuddy", "hermes", "opencode", "openclaw")
    explicit = args.all or any(getattr(args, agent) for agent in agents)
    if args.all:
        for agent in agents:
            setattr(args, agent, True)
    elif not explicit:
        raise RuntimeError("请显式选择目标 Agent（例如 --codex），或使用 --all；安装器不会根据目录或命令猜测宿主。")

    selected_agents = [agent for agent in agents if getattr(args, agent)]
    unsupported_bridges = [agent for agent in selected_agents if agent not in ("codex", "claude")]
    if args.bridge_only and unsupported_bridges:
        raise RuntimeError("Cursor、WorkBuddy、Hermes、OpenCode 和 OpenClaw 当前只安装 Skill 目录；自动入口尚未完成运行时验证。")

    project = Path(args.project).expanduser().resolve() if args.project else None
    home = _home()
    installed: list[str] = []
    removed: list[dict[str, str]] = []
    bridges: list[dict[str, str]] = []
    bridge_paths = {
        "codex": project / "AGENTS.md" if project else home / ".codex" / "AGENTS.md",
        "claude": project / "CLAUDE.md" if project else home / ".claude" / "CLAUDE.md",
    }
    roots_by_agent = {
        agent: ([Path(args.codex_dir)] if agent == "codex" and args.codex_dir else
                [Path(args.claude_dir)] if agent == "claude" and args.claude_dir else
                _skill_roots(agent, home, project))
        for agent in agents
    }
    selected_roots: list[Path] = []
    seen_roots: set[Path] = set()
    for agent in selected_agents:
        for skill_root in roots_by_agent[agent]:
            resolved = skill_root.expanduser().resolve()
            if resolved not in seen_roots:
                selected_roots.append(skill_root)
                seen_roots.add(resolved)

    if args.uninstall:
        for skill_root in selected_roots:
            consumers = {agent for agent, roots in roots_by_agent.items()
                         if any(root.expanduser().resolve() == skill_root.expanduser().resolve() for root in roots)}
            target = skill_root.expanduser() / "context-keeper"
            if consumers - set(selected_agents) and (target.exists() or target.is_symlink()):
                raise RuntimeError(f"安装位置由多个 Agent 共用，拒绝单独卸载：{skill_root}；请使用 --all --uninstall")
            _check_remove_target(skill_root)
    elif not args.bridge_only:
        for skill_root in selected_roots:
            _check_install_target(skill_root)
    for agent in selected_agents:
        if agent in bridge_paths:
            _check_bridge(bridge_paths[agent])

    if not args.approved:
        print(json.dumps({
            "approval_required": True,
            "operation": "卸载" if args.uninstall else "安装",
            "skill_entries": [str(root.expanduser() / "context-keeper") for root in selected_roots] if not args.bridge_only else [],
            "rule_files": [str(bridge_paths[agent]) for agent in selected_agents if agent in bridge_paths],
            "effect": "仅移除当前源码创建的入口和自身规则区块" if args.uninstall else
                      "新增或复用 Skill 入口，并在 Codex/Claude Code 规则文件中新增或更新自身区块",
        }, ensure_ascii=False, indent=2))
        return 0

    if args.uninstall:
        for skill_root in selected_roots:
            skill, action = _remove_skill(skill_root)
            removed.append({"path": skill, "action": action})
        for agent in selected_agents:
            if agent in bridge_paths:
                bridge = bridge_paths[agent]
                bridges.append({"file": str(bridge), "action": _remove_bridge(bridge)})
    else:
        created: list[Path] = []
        saved_bridges: list[tuple[Path, bytes | None]] = []
        try:
            if not args.bridge_only:
                for skill_root in selected_roots:
                    target = _check_install_target(skill_root)
                    existed = target.is_symlink()
                    if not existed:
                        created.append(target)
                    installed.append(str(_link_skill(skill_root)))
            for agent in selected_agents:
                if agent in bridge_paths:
                    bridge = bridge_paths[agent]
                    saved_bridges.append((bridge, bridge.read_bytes() if bridge.exists() else None))
                    bridges.append({"file": str(bridge), "action": _upsert_bridge(bridge)})
        except (RuntimeError, OSError):
            try:
                for bridge, original in reversed(saved_bridges):
                    if original is None:
                        bridge.unlink(missing_ok=True)
                    elif bridge.read_bytes() != original:
                        bridge.write_bytes(original)
            finally:
                for target in reversed(created):
                    if target.is_symlink() and target.resolve() == SOURCE.resolve():
                        target.unlink()
            raise
    print(json.dumps({
        "scope": "project" if project else "user",
        "project": str(project) if project else None,
        "installed": installed,
        "removed": removed,
        "bridges": bridges,
        "configured_agents": [name for name, enabled in (("Codex", args.codex), ("Claude Code", args.claude), ("Cursor", args.cursor), ("WorkBuddy", args.workbuddy), ("Hermes", args.hermes), ("OpenCode", args.opencode), ("OpenClaw", args.openclaw)) if enabled],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError) as exc:
        print(f"Context Keeper 配置失败：{exc}")
        raise SystemExit(2)
