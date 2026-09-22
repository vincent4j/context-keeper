#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import NamedTuple


ENTRY_RE = re.compile(r"^## \d{4}-\d{2}-\d{2} .*$")
SESSION_RE = re.compile(r"<!--\s*context-keeper:\s*session-id=([^\s>]+)\s*-->")
LOCAL_LINK_RE = re.compile(r"!?\[[^\]]*\]\((?:<([^>]+)>|([^\s)]+))(?:\s+[\"\'][^)]*[\"\'])?\)")
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+\.md(?:#[^)]+)?)\)")
DEFAULT_STORE = "docs/context-keeper"
CONFIG_FILE = "context-keeper.json"
EVOLUTION_FIELDS = ("编号", "状态", "触发条件", "已知事实", "证据位置", "建议动作", "适用范围")
EVOLUTION_STATUSES = {"待验证", "已验证", "已替代"}
RC_NEEDS_CONFIRMATION = 5


class Layout(NamedTuple):
    root: Path
    store: Path
    memory: Path
    plans: Path
    worklogs: Path
    evolution: Path


def _clip(text: str, limit: int = 220) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _load_config(root: Path) -> dict:
    path = root / CONFIG_FILE
    if not path.is_file():
        return {}
    try:
        value = json.loads(_read_text(path))
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"记录目录配置无法读取，停止操作：{path}") from exc
    if not isinstance(value, dict) or not isinstance(value.get("directory"), str) or not value["directory"].strip():
        raise ValueError(f"记录目录配置无效，停止操作：{path}")
    return value


def _layout(root: Path, store_dir: str | None = None) -> Layout:
    root = root.resolve()
    if store_dir:
        configured = store_dir
    else:
        discovered = _discover_store(root)
        configured = str(discovered) if discovered is not None else str(_load_config(root).get("directory") or DEFAULT_STORE)
    store = Path(configured).expanduser()
    if not store.is_absolute():
        store = root / store
    store = store.resolve()
    return Layout(root, store, store / "memory-keeper.md", store / "plans", store / "worklogs", store / "evolution")


def _discovery_candidates(root: Path) -> list[Path]:
    return [(root / "docs" / "context-keeper").resolve(), (root / "context-keeper").resolve()]


def _looks_like_store(path: Path) -> bool:
    markers = ("memory-keeper.md", "worklogs", "plans", "evolution", "migration-manifest.json")
    return path.is_dir() and any((path / marker).exists() for marker in markers)


def _discover_store(root: Path) -> Path | None:
    """按目录名自动发现记录库：根目录与 docs/ 下各一个候选；歧义时明确报错，绝不静默二选一。"""
    found = [candidate for candidate in _discovery_candidates(root) if _looks_like_store(candidate)]
    if not found:
        return None
    if len(found) > 1:
        raise ValueError(
            "发现多个记录库："
            + "、".join(_rel(root, path) for path in found)
            + "。任一命令都可用 --store-dir 显式指定要用的目录，或删除多余的目录。"
        )
    return found[0]


def _configured_value(root: Path, store: Path) -> str:
    try:
        return str(store.relative_to(root))
    except ValueError:
        return str(store)


