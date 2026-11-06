#!/usr/bin/env python3
"""Look up one explicitly opted-in project experience before a known operation."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import context_keeper_probe as probe


HOSTS = ("codex", "claude", "workbuddy", "zcode", "dsh", "opencode")
INDEX_BYTES = 32 * 1024
MAX_CANDIDATES = 24


def _local_link(base: Path, raw: str, allowed: Path) -> Path | None:
    raw = raw.partition("#")[0]
    if not raw or raw.startswith("//") or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", raw):
        return None
    target = (base / raw).resolve()
    if target.is_relative_to(allowed) and target.is_file():
        return target
    return None


def _indexed_entries(index: Path):
    with index.open("rb") as stream:
        data = stream.read(INDEX_BYTES + 1)
    if len(data) > INDEX_BYTES:
        data = data[:INDEX_BYTES].rpartition(b"\n")[0]  # omit an incomplete last index row
    seen = set()
    for line in data.decode("utf-8").splitlines():
        if line.strip() == "## 已替代经验":
            break
        for enclosed, bare in probe.LOCAL_LINK_RE.findall(line):
            entry = _local_link(index.parent, enclosed or bare, index.parent)
            if not entry or entry == index or entry.parent != index.parent or entry.suffix != ".md" or entry in seen:
                continue
            seen.add(entry)
            yield entry
            if len(seen) >= MAX_CANDIDATES:
                return


def _hint(entry: Path, root: Path, trigger: tuple[str, str, str]) -> dict | None:
    if entry.stat().st_size > 4 * probe.EVOLUTION_MAX_CHARS:
        return None
    fields = probe._field_map(entry)
    selector = tuple(item.strip() for item in fields.get("操作前提示", "").split("|"))
    if selector != trigger or fields.get("状态") != "已验证" or probe._validate_evolution(entry):
        return None
    evidence = []
    for enclosed, bare in probe.LOCAL_LINK_RE.findall(fields["证据位置"]):
        source = _local_link(entry.parent, enclosed or bare, root)
        if not source or source.is_relative_to(entry.parent):
            return None
        evidence.append(str(source.relative_to(root)))
    if not evidence:
        return None
    return {"id": fields["编号"], "check": fields["建议动作"], "experience": str(entry.relative_to(root)),
            "evidence": list(dict.fromkeys(evidence))}


def find_hint(root: Path, action: str, host: str, scope: str, store_dir: str | None = None) -> dict | None:
    """Best-effort lookup. A miss or broken memory never changes the operation's outcome."""
    if action != "uninstall-skill" or host not in HOSTS or scope not in ("project", "user"):
        return None
    try:
        root = Path(root).resolve()
        config = root / probe.CONFIG_FILE
        if config.is_symlink() or (config.exists() and (not config.is_file() or config.stat().st_size > INDEX_BYTES)):
            return None
        if probe._legacy_sources(root):
            return None
        layout = probe._layout(root, store_dir)
        if not layout.store.is_relative_to(root) or not layout.memory.resolve().is_relative_to(layout.store):
            return None
        index = (layout.evolution / "index.md").resolve()
        if not layout.memory.is_file() or index != layout.store / "evolution/index.md" or not index.is_file():
            return None
        for entry in _indexed_entries(index):
            hint = _hint(entry, root, (action, host, scope))
            if hint:
                return hint
    except (OSError, RuntimeError, ValueError):  # unreadable data, symlink loop, ambiguous or invalid store
        return None
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--action", choices=["uninstall-skill"], required=True)
    parser.add_argument("--host", choices=HOSTS, required=True)
    parser.add_argument("--scope", choices=["project", "user"], required=True)
    parser.add_argument("--store-dir")
    args = parser.parse_args(argv)
    hint = find_hint(args.root, args.action, args.host, args.scope, args.store_dir)
    if hint:
        print(json.dumps(hint, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
