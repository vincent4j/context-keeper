#!/usr/bin/env python3
"""Build a source-only Skill ZIP from an explicit file list."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "SKILL.md",
    "README.md",
    "scripts/install.py",
    "scripts/context_keeper_probe.py",
    "references/save.md",
    "references/resume.md",
    "references/install.md",
    "references/migrate.md",
    "references/search.md",
)
MAX_BYTES = 20_971_520


def build() -> Path:
    manifest_path = ROOT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("type") != "skill" or manifest.get("code") != "context-keeper":
        raise ValueError("manifest 类型或 code 错误")
    if not isinstance(manifest.get("runtimeTargets"), list) or len(manifest.get("examplePrompts", [])) < 3:
        raise ValueError("manifest 缺少 runtimeTargets 或至少三条 examplePrompts")

    contents = {}
    for name in FILES:
        path = ROOT / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"源码文件缺失：{name}")
        contents[name] = path.read_bytes()
    manifest["files"] = [
        {"path": name, "sha256": hashlib.sha256(data).hexdigest()}
        for name, data in contents.items()
    ]
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    manifest_path.write_bytes(manifest_bytes)

    output = ROOT / "dist" / f"context-keeper-{manifest['version']}.zip"
    output.parent.mkdir(exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for name, data in (("manifest.json", manifest_bytes), *contents.items()):
            info = ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)

    with ZipFile(output) as archive:
        expected = {"manifest.json", *FILES}
        if set(archive.namelist()) != expected:
            raise ValueError("ZIP 包含未声明文件或缺少必要文件")
        for entry in manifest["files"]:
            if hashlib.sha256(archive.read(entry["path"])).hexdigest() != entry["sha256"]:
                raise ValueError(f"ZIP 文件哈希不匹配：{entry['path']}")
    size = output.stat().st_size
    if size > MAX_BYTES:
        raise ValueError("ZIP 超过 20 MiB")
    print(json.dumps({"zip": str(output), "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                      "sizeBytes": size, "files": len(FILES)}, ensure_ascii=False))
    return output


if __name__ == "__main__":
    build()