def _write_config(root: Path, store: Path) -> None:
    (root / CONFIG_FILE).write_text(
        json.dumps({"directory": _configured_value(root, store), "schema_version": 2}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _legacy_memory_paths(root: Path) -> list[Path]:
    return [root / "docs" / "memory-keeper.md"]


def _legacy_worklog_dirs(root: Path) -> list[Path]:
    return [root / "docs" / "worklogs", root / "docs" / "worklog"]


def _legacy_plan_dirs(root: Path) -> list[Path]:
    return [root / "docs" / "plans"]


def _legacy_sources(root: Path) -> list[tuple[Path, str]]:
    sources = [(path, "memory-keeper.md") for path in _legacy_memory_paths(root) if path.is_file()]
    for directories, kind in ((_legacy_plan_dirs(root), "plans"), (_legacy_worklog_dirs(root), "worklogs")):
        for directory in directories:
            if directory.is_dir() and any(directory.iterdir()):
                sources.append((directory, kind))
    return sources


def _migration_warning(root: Path) -> int:
    sources = _legacy_sources(root)
    print("需要迁移：发现旧版 Context Keeper 记录；新版已停止读取和写入旧结构。")
    for path, kind in sources:
        print(f"- {_rel(root, path)} → {kind}")
    print("请先运行 migrate 查看迁移范围，并询问用户是否确认。只有用户明确确认后，才运行 migrate --approved；未确认或拒绝时停止本 Skill。")
    return 3


def _migrated_records(root: Path, store_dir: str | None = None) -> set[Path]:
    manifest = _layout(root, store_dir).store / "migration-manifest.json"
    if not manifest.is_file():
        return set()
    data = json.loads(manifest.read_text(encoding="utf-8"))
    return {(_layout(root, store_dir).store / item).resolve() for item in data.get("historical_records", [])}


def cmd_migrate(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    sources = _legacy_sources(root)
    if not sources:
        print("未发现旧版记录，无需迁移。")
        return 0
    layout = _layout(root, args.store_dir)
    docs_exception = (root / "docs" / "context-keeper").resolve()
    if layout.store == root or (layout.store.is_relative_to(root / "docs") and layout.store != docs_exception):
        raise ValueError(
            f"迁移目标 {_rel(root, layout.store)} 不能是项目根目录或 docs/ 下的非 context-keeper 子路径，"
            f"会覆盖项目文档。请显式 --store-dir 指到根目录 context-keeper/ 或其他非 docs 子路径。"
        )
    if layout.store.exists() and (not layout.store.is_dir() or any(layout.store.iterdir())):
        raise ValueError(
            f"目标位置 {_rel(root, layout.store)} 已存在非空内容；停止迁移，绝不覆盖。请清理目标或用 --store-dir 指定其他位置。"
        )
    directory_mapping = {source.resolve(): layout.store / kind for source, kind in sources if source.is_dir()}
    mapping: dict[Path, Path] = {}
    for source, kind in sources:
        files = [source] if source.is_file() else list(source.rglob("*"))
        if source.is_symlink() or any(path.is_symlink() for path in files):
            raise ValueError("旧记录包含软链接，停止迁移，请先确认实际文件归属。")
        for path in files:
            if not path.is_file():
                continue
            target = layout.store / kind if source.is_file() else layout.store / kind / path.relative_to(source)
            if target in mapping.values():
                raise ValueError(f"旧目录存在同名目标，停止迁移：{target}")
            mapping[path.resolve()] = target
    print(f"旧版迁移预览：{len(mapping)} 个文件 → {_rel(root, layout.store)}")
    preview_limit = 20
    shown = 0
    for source, target in mapping.items():
        if shown >= preview_limit:
            print(f"  · ... 其余 {len(mapping) - shown} 个文件略")
            break
        print(f"  · {_rel(root, source)} → {_rel(root, target)}")
        shown += 1

    def rewrite(text: str, old: Path, new: Path) -> str:
        def replace(match: re.Match[str]) -> str:
            raw = match.group(1) or match.group(2)
            local, sep, fragment = raw.partition("#")
            if not local or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", local):
                return match.group(0)
            before = (old.parent / local).resolve()
            after = mapping.get(before, before)
            for source_dir, target_dir in directory_mapping.items():
                if before.is_relative_to(source_dir):
                    after = target_dir / before.relative_to(source_dir)
                    break
            if old == new and after == before:
                return match.group(0)
            updated = str(after) if Path(local).is_absolute() else os.path.relpath(after, new.parent)
            updated += sep + fragment
            if updated == raw:
                return match.group(0)
            if match.group(1) is None and " " in updated:
                updated = "<" + updated + ">"
            start, end = match.span(1 if match.group(1) is not None else 2)
            return match.group(0)[:start-match.start()] + updated + match.group(0)[end-match.start():]
        return LOCAL_LINK_RE.sub(replace, text)

    # Only Markdown links are rebased; history prose and code are not rewritten.
    external: dict[Path, bytes] = {}
    excluded = {".git", ".context-keeper-backups", "node_modules", ".venv", "venv", "vendor"}
    for parent, dirs, files in os.walk(root):
        dirs[:] = [name for name in dirs if name not in excluded and not (Path(parent)/name).is_symlink()]
        for name in files:
            path = Path(parent) / name
            if path.suffix != ".md" or path.is_symlink() or path.resolve() in mapping:
                continue
            original = path.read_bytes()
            try:
                text = original.decode("utf-8")
            except UnicodeDecodeError:
                continue
            changed = rewrite(text, path, path)
            if changed != text:
                external[path] = changed.encode("utf-8")
    print(f"需同步修正 {len(external)} 个项目 Markdown 文件中的链接：")
    for path in sorted(external):
        print(f"  · {_rel(root, path)}")
    print("先备份原文件，只更改链接地址。")
    print("历史正文不补写、不推断；建立 evolution 空索引，旧经验按需核对后再沉淀。")
    if not args.approved:
        print("尚未迁移。请取得用户明确确认后运行 migrate --approved。")
        return 3

    backup_root = root / ".context-keeper-backups"
    backup_root.mkdir(exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix="migration-", dir=backup_root))
    originals = {path: path.read_bytes() for path in [*mapping, *external]}
    config = root / CONFIG_FILE
    old_config = config.read_bytes() if config.exists() else None
    for path, content in originals.items():
        saved = backup / path.relative_to(root)
        saved.parent.mkdir(parents=True, exist_ok=True)
        saved.write_bytes(content)
    if old_config is not None:
        (backup / CONFIG_FILE).write_bytes(old_config)
    layout.store.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".context-keeper-migration-", dir=layout.store.parent))
    published = False
    try:
        for source, target in mapping.items():
            output = stage / target.relative_to(layout.store)
            output.parent.mkdir(parents=True, exist_ok=True)
            content = originals[source]
            if source.suffix == ".md":
                content = rewrite(content.decode("utf-8"), source, target).encode("utf-8")
            output.write_bytes(content)
        for kind in ("plans", "worklogs", "evolution"):
            (stage / kind).mkdir(exist_ok=True)
        memory = stage / "memory-keeper.md"
        text = memory.read_text() if memory.exists() else "# 项目记忆索引\n"
        text = text.replace("## 未完成事项", "## 历史未完成事项（迁移时未复核）")
        text += "\n---\n\n## 未完成事项\n\n- 暂无\n\n## 进化经验入口\n\n- [进化经验索引](evolution/index.md)\n"
        text += "\n## 迁移记录入口\n\n"
        records = []
        for target in mapping.values():
            relative = target.relative_to(layout.store)
            if relative.parts[0] in ("plans", "worklogs") and target.suffix == ".md":
                records.append(str(relative))
                text += f"- [{target.stem}]({relative})\n"
        memory.write_text(text)
        (stage / "evolution/index.md").write_text("# 自我进化索引\n\n## 有效经验\n\n- 暂无\n")
        manifest = {"schema_version": 2, "backup": str(backup), "historical_records": records,
                    "files": [{"old": str(p.relative_to(root)), "new": str(t), "sha256": hashlib.sha256(originals[p]).hexdigest()} for p,t in mapping.items()]}
        (stage / "migration-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n")
        # Abort if anything changed since preparing the backup.
        drifted = [p for p, content in originals.items() if not p.exists() or p.read_bytes() != content]
        if drifted:
            print("迁移期间以下源文件发生变化：")
            for path in drifted:
                print(f"  · {_rel(root, path)}")
            raise ValueError(f"迁移期间源文件发生变化（{len(drifted)} 个），已停止；请重新预览。")
        if layout.store.exists():
            layout.store.rmdir()
        stage.rename(layout.store)
        published = True
        for path, content in external.items():
            path.write_bytes(content)
        if layout.store in _discovery_candidates(root):
            config.unlink(missing_ok=True)
        else:
            _write_config(root, layout.store)
        for path in mapping:
            path.unlink()
        # 复制 manifest 到备份目录，方便撤销时识别迁移文件
        shutil.copy2(layout.store / "migration-manifest.json", backup / "migration-manifest.json")
    except Exception:
        if published:
            for path, content in originals.items():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            if old_config is None:
                config.unlink(missing_ok=True)
            else:
                config.write_bytes(old_config)
            shutil.rmtree(layout.store)
        elif stage.exists():
            shutil.rmtree(stage)
        raise
    for source, _ in sources:
        if source.is_dir():
            for directory in sorted((p for p in source.rglob("*") if p.is_dir()), reverse=True):
                if not any(directory.iterdir()):
                    directory.rmdir()
            if not any(source.iterdir()):
                source.rmdir()
    print(f"迁移完成：{_rel(root, layout.store)}")
    print(f"  · 迁移文件 {len(mapping)} 个；修改项目链接 {len(external)} 个 Markdown")
    print(f"  · 原始备份：{_rel(root, backup)}")
    print(f"  · 迁移清单：{_rel(root, layout.store / 'migration-manifest.json')}（备份目录也有一份）")
    print(f"  · 历史缺项保持原状，不冒充新验证。")
    return 0


def _memory_paths(root: Path, store_dir: str | None = None) -> list[Path]:
    candidates = [_layout(root, store_dir).memory]
    return list(dict.fromkeys(path for path in candidates if path.is_file()))


def _worklog_dirs(root: Path, store_dir: str | None = None) -> list[Path]:
    candidates = [_layout(root, store_dir).worklogs]
    return list(dict.fromkeys(path for path in candidates if path.is_dir()))


def _plan_dirs(root: Path, store_dir: str | None = None) -> list[Path]:
    candidates = [_layout(root, store_dir).plans]
    return list(dict.fromkeys(path for path in candidates if path.is_dir()))


def _markdown_files(directories: list[Path]) -> list[Path]:
    files: list[Path] = []
    for directory in directories:
        files.extend(directory.rglob("*.md"))
    return sorted(dict.fromkeys(path.resolve() for path in files), key=lambda path: (path.name, str(path)))


def _worklog_files(root: Path, limit: int | None = None, store_dir: str | None = None) -> list[Path]:
    files = _markdown_files(_worklog_dirs(root, store_dir))
    return files[-limit:] if limit is not None else files


def _plan_files(root: Path, store_dir: str | None = None) -> list[Path]:
    return _markdown_files(_plan_dirs(root, store_dir))


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


def _fallback_summary(path: Path, max_items: int = 3) -> list[str]:
    items: list[str] = []
    for line in _read_text(path).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("<!--"):
            continue
        if stripped.startswith(("- ", "* ")) or len(stripped) >= 12:
            items.append(_clip(stripped.lstrip("-* "), 180))
        if len(items) >= max_items:
            break
    return items


