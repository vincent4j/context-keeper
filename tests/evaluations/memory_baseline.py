"""Controlled CLI evidence probes, not a model-behavior or production benchmark.
Run: python3 tests/evaluations/memory_baseline.py --output /absolute/new/directory
"""
import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[2]
PROBE = REPO / 'scripts/context_keeper_probe.py'


def write(root, name, text):
    p = root / 'docs/context-keeper' / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding='utf-8')


def digest(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def build(root, case):
    write(root, 'evolution/index.md', '# 经验索引\n')
    write(root, 'memory-keeper.md', '# 项目记忆\n\n## 主题摘要（按类型）\n'
          '- **上传：** 413 已解决；来源：[旧验证](worklogs/2026-11-01-old.md)。\n'
          '\n## 未完成事项\n\n## 时间线（最新在前）\n')
    write(root, 'worklogs/2026-11-01-old.md', '# 上传旧验证\n上传 413：2 MB，入口限制修复后返回 200。\n')
    evidence = '上传 413：25 MB，入口已放行；上游仍返回 413，尚未修复。'
    if case == 'middle':
        evidence = ('上传 413：首次判断全部修复。\n' * 5 + '\n'.join('无关追加 %d' % i for i in range(100))
                    + '\n' + evidence + '\n' + '\n'.join('无关尾部 %d' % i for i in range(100)))
    elif case == 'valid':
        evidence = '上传 413：2 MB 在相同版本 v1 重测返回 200；无新增失败。'
    elif case == 'version':
        evidence = '上传 413：旧 v1 的2 MB返回200；新 v2 的25 MB返回413，不能推翻 v1 的2 MB结论。'
    elif case == 'duplicate':
        evidence = '上传 413：Codex 引用 run-001 的2 MB返回200；Claude 引用同一 run-001，不是第二次独立运行。'
    elif case == 'claim':
        evidence = '上传 413：Agent 判断全通过。\n工具结果：25 MB HTTP 413，exit=1。另一个生产验证未执行。'
    write(root, 'worklogs/2026-11-02-new.md', '# 后续记录\n' + evidence + '\n')
    if case == 'linked':
        write(root, 'memory-keeper.md', '# 项目记忆\n\n## 主题摘要（按类型）\n'
              '- **上传：** 413 已解决；来源：[后续记录](worklogs/2026-11-02-new.md)。\n'
              '\n## 未完成事项\n\n## 时间线（最新在前）\n')
    if case == 'saturated':
        for i in range(3):
            write(root, f'evolution/e{i}.md', f'# 上传经验{i}\n- **编号：** CK-{i}\n- **状态：** 已验证\n'
                  '- **触发条件：** 上传 413\n- **已知事实：** 2 MB 已通过\n'
                  '- **证据位置：** [旧验证](../worklogs/2026-11-01-old.md)\n'
                  '- **建议动作：** 使用入口修复\n- **适用范围：** 2 MB\n')
        write(root, 'memory-keeper.md', '# 项目记忆\n\n## 主题摘要（按类型）\n'
              '- **上传一：** 上传 413 入口已修复。\n- **上传二：** 上传 413 复测通过。\n'
              '\n## 未完成事项\n\n## 时间线（最新在前）\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    home=out/'isolated-home';home.mkdir(mode=0o700)
    child_env={'HOME':str(home),'CODEX_HOME':str(home/'.codex'),'PATH':os.defpath,'LANG':'en_US.UTF-8','PYTHONDONTWRITEBYTECODE':'1'}
    git=subprocess.run(['git','rev-parse','HEAD'],cwd=REPO,env=child_env,capture_output=True,text=True)
    protocol = {
        'cases': ['stale', 'middle', 'linked', 'saturated', 'valid', 'version', 'duplicate', 'claim'],
        'repetitions': 3, 'query': '上传 413', 'timeout_seconds_per_command': 10,
        'commands': ['resume', 'search'], 'budget': 'CLI defaults; search user evolution isolated empty',
        'primary_metric': 'direct evidence text visible; path alone is not evidence body',
        'safety': 'readonly fixture hash invariant; no agent memory writes',
        'semantic_evaluation': 'current reviewer directed read; not blind or fresh-session model trial',
        'deferred': ['natural no-history trigger', 'semantic save idempotency', 'fresh-session reliability'],
        'probe_sha256': hashlib.sha256(PROBE.read_bytes()).hexdigest(),
        'git_head': git.stdout.strip() if git.returncode==0 else None,
        'source_scope': 'Git commit when available; source exports are valid without Git',
        'child_home': 'new isolated-home under output; no user config or auth copied',
        'python': sys.version,
    }
    (out / 'protocol.json').write_text(json.dumps(protocol, ensure_ascii=False, indent=2))
    rows = []
    empty = out / 'empty-user-evolution'
    empty.mkdir()
    for case in protocol['cases']:
        root = out / 'fixtures' / case
        build(root, case)
        before = digest(root)
        for rep in range(3):
            for command in protocol['commands']:
                cmd = [sys.executable, str(PROBE), command, '--root', str(root), '--query', protocol['query']]
                if command == 'search':
                    cmd += ['--user-evolution-dir', str(empty)]
                started = time.perf_counter()
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, env=child_env)
                filename = f'{case}-{command}-{rep+1}.txt'
                (out / filename).write_text(result.stdout + result.stderr)
                rows.append({'case': case, 'command': command, 'repeat': rep+1,
                             'rc': result.returncode, 'elapsed_ms': round((time.perf_counter()-started)*1000, 2),
                             'output_file': filename, 'argv': cmd, 'readonly': before == digest(root),
                             'output_sha256': hashlib.sha256(result.stdout.encode()).hexdigest()})
    # Single-factor interventions: linked exclusion, hit-line cutoff, candidate saturation.
    for case, flags in [('middle', ['--hit-lines', '10']), ('saturated', ['--entries', '6'])]:
        cmd = [sys.executable, str(PROBE), 'search', '--root', str(out/'fixtures'/case),
               '--query', '上传 413', '--user-evolution-dir', str(empty)] + flags
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10, env=child_env)
        (out / f'{case}-expanded.txt').write_text(r.stdout+r.stderr)
    # The linked source is opened directly as a read-only diagnostic intervention.
    p = out/'fixtures/linked/docs/context-keeper/worklogs/2026-11-02-new.md'
    (out/'linked-opened.txt').write_text(p.read_text())
    unlinked = out / 'diagnostic-unlinked'
    shutil.copytree(out/'fixtures/linked', unlinked)
    memory = unlinked/'docs/context-keeper/memory-keeper.md'
    memory.write_text(memory.read_text().replace('[后续记录](worklogs/2026-11-02-new.md)', '后续记录'))
    cmd = [sys.executable, str(PROBE), 'search', '--root', str(unlinked), '--query',
           '上传 413', '--user-evolution-dir', str(empty)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, env=child_env)
    (out/'linked-unlinked.txt').write_text(result.stdout + result.stderr)
    (out/'results.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    print(json.dumps({'output': str(out), 'commands': len(rows),
                      'nonzero': sum(r['rc'] != 0 for r in rows),
                      'readonly': all(r['readonly'] for r in rows)}, ensure_ascii=False))

if __name__ == '__main__':
    main()