def _quick_summary_fields(path: Path) -> dict[str, str]:
    lines = _read_text(path).splitlines()
    start = next((idx for idx, line in enumerate(lines) if line.strip() == "## 快速摘要（用于下次对话）"), None)
    if start is None:
        return {}
    fields: dict[str, str] = {}
    pattern = re.compile(r"^\*\*(类型|完成|问题|经验|下一步|文件)：\*\*\s*(.*)$")
    for line in lines[start + 1 : start + 14]:
        match = pattern.match(line.strip())
        if match:
            fields[match.group(1)] = match.group(2).strip()
    return fields


def _section_items(path: Path, heading: str, limit: int | None = 5) -> list[str]:
    if not path.is_file():
        return []
    lines = _read_text(path).splitlines()
    start = next((idx for idx, line in enumerate(lines) if line.strip() == heading), None)
    if start is None:
        return []
    result: list[str] = []
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if stripped.startswith("## "):
            break
        if stripped.startswith("- ") and stripped not in ("- 无", "- 暂无"):
            result.append(_clip(stripped, 260))
        if limit is not None and len(result) >= limit:
            break
    return result


def _memory_entries(memory_path: Path) -> list[list[str]]:
    if not memory_path.exists():
        return []
    entries: list[list[str]] = []
    current: list[str] = []
    in_timeline = False
    for line in _read_text(memory_path).splitlines():
        if line.strip() == "## 时间线（最新在前）":
            in_timeline = True
            continue
        if not in_timeline:
            continue
        if ENTRY_RE.match(line):
            if current:
                entries.append(current)
            current = [line]
        elif current:
            if line.strip() == "---":
                break
            current.append(line)
    if current:
        entries.append(current)
    return entries


def _all_memory_entries(root: Path, store_dir: str | None = None) -> list[list[str]]:
    entries: list[list[str]] = []
    seen: set[str] = set()
    for path in _memory_paths(root, store_dir):
        for entry in _memory_entries(path):
            key = "\n".join(entry)
            if key not in seen:
                entries.append(entry)
                seen.add(key)
    return entries


def _entry_type(entry: list[str]) -> str | None:
    match = re.search(r"`([^`]+)`", entry[0])
    return match.group(1) if match else None


def _entry_resume_line(entry: list[str]) -> str:
    wanted = []
    for prefix in ("- **任务：**", "- **关键经验：**"):
        line = next((item for item in entry if item.startswith(prefix)), "")
        if line:
            wanted.append(_clip(line.lstrip("- "), 110))
    return " | ".join([_clip(entry[0].lstrip("# "), 90), *wanted])


def _compile_pattern(query: str) -> re.Pattern[str]:
    try:
        return re.compile(query, re.IGNORECASE)
    except re.error:
        return re.compile(re.escape(query), re.IGNORECASE)


def _file_hits(path: Path, pattern: re.Pattern[str], limit: int) -> list[str]:
    return [_clip(line, 180) for line in _read_text(path).splitlines() if pattern.search(line)][:limit]


def _session_id(path: Path) -> str | None:
    if not path.is_file():
        return None
    match = SESSION_RE.search(_read_text(path)[:1200])
    return match.group(1) if match else None


def _safe_title(value: str) -> str:
    value = re.sub(r"[\/:*?\"<>|\x00-\x1f]+", "-", value.strip())
    value = re.sub(r"\s+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-.")
    if not value:
        raise ValueError("标题不能为空")
    if not re.search(r"[\u4e00-\u9fff]", value):
        raise ValueError("plan/worklog 标题必须包含中文主题")
    return value


def _field_map(path: Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    pattern = re.compile(r"^-\s+(?:\*\*)?([^：*]+)：(?:\*\*)?\s*(.+)$")
    for line in _read_text(path).splitlines():
        match = pattern.match(line.strip())
        if match:
            fields[match.group(1).strip()] = match.group(2).strip()
    return fields


def _validate_evolution(path: Path) -> list[str]:
    fields = _field_map(path)
    problems = [f"缺少字段 {name}" for name in EVOLUTION_FIELDS if not fields.get(name)]
    status = fields.get("状态")
    if status and status not in EVOLUTION_STATUSES:
        problems.append(f"状态无效 {status}")
    if status == "已替代":
        replacement = fields.get("替代为", "")
        targets = _markdown_links(path) if replacement else []
        replacement_targets = [target for target in targets if target.name in replacement]
        if not replacement_targets or any(target == path or not target.is_file() for target in replacement_targets):
            problems.append("已替代经验必须链接有效的替代经验")
        elif any(_evolution_status(target) == "已替代" for target in replacement_targets):
            problems.append("替代关系必须直接指向当前经验，不能形成循环或替代链")
    return problems


def _evolution_status(path: Path) -> str:
    return _field_map(path).get("状态", "待验证")


def _user_evolution_dir(value: str | None = None) -> Path:
    return Path(value).expanduser().resolve() if value else (Path.home() / ".context-keeper" / "evolution").resolve()


def _canonical_experience(path: Path) -> str:
    text = _read_text(path)
    for raw in LINK_RE.findall(text):
        if "://" not in raw and not Path(raw.split("#", 1)[0]).is_absolute():
            local, sep, fragment = raw.partition("#")
            text = text.replace(f"]({raw})", f"]({(path.parent / local).resolve()}{sep}{fragment})")
    return text


def _evolution_files(root: Path, user_dir: str | None = None, store_dir: str | None = None) -> list[tuple[str, Path]]:
    layout = _layout(root, store_dir)
    result: list[tuple[str, Path]] = []
    if layout.evolution.is_dir():
        result.extend(("project", path.resolve()) for path in layout.evolution.glob("*.md") if path.name != "index.md")
    user_evolution = _user_evolution_dir(user_dir)
    if user_evolution.is_dir():
        result.extend(("user", path.resolve()) for path in user_evolution.glob("*.md") if path.name != "index.md")
    # A promoted copy is the same experience, not another candidate.
    unique = {}
    for scope, path in sorted(result, key=lambda item: (item[0] != "project", item[1].name)):
        fields = _field_map(path)
        key = (fields.get("编号"), _canonical_experience(path).strip())
        unique.setdefault(key, (scope, path))
    return sorted(unique.values(), key=lambda item: (_evolution_status(item[1]) != "已验证", item[0] != "project", item[1].name))


def _markdown_links(path: Path) -> list[Path]:
    links: list[Path] = []
    for target in LINK_RE.findall(_read_text(path)):
        raw = target.split("#", 1)[0]
        if "://" in raw:
            continue
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = path.parent / candidate
        links.append(candidate.resolve())
    return links


def _user_visible_items(path: Path) -> tuple[list[tuple[str, str, str]], bool]:
    lines = _read_text(path).splitlines()
    start = next((idx for idx, line in enumerate(lines) if line.strip() == "## 给用户看的增量认知"), None)
    if start is None:
        return [], False
    item_pattern = re.compile(r"^- \*\*(盲点|复盘|隐患|决策影响|规则候选|合同候选)：\*\*\s*(.+)$")
    value_pattern = re.compile(r"^- \*\*影响：\*\*\s*(.+)$")
    items: list[tuple[str, str, str]] = []
    pending: tuple[str, str] | None = None
    no_extra = False
    for raw_line in lines[start + 1 :]:
        line = raw_line.strip()
        if line.startswith("## "):
            break
        if line == "本轮未发现需要额外提醒的盲点或隐患。":
            no_extra = True
            continue
        item_match = item_pattern.match(line)
        if item_match:
            if pending:
                items.append((pending[0], pending[1], ""))
            pending = (item_match.group(1), item_match.group(2).strip())
            continue
        value_match = value_pattern.match(line)
        if value_match and pending:
            items.append((pending[0], pending[1], value_match.group(1).strip()))
            pending = None
    if pending:
        items.append((pending[0], pending[1], ""))
    return items, no_extra


def _evolution_notices(path: Path) -> list[tuple[str, str]]:
    lines = _read_text(path).splitlines()
    start = next((idx for idx, line in enumerate(lines) if line.strip() == "## 自我进化"), None)
    if start is None:
        return []
    pattern = re.compile(r"^- \*\*(已沉淀|本次复用|修正经验)：\*\*\s*(.+)$")
    notices: list[tuple[str, str]] = []
    for raw_line in lines[start + 1 :]:
        line = raw_line.strip()
        if line.startswith("## "):
            break
        match = pattern.match(line)
        if match:
            notices.append((match.group(1), match.group(2).strip()))
    return notices


def _notice_links(path: Path, notices: list[tuple[str, str]]) -> list[Path]:
    links: list[Path] = []
    for _, content in notices:
        for target in LINK_RE.findall(content):
            candidate = Path(target.split("#", 1)[0])
            if not candidate.is_absolute():
                candidate = path.parent / candidate
            links.append(candidate.resolve())
    return links


def _notice_link_groups(path: Path, notices: list[tuple[str, str]]) -> list[list[Path]]:
    groups: list[list[Path]] = []
    for _, content in notices:
        current: list[Path] = []
        for target in LINK_RE.findall(content):
            candidate = Path(target.split("#", 1)[0])
            if not candidate.is_absolute():
                candidate = path.parent / candidate
            current.append(candidate.resolve())
        groups.append(current)
    return groups


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


def cmd_init(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    try:
        existing = _discover_store(root)
    except ValueError as exc:
        print(str(exc))
        return 2
    if args.store_dir:
        target = _layout(root, args.store_dir)
    else:
        target = _layout(root, None)
    if existing is not None and existing == target.store:
        print(f"Context Keeper 记录库已就绪：{_rel(root, existing)}")
        return 0
    current = _layout(root)
    if args.store_dir and current.store != target.store and current.store.exists():
        if not args.migrate:
            print(
                f"记录位置仍为 {_rel(root, current.store)}；如需迁移到 {_rel(root, target.store)}，请使用 --migrate。",
            )
            return 2
        if target.store.exists() and any(target.store.iterdir()):
            print(f"目标目录非空，停止迁移：{_rel(root, target.store)}")
            return 2
        if target.store.is_relative_to(current.store) or current.store.is_relative_to(target.store):
            print("停止迁移：源目录与目标目录不能相互包含。")
            return 2
        # Moving records must preserve evidence destinations without editing history.
        for document in current.store.rglob("*.md"):
            for enclosed, bare in LOCAL_LINK_RE.findall(_read_text(document)):
                raw = enclosed or bare
                local = raw.split("#", 1)[0]
                if not local or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", local):
                    continue
                before = (document.parent / local).resolve()
                after = ((target.store / document.relative_to(current.store)).parent / local).resolve()
                expected = (target.store / before.relative_to(current.store)
                            if before.is_relative_to(current.store) else before)
                if after != expected:
                    print(f"停止迁移：{_rel(root, document)} 的证据链接 {raw} 会改变指向；历史记录保持不变。")
                    return 2
        target.store.parent.mkdir(parents=True, exist_ok=True)
        if target.store.exists():
            target.store.rmdir()
        shutil.move(str(current.store), str(target.store))
        print(f"已迁移记录：{_rel(root, current.store)} → {_rel(root, target.store)}")
    if not args.approved:
        if args.store_dir:
            print(f"Context Keeper 准备在 {_rel(root, target.store)} 创建记录库（来自 --store-dir）。")
        else:
            print(f"Context Keeper 准备在 {_rel(root, target.store)} 创建默认记录库。")
        print(f"确认请加 --approved；改用其他位置请加 --store-dir <path>。")
        return RC_NEEDS_CONFIRMATION
    existed = target.store.exists()
    for directory in (target.store, target.plans, target.worklogs, target.evolution):
        directory.mkdir(parents=True, exist_ok=True)
    if target.store in _discovery_candidates(root):
        (root / CONFIG_FILE).unlink(missing_ok=True)
    elif args.store_dir:
        _write_config(root, target.store)
    if not target.memory.exists():
        target.memory.write_text(
            "# 项目记忆索引\n\n## 未完成事项\n\n- 暂无\n\n## 主题摘要（按类型）\n\n---\n\n"
            "## 进化经验入口\n\n- [进化经验索引](evolution/index.md)\n\n## 时间线（最新在前）\n\n---\n",
            encoding="utf-8",
        )
    evolution_index = target.evolution / "index.md"
    if not evolution_index.exists():
        evolution_index.write_text("# 自我进化索引\n\n## 有效经验\n\n- 暂无\n\n## 已替代经验\n\n- 暂无\n", encoding="utf-8")
    if not existed:
        if args.store_dir:
            print(f"Context Keeper 记录位置：{_rel(root, target.store)}")
        else:
            print(f"Context Keeper 默认记录位置：{_rel(root, target.store)}；如需修改，可显式迁移。")
    else:
        print(f"Context Keeper 记录位置：{_rel(root, target.store)}")
    return 0


def _baseline_path(root: Path, session: str) -> Path:
    key = hashlib.sha256(f"{root.resolve()}:{session}".encode()).hexdigest()
    return Path.home() / ".cache" / "context-keeper" / f"{key}.json"


def _capture_baseline(root: Path, session: str) -> None:
    target = _baseline_path(root, session)
    if target.exists():
        return
    records = _plan_files(root) + _worklog_files(root)
    baseline = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in records if _session_id(p) != session}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(baseline), encoding="utf-8")


def _check_baseline(root: Path, session: str) -> list[str]:
    target = _baseline_path(root, session)
    if not target.is_file():
        return ["缺少会话历史基线；保存前先运行 record-path 或 record-guard"]
    baseline = json.loads(target.read_text())
    return [f"历史记录被改写或删除：{path}" for path, digest in baseline.items()
            if not Path(path).is_file() or hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest]


def _validate_plan(path: Path) -> list[str]:
    text = _read_text(path)
    required = ("用户需求", "范围", "实施计划", "验证方式", "待确认")
    return [f"缺少 {heading}" for heading in required
            if not re.search(r"^## " + heading + r"\s*\n+(?!#)(\S[^\n]*)", text, re.MULTILINE)]


def cmd_record_path(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    store_dir = getattr(args, "store_dir", None)
    layout = _layout(root, store_dir)
    directory = layout.plans if args.kind == "plan" else layout.worklogs
    directory.mkdir(parents=True, exist_ok=True)
    title = _safe_title(args.title)
    date = args.date or dt.date.today().isoformat()
    try:
        if dt.date.fromisoformat(date).isoformat() != date:
            raise ValueError()
    except ValueError:
        print("日期必须为有效的 YYYY-MM-DD")
        return 2
    _capture_baseline(root, args.session_id)
    base = directory / f"{date}-{title}.md"
    if base.exists() and (_session_id(base) != args.session_id or base in _migrated_records(root, store_dir)):
        index = 2
        while True:
            candidate = directory / f"{date}-{title}-{index}.md"
            if not candidate.exists() or (_session_id(candidate) == args.session_id and candidate not in _migrated_records(root, store_dir)):
                base = candidate
                break
            index += 1
    if not base.exists():
        base.write_text(f"<!-- context-keeper: session-id={args.session_id} -->\n# {title}\n", encoding="utf-8")
    print(_rel(root, base))
    return 0


def cmd_record_guard(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    store_dir = getattr(args, "store_dir", None)
    path = Path(args.path)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    layout = _layout(root, store_dir)
    allowed = any(parent == path.parent for parent in (layout.plans, layout.worklogs))
    if not allowed or not path.is_file():
        print(f"记录不存在或不在当前记录目录：{_rel(root, path)}")
        return 2
    if path in _migrated_records(root, store_dir):
        print("迁移保留的历史记录不可更新；请创建当前会话的新记录。")
        return 2
    _capture_baseline(root, args.session_id)
    actual = _session_id(path)
    if actual != args.session_id:
        print(f"跨会话修改已阻止：文件属于 {actual or '未知会话'}，当前会话为 {args.session_id}")
        return 2
    print(f"会话边界通过：{_rel(root, path)}")
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    store_dir = getattr(args, "store_dir", None)
    pattern = _compile_pattern(args.query) if args.query else None
    memory_paths = _memory_paths(root, store_dir)
    print("最近工作摘要：")
    worklogs = _worklog_files(root, args.worklogs, store_dir)
    if not worklogs:
        print("- 未找到工作日志")
    for idx, path in enumerate(worklogs, 1):
        print(f"\n[{idx}] {_rel(root, path)}")
        summary = _quick_summary(path, full=args.full, details=args.details)
        if summary:
            print("\n".join(summary))
        else:
            print("- 快速摘要缺失；以下为有限提取，不代表完整记录")
            for item in _fallback_summary(path):
                print(f"  - {item}")

    pending: list[str] = []
    for path in memory_paths:
        pending.extend(_section_items(path, "## 未完成事项", None))
    pending = [item for item in dict.fromkeys(pending) if not re.search(r"状态：\s*(已完成|已取消)", item)]
    if pattern:
        pending = [item for item in pending if pattern.search(item)]
    if pending:
        print("\n相关未完成事项：" if pattern else "\n未完成事项：")
        print("\n".join(pending[: args.pending]))

    historical_pending = []
    for path in memory_paths:
        historical_pending.extend(_section_items(path, "## 历史未完成事项（迁移时未复核）", None))
    if pattern:
        historical_pending = [item for item in historical_pending if pattern.search(item)]
    historical_pending = historical_pending[:max(0, args.pending - len(pending[:args.pending]))]
    if historical_pending:
        print("\n迁移保留的历史待办（尚未复核，不代表当前状态或授权）：")
        print("\n".join(historical_pending))

    if memory_paths:
        theme = _theme_summary(memory_paths[0])
        if theme:
            print("\n近期主题摘要：")
            print("\n".join(theme))

    evolution = []
    if pattern:
        for scope, path in _evolution_files(root, None, store_dir):
            if _evolution_status(path) != "已替代" and _file_hits(path, pattern, 1):
                title = next((line[2:] for line in _read_text(path).splitlines() if line.startswith("# ")), path.stem)
                evolution.append((_field_map(path).get("类型"), f"- [{_evolution_status(path)}] {title}：{_field_map(path).get('建议动作', '')}（{path}）"))
            if len(evolution) >= min(3, args.entries):
                break
    entries = _all_memory_entries(root, store_dir)
    if pattern:
        entries = [entry for entry in entries if pattern.search("\n".join(entry))]
    candidates = evolution + [(_entry_type(entry), "- " + _entry_resume_line(entry)) for entry in entries]
    if args.kind:
        selected = ([item for item in candidates if item[0] == args.kind][:3]
                    + [item for item in candidates if item[0] != args.kind][:2])[:args.entries]
    else:
        selected = candidates[:args.entries]
    if selected:
        print("\n相关经验：" if pattern else "\n近期经验：")
        for _, line in selected:
            print(line)
    elif not memory_paths:
        print("\n近期经验：未找到 memory-keeper.md")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    store_dir = getattr(args, "store_dir", None)
    pattern = _compile_pattern(args.query)
    results: list[tuple[str, str, list[str]]] = []
    seen: set[str] = set()
    evolution_count = 0
    for scope, path in _evolution_files(root, args.user_evolution_dir, store_dir):
        if evolution_count >= min(args.evolution_entries, args.entries):
            break
        status = _evolution_status(path)
        if status == "已替代":
            continue
        hits = _file_hits(path, pattern, args.hit_lines)
        index_path = path.parent / "index.md"
        if not hits and index_path.is_file():
            hits = [_clip(line, 180) for line in _read_text(index_path).splitlines()
                    if path.name in line and pattern.search(line)][:args.hit_lines]
        if not hits:
            continue
        title = next((line.lstrip("# ") for line in _read_text(path).splitlines() if line.startswith("# ")), path.stem)
        suffix = f"{status}；{'项目' if scope == 'project' else '用户级'}"
        results.append(("evolution", f"{title}（{suffix}；{_rel(root, path)}）", hits))
        seen.add(str(path))
        evolution_count += 1

    if len(results) < args.entries:
        for memory_path in _memory_paths(root, store_dir):
            for entry in _memory_entries(memory_path):
                hits = [_clip(line, 180) for line in entry if pattern.search(line)][: args.hit_lines]
                key = "\n".join(entry)
                if hits and key not in seen:
                    results.append(("memory", entry[0].lstrip("# ").strip(), hits))
                    seen.add(key)
                if len(results) >= args.entries:
                    break
            if len(results) >= args.entries:
                break

    if len(results) < args.entries:
        scanned = 0
        historical_files = [("plan", path) for path in _plan_files(root, store_dir)]
        historical_files.extend(("worklog", path) for path in _worklog_files(root, None, store_dir))
        historical_files.sort(key=lambda item: (item[1].name, str(item[1])), reverse=True)
        for source_kind, path in historical_files:
            if scanned >= args.scan_worklogs:
                break
            scanned += 1
            hits = _file_hits(path, pattern, args.hit_lines)
            if hits and str(path) not in seen:
                results.append((source_kind, _rel(root, path), hits))
                seen.add(str(path))
            if len(results) >= args.entries:
                break

    if not results:
        print("当前检索未找到证据；这不代表历史上从未发生。")
        return 0
    print(f"命中 {len(results)} 条历史证据：")
    labels = {"evolution": "进化经验", "memory": "历史索引", "plan": "需求与计划", "worklog": "工作日志"}
    for idx, (kind, title, hits) in enumerate(results, 1):
        print(f"\n{idx}. [{labels[kind]}] {title}")
        for line in hits:
            print(f"- {line}")
    print("\n以上是历史记录或摘要；需要引用原文时，应继续定位原始记录，不能用推测补全。")
    return 0


def _message_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                value = item.get("text") or item.get("output_text")
                if isinstance(value, str):
                    parts.append(value)
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return ""


def _codex_messages(path: Path, root: Path) -> list[tuple[str, str, str]]:
    messages: list[tuple[str, str, str]] = []
    matched_project = False
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line_no, line in enumerate(handle, 1):
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if item.get("type") == "session_meta":
                    cwd = item.get("payload", {}).get("cwd")
                    matched_project = bool(cwd and Path(cwd).expanduser().resolve() == root)
                    continue
                if not matched_project or item.get("type") != "response_item":
                    continue
                payload = item.get("payload", {})
                if payload.get("type") != "message" or payload.get("role") not in ("user", "assistant"):
                    continue
                text = _message_text(payload.get("content"))
                if text:
                    messages.append((payload.get("role", "unknown"), text, f"line {line_no}"))
    except (OSError, json.JSONDecodeError):
        return []
    return messages


def _claude_messages(path: Path, root: Path) -> list[tuple[str, str, str]]:
    messages: list[tuple[str, str, str]] = []
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line_no, line in enumerate(handle, 1):
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                cwd = item.get("cwd")
                if not cwd or Path(cwd).expanduser().resolve() != root:
                    continue
                role = item.get("type")
                message = item.get("message", {})
                if role not in ("user", "assistant"):
                    role = message.get("role")
                if role not in ("user", "assistant"):
                    continue
                text = _message_text(message.get("content", item.get("content")))
                if text:
                    messages.append((role, text, f"line {line_no}"))
    except (OSError, json.JSONDecodeError):
        return []
    return messages


def _match_excerpt(text: str, pattern: re.Pattern[str], limit: int = 320) -> str:
    match = pattern.search(text)
    if not match:
        return ""
    start = max(0, match.start() - 100)
    end = min(len(text), match.end() + 180)
    return _clip(re.sub(r"\s+", " ", text[start:end]), limit)


def _history_candidates(directory: Path) -> list[Path]:
    return list(directory.rglob("*.jsonl"))


def cmd_history_search(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    pattern = _compile_pattern(args.query)
    if not args.history_dir:
        print("默认不读取本地会话。请先指定一个具体的历史目录，并向用户说明读取范围。")
        return 5
    history_root = Path(args.history_dir).expanduser().resolve()
    if not args.approved:
        print(f"需要用户确认读取目录：{history_root}；来源：{args.agent}；最多检查 {args.scan_files} 个会话文件。确认后才可加 --approved。")
        return 5
    if not history_root.is_dir():
        print(f"历史目录不存在：{history_root}")
        return 2
    active_ids = {
        value
        for value in (
            os.environ.get("CODEX_THREAD_ID"),
            os.environ.get("CODEX_SESSION_ID"),
            os.environ.get("CLAUDE_SESSION_ID"),
        )
        if value
    }
    label, reader = ("Codex", _codex_messages) if args.agent == "codex" else ("Claude Code", _claude_messages)
    sources = [
        (label, path, reader)
        for path in _history_candidates(history_root)
        if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(history_root)
        and not any(identifier in path.name for identifier in active_ids)
    ]
    matches: list[tuple[str, Path, str, str, str]] = []
    sources.sort(key=lambda item: item[1].stat().st_mtime if item[1].exists() else 0, reverse=True)
    for agent, path, reader in sources[: args.scan_files]:
        if len(matches) >= args.entries:
            break
        for role, message, location in reader(path, root):
            excerpt = _match_excerpt(message, pattern)
            if excerpt:
                matches.append((agent, path, location, role, excerpt))
                if len(matches) >= args.entries:
                    break
        if len(matches) >= args.entries:
            break
    if not matches:
        print("当前原始会话检索未找到证据；这不代表历史上从未发生。")
        return 0
    print(f"命中 {len(matches)} 条原始会话证据：")
    for index, (agent, path, location, role, excerpt) in enumerate(matches, 1):
        print(f"\n{index}. [{agent} 原文] {path}#{location}；角色：{role}")
        print(f"- {excerpt}")
    print("\n以上内容来自用户本次确认的历史目录；引用结论时仍需结合日期、版本和当前适用范围。")
    return 0


def cmd_promote_evolution(args: argparse.Namespace) -> int:
    if not args.approved:
        print("只有用户明确确认可跨项目复用后，才能使用 --approved 晋升用户级经验。")
        return 2
    root = Path(args.root).resolve()
    layout = _layout(root, getattr(args, "store_dir", None))
    source = Path(args.source)
    if not source.is_absolute():
        source = root / source
    source = source.resolve()
    if source.parent != layout.evolution or source.name == "index.md" or not source.is_file():
        print("来源必须是当前项目 evolution/ 下的主题经验文件。")
        return 2
    problems = _validate_evolution(source)
    if problems:
        print("经验格式不完整：" + "；".join(problems))
        return 2
    if _evolution_status(source) == "已替代":
        print("已替代经验不能晋升为用户级经验。")
        return 2
    target_dir = _user_evolution_dir(args.user_evolution_dir)
    name = args.target_name or source.name
    if Path(name).name != name or Path(name).suffix != ".md" or name.lower() == "index.md":
        print("用户级经验必须使用独立的 .md 文件名，不能包含目录或覆盖 index.md")
        return 2
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / name
    if target.exists() and _canonical_experience(target) != _canonical_experience(source) and not args.replace:
        print(f"用户级经验已存在且内容不同：{target}；确认后使用 --replace。")
        return 2
    promoted = _canonical_experience(source)
    target.write_text(promoted, encoding="utf-8")
    index = target_dir / "index.md"
    if not index.exists():
        index.write_text("# 用户级进化经验索引\n\n## 有效经验\n\n", encoding="utf-8")
    index_text = _read_text(index)
    if target.name not in index_text:
        with index.open("a", encoding="utf-8") as handle:
            handle.write(f"- [{target.stem}]({target.name})；来源：{root}\n")
    print(f"已晋升用户级经验：{target}")
    return 0


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(["git", "-C", str(root), *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    return completed.stdout.strip()


def cmd_status(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    for title, content in (
        ("branch", _git(root, "status", "--short", "--branch")),
        ("name-status", _git(root, "diff", "--name-status", "HEAD")),
        ("stat", _git(root, "diff", "--stat", "HEAD")),
    ):
        print(f"## {title}")
        print(content or "(empty)")
    return 0


def _invalid_pending(memory: Path) -> list[str]:
    return [item for item in _section_items(memory, "## 未完成事项", None) if not all(key in item for key in ("状态：", "触发：", "完成：", "证据："))]


def cmd_coverage(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    store_dir = getattr(args, "store_dir", None)
    layout = _layout(root, store_dir)
    worklogs = _worklog_files(root, None, store_dir)
    plans = _plan_files(root, store_dir)
    memories = _memory_paths(root, store_dir)
    indexed = {target for memory in memories for target in _markdown_links(memory)}
    unindexed_plans = [path for path in plans if path not in indexed]
    unindexed_worklogs = [path for path in worklogs if path not in indexed]
    missing_summary = [path for path in worklogs if not _quick_summary_fields(path)]
    current_records = [path for path in [*plans, *worklogs] if path.is_relative_to(layout.store) and path not in _migrated_records(root, store_dir)]
    missing_session = [path for path in current_records if not _session_id(path)]
    evolution_files = [path for path in layout.evolution.glob("*.md") if path.name != "index.md"] if layout.evolution.is_dir() else []
    evolution_index = layout.evolution / "index.md"
    evolution_text = _read_text(evolution_index) if evolution_index.is_file() else ""
    indexed_evolution = set(_markdown_links(evolution_index)) if evolution_index.is_file() else set()
    unindexed_evolution = [path for path in evolution_files if path not in indexed_evolution]
    invalid_evolution = [(path, _validate_evolution(path)) for path in evolution_files if _validate_evolution(path)]
    identifiers: dict[str, list[Path]] = {}
    for path in evolution_files:
        identifier = _field_map(path).get("编号")
        if identifier:
            identifiers.setdefault(identifier, []).append(path)
    for scope, path in _evolution_files(root, None, store_dir):
        if scope == "user":
            identifier = _field_map(path).get("编号")
            if identifier and not any(_canonical_experience(p) == _canonical_experience(path) for p in identifiers.get(identifier, [])):
                identifiers.setdefault(identifier, []).append(path)
    duplicate_ids = {key: value for key, value in identifiers.items() if len(value) > 1}
    themes = {}
    for path in evolution_files:
        title = next((line[2:].strip() for line in _read_text(path).splitlines() if line.startswith("# ")), path.stem)
        if _evolution_status(path) != "已替代":
            themes.setdefault(title, []).append(path)
    duplicate_themes = {key: paths for key, paths in themes.items() if len(paths) > 1}
    invalid_plans = [(path, _validate_plan(path)) for path in plans if path.parent == layout.plans and path not in _migrated_records(root, store_dir) and _validate_plan(path)]
    broken_links: list[tuple[Path, Path]] = []
    for source in [*memories, evolution_index, *worklogs, *plans, *evolution_files]:
        if source and source.is_file():
            broken_links.extend((source, target) for target in _markdown_links(source) if not target.exists())
    invalid_pending = _invalid_pending(layout.memory) if layout.memory.is_file() else []
    counts = {
        "evolution_entry_missing": int(layout.memory.is_file() and evolution_index not in _markdown_links(layout.memory)),
        "plans_unindexed": len(unindexed_plans),
        "worklogs_unindexed": len(unindexed_worklogs),
        "missing_summary": len(missing_summary),
        "missing_session": len(missing_session),
        "evolution_unindexed": len(unindexed_evolution),
        "evolution_invalid": len(invalid_evolution),
        "duplicate_ids": len(duplicate_ids),
        "duplicate_themes": len(duplicate_themes),
        "plans_invalid": len(invalid_plans),
        "broken_links": len(broken_links),
        "pending_invalid": len(invalid_pending),
    }
    print("；".join(f"{key}={value}" for key, value in counts.items()))
    if args.details:
        groups = (
            ("Plans 未索引", unindexed_plans),
            ("Worklogs 未索引", unindexed_worklogs),
            ("缺少快速摘要", missing_summary),
            ("缺少会话标识", missing_session),
            ("进化经验未索引", unindexed_evolution),
        )
        for label, paths in groups:
            if paths:
                print(f"\n{label}（最多 {args.limit} 条）：")
                for path in paths[: args.limit]:
                    print(f"- {_rel(root, path)}")
        for path, problems in invalid_plans[: args.limit]:
            print(f"\n计划缺项：{path}：{';'.join(problems)}")
        for title, paths in duplicate_themes.items():
            print(f"\n同主题重复经验：{title}：{paths}")
        if counts["evolution_entry_missing"]:
            print("\n项目记忆缺少 evolution/index.md 入口")
        for path, problems in invalid_evolution[: args.limit]:
            print(f"\n进化经验格式错误：{_rel(root, path)}：{'；'.join(problems)}")
        for identifier, paths in list(duplicate_ids.items())[: args.limit]:
            print(f"\n重复经验编号 {identifier}：" + "、".join(_rel(root, path) for path in paths))
        for source, target in broken_links[: args.limit]:
            print(f"\n失效链接：{_rel(root, source)} → {_rel(root, target)}")
        for item in invalid_pending[: args.limit]:
            print(f"\n未完成事项缺少状态/触发/完成/证据字段：{item}")
    return 1 if any(counts.values()) else 0


def _save_report_error(message: str) -> int:
    print(f"Context Keeper 用户报告校验失败：{message}")
    return 2


def _previous_worklogs(root: Path, current: Path, store_dir: str | None = None) -> list[Path]:
    return [path for path in _worklog_files(root, None, store_dir) if path.resolve() != current.resolve()]


def cmd_save_report(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    store_dir = getattr(args, "store_dir", None)
    layout = _layout(root, store_dir)
    if args.worklog:
        worklog = Path(args.worklog)
        if not worklog.is_absolute():
            worklog = root / worklog
    else:
        worklogs = _worklog_files(root, 1, store_dir)
        if not worklogs:
            return _save_report_error("未找到工作日志")
        worklog = worklogs[-1]
    worklog = worklog.resolve()
    if not worklog.is_file():
        return _save_report_error(f"工作日志不存在：{_rel(root, worklog)}")
    if worklog in _migrated_records(root, store_dir):
        return _save_report_error("迁移历史不能作为本轮保存记录；请新建日志")
    if worklog.is_relative_to(layout.worklogs):
        if not args.session_id:
            return _save_report_error("新目录工作日志必须提供 --session-id")
        if _session_id(worklog) != args.session_id:
            return _save_report_error("当前会话不能保存其他会话的工作日志")
    if args.session_id:
        problems = _check_baseline(root, args.session_id)
        for plan in _plan_files(root, store_dir):
            if _session_id(plan) == args.session_id:
                problems.extend(f"{plan.name}：{issue}" for issue in _validate_plan(plan))
        if problems:
            return _save_report_error("；".join(problems[:5]))
    if layout.memory.is_file() and layout.evolution / "index.md" not in _markdown_links(layout.memory):
        return _save_report_error("项目记忆缺少进化经验索引入口")
    fields = _quick_summary_fields(worklog)
    missing = [name for name in ("类型", "完成", "下一步", "文件") if not fields.get(name)]
    if missing:
        return _save_report_error("快速摘要缺少字段：" + "、".join(missing))
    visible_items, no_extra = _user_visible_items(worklog)
    if not visible_items and not no_extra:
        return _save_report_error("工作日志缺少“给用户看的增量认知”")
    if visible_items and no_extra:
        return _save_report_error("不能同时写增量认知和“无新增提醒”")
    if len(visible_items) > 3:
        return _save_report_error("“给用户看的增量认知”最多 3 条")
    if any(not value for _, _, value in visible_items):
        return _save_report_error("每条增量认知都必须说明影响")
    if any(len(content) > 120 for _, content, _ in visible_items):
        return _save_report_error("单条增量认知不能超过 120 字")
    if any(len(impact) > 80 for _, _, impact in visible_items):
        return _save_report_error("单条影响不能超过 80 字")
    previous_logs = _previous_worklogs(root, worklog, store_dir)[-20:]
    previous_text = "\n".join(_read_text(path) for path in previous_logs)
    repeated = [content for _, content, _ in visible_items if content in previous_text]
    if repeated:
        return _save_report_error("增量认知与历史记录完全重复；请补充新证据或新场景，或改为无新增提醒")
    memories = _memory_paths(root, store_dir)
    if not memories:
        return _save_report_error("未找到 memory-keeper.md")
    if not any(worklog in _markdown_links(path) for path in memories):
        return _save_report_error("项目记忆中缺少指向本次工作日志的时间线条目")
    if layout.memory.is_file() and _invalid_pending(layout.memory):
        return _save_report_error("未完成事项必须包含状态、触发、完成和证据字段")
    broken_memory_links = [target for path in memories for target in _markdown_links(path) if not target.exists()]
    if broken_memory_links:
        return _save_report_error("项目记忆存在失效链接：" + "、".join(_rel(root, path) for path in broken_memory_links[:3]))
    notices = _evolution_notices(worklog)
    if len(notices) > 3:
        return _save_report_error("自我进化反馈最多三条，请合并同类反馈")
    if notices:
        link_groups = _notice_link_groups(worklog, notices)
        if any(len(group) != 1 for group in link_groups):
            return _save_report_error("每条自我进化记录必须且只能链接一个对应的 evolution 经验文件")
        notice_links = [group[0] for group in link_groups]
        missing_links = [path for path in notice_links if not path.is_file()]
        if missing_links:
            return _save_report_error("自我进化经验文件不存在：" + "、".join(_rel(root, path) for path in missing_links))
        invalid = [(path, _validate_evolution(path)) for path in notice_links if _validate_evolution(path)]
        if invalid:
            return _save_report_error("自我进化经验字段不完整：" + "、".join(_rel(root, path) for path, _ in invalid))
        for (kind, _), link in zip(notices, notice_links):
            if kind == "已沉淀" and any(old_kind == "已沉淀" and link in _notice_links(old, [(old_kind, content)]) for old in previous_logs for old_kind, content in _evolution_notices(old)):
                return _save_report_error("同一经验已经沉淀过；请记录本次复用或修正，不要重复宣称沉淀")
    print("已保存上下文。")
    if no_extra:
        print("\n本轮未发现需要额外提醒的盲点或隐患。")
    else:
        print("\n你可能还没意识到：")
        for index, (kind, content, impact) in enumerate(visible_items, 1):
            print(f"{index}. [{kind}] {content}")
            print(f"   影响：{impact}")
    if notices:
        print("\n自我进化：")
        for kind, content in notices:
            print(f"- {kind}：{content}")
    print("\n详细内容：")
    print(f"- 工作日志：[{_rel(root, worklog)}]({_rel(root, worklog)})")
    print(f"- 项目记忆：[{_rel(root, memories[0])}]({_rel(root, memories[0])})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Context Keeper bounded probes")
    sub = parser.add_subparsers(dest="command", required=True)
    migrate = sub.add_parser("migrate", help="预览旧版迁移；用户确认后使用 --approved")
    migrate.add_argument("--root", default=".")
    migrate.add_argument("--store-dir", help="自定义迁移目标目录；默认自动发现")
    migrate.add_argument("--approved", action="store_true")
    migrate.set_defaults(func=cmd_migrate)
    init = sub.add_parser("init", help="初始化或迁移 Context Keeper 记录目录")
    init.add_argument("--root", default=".")
    init.add_argument("--store-dir", help="自定义记录目录；默认 docs/context-keeper（需要 --approved 确认）")
    init.add_argument("--migrate", action="store_true", help="显式迁移已有记录到新目录")
    init.add_argument("--approved", action="store_true", help="确认使用默认记录位置；不带 --store-dir 时必填")
    init.set_defaults(func=cmd_init)
    record_path = sub.add_parser("record-path", help="按会话边界创建 plan/worklog 文件")
    record_path.add_argument("--root", default=".")
    record_path.add_argument("--store-dir", help="显式指定记录目录；默认自动发现")
    record_path.add_argument("--kind", choices=["plan", "worklog"], required=True)
    record_path.add_argument("--title", required=True)
    record_path.add_argument("--session-id", required=True)
    record_path.add_argument("--date", help="YYYY-MM-DD；默认今天")
    record_path.set_defaults(func=cmd_record_path)
    record_guard = sub.add_parser("record-guard", help="写入前校验会话边界")
    record_guard.add_argument("--root", default=".")
    record_guard.add_argument("--store-dir", help="显式指定记录目录；默认自动发现")
    record_guard.add_argument("--path", required=True)
    record_guard.add_argument("--session-id", required=True)
    record_guard.set_defaults(func=cmd_record_guard)
    resume = sub.add_parser("resume", help="输出轻量续接摘要")
    resume.add_argument("--root", default=".")
    resume.add_argument("--store-dir", help="显式指定记录目录；默认自动发现")
    resume.add_argument("--query", help="当前任务关键词，用于筛选相关未完成事项和经验")
    resume.add_argument("--worklogs", type=int, default=3)
    resume.add_argument("--entries", type=int, default=5)
    resume.add_argument("--pending", type=int, default=5)
    resume.add_argument("--kind", choices=["feature", "bugfix", "refactor", "research", "config"])
    resume.add_argument("--details", action="store_true")
    resume.add_argument("--full", action="store_true")
    resume.set_defaults(func=cmd_resume)
    search = sub.add_parser("search", help="分层查找历史证据和进化经验")
    search.add_argument("--root", default=".")
    search.add_argument("--store-dir", help="显式指定记录目录；默认自动发现")
    search.add_argument("--query", required=True)
    search.add_argument("--entries", type=int, default=5)
    search.add_argument("--evolution-entries", type=int, default=3)
    search.add_argument("--hit-lines", type=int, default=3)
    search.add_argument("--scan-worklogs", type=int, default=200)
    search.add_argument("--user-evolution-dir", help=argparse.SUPPRESS)
    search.set_defaults(func=cmd_search)
    history = sub.add_parser("history-search", help="经用户逐目录确认后读取原始会话")
    history.add_argument("--root", default=".")
    history.add_argument("--query", required=True)
    history.add_argument("--agent", choices=["codex", "claude"], required=True)
    history.add_argument("--history-dir", help="本次获准读取的唯一历史目录")
    history.add_argument("--approved", action="store_true", help="用户已明确同意读取该目录")
    history.add_argument("--entries", type=int, default=5)
    history.add_argument("--scan-files", type=int, default=500)
    history.set_defaults(func=cmd_history_search)
    promote = sub.add_parser("promote-evolution", help="经用户确认后晋升跨项目经验")
    promote.add_argument("--root", default=".")
    promote.add_argument("--store-dir", help="显式指定记录目录；默认自动发现")
    promote.add_argument("--source", required=True)
    promote.add_argument("--approved", action="store_true")
    promote.add_argument("--replace", action="store_true")
    promote.add_argument("--target-name")
    promote.add_argument("--user-evolution-dir", help=argparse.SUPPRESS)
    promote.set_defaults(func=cmd_promote_evolution)
    status = sub.add_parser("status", help="输出 git 状态、文件名和 stat")
    status.add_argument("--root", default=".")
    status.set_defaults(func=cmd_status)
    coverage = sub.add_parser("coverage", help="检查索引、摘要、会话、经验字段和链接")
    coverage.add_argument("--root", default=".")
    coverage.add_argument("--store-dir", help="显式指定记录目录；默认自动发现")
    coverage.add_argument("--limit", type=int, default=20)
    coverage.add_argument("--details", action="store_true")
    coverage.set_defaults(func=cmd_coverage)
    save_report = sub.add_parser("save-report", help="校验保存产物并生成精简用户报告")
    save_report.add_argument("--root", default=".")
    save_report.add_argument("--store-dir", help="显式指定记录目录；默认自动发现")
    save_report.add_argument("--worklog", help="工作日志路径；默认使用最新工作日志")
    save_report.add_argument("--session-id", help="新目录记录必须传入当前会话标识")
    save_report.set_defaults(func=cmd_save_report)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "history-search" and not args.approved:
            return int(args.func(args))
        root = Path(args.root).resolve()
        if args.command != "migrate" and _legacy_sources(root):
            return _migration_warning(root)
        return int(args.func(args))
    except ValueError as exc:
        print(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
