# Context Keeper

Context Keeper 帮助本地 Agent 保存项目进度、继续上次工作、查找有证据的历史事实，并把用户纠正或已验证的新结果沉淀为以后可以复用的经验。

它按需读取：普通新需求不查历史；需要追溯时先查索引和少量项目记录，关键判断仍缺证据时才检索原始会话。

## 功能

- 保存用户需求、实施计划、工作结果和未完成事项。
- 续接最近 3 份工作摘要和最多 5 条相关经验。
- 自动从当前上下文提取关键词，分层查找进化经验、历史索引、plans 和 worklogs。
- 按项目定位 Codex 和 Claude Code 原始会话，避免用猜测代替过去事实。
- 用户纠正或出现已验证的新结果时沉淀到 `evolution/`，实际复用后在对话中告知用户。
- 同一会话可以更新同一记录；跨会话由脚本创建新记录，交付检查发现旧记录改写或删除时阻断完成报告。
- 支持项目经验经用户明确批准后晋升为用户级跨项目经验。
- 支持 Codex 和 Claude Code 的用户级、项目级安装、入口配置和卸载。

## 项目记录

第一次保存时默认创建：

```text
context-keeper/
├── memory-keeper.md
├── plans/
│   └── YYYY-MM-DD-中文主题.md
├── worklogs/
│   └── YYYY-MM-DD-中文主题.md
└── evolution/
    ├── index.md
    └── 中文主题.md
```

自定义位置：

```bash
python3 scripts/context_keeper_probe.py init --root <repo> --store-dir <path>
```

已有记录改位置必须显式迁移：

```bash
python3 scripts/context_keeper_probe.py init \
  --root <repo> --store-dir <path> --migrate
```

选择记录在项目根目录的 `context-keeper.json`。目标目录非空时迁移停止，避免产生两套事实源。旧版 `docs/plans/`、`docs/worklog/`、`docs/worklogs/` 和 `docs/memory-keeper.md` 继续可读，不自动迁移。

## 安装与入口

用户级安装，对当前用户的项目生效：

```bash
python3 scripts/install.py --all
```

项目级安装：

```bash
python3 scripts/install.py --project <repo> --all
```

只配置自动入口：

```bash
python3 scripts/install.py --all --bridge-only
```

卸载 Skill 和自身入口区块：

```bash
python3 scripts/install.py --all --uninstall
```

可以用 `--codex` 或 `--claude` 只处理一个 Agent。安装器会分别报告 Skill、入口和移除结果，重复运行不会重复追加。其他 Agent 只有在其规则入口和 Skill 目录经过实际验证后才能宣称支持。

## 主要命令

```bash
# 初始化
python3 scripts/context_keeper_probe.py init --root <repo>

# 创建当前会话拥有的记录
python3 scripts/context_keeper_probe.py record-path --root <repo> \
  --kind plan --title '中文主题' --session-id '<session-id>'

# 编辑前防止跨会话覆盖
python3 scripts/context_keeper_probe.py record-guard --root <repo> \
  --path <record> --session-id '<session-id>'

# 轻量续接并筛选当前相关事项
python3 scripts/context_keeper_probe.py resume --root <repo> --query '<关键词>'

# 分层历史搜索
python3 scripts/context_keeper_probe.py search --root <repo> --query '<关键词>'

# 关键判断需要原文时搜索原始会话
python3 scripts/context_keeper_probe.py history-search --root <repo> --query '<关键词>'

# 用户批准后晋升跨项目经验
python3 scripts/context_keeper_probe.py promote-evolution --root <repo> \
  --source <evolution-file> --approved

# 一行覆盖检查；加 --details 才展开
python3 scripts/context_keeper_probe.py coverage --root <repo>

# 保存交付校验
python3 scripts/context_keeper_probe.py save-report --root <repo> \
  --worklog <worklog> --session-id '<session-id>'
```

## 自我进化边界

Context Keeper 不自动修改自己的代码。它更新项目 `evolution/` 中的经验数据：编号、状态、触发条件、已知事实、证据、建议动作和适用范围。

只有用户明确纠正、失败后出现可核验的新结果，或旧经验被新证据修正时才沉淀。搜索排除已替代经验，待验证经验不会包装成成功结论。同一经验已经沉淀后只能报告复用或修正，不能再次宣称首次学会。

经验命中不等于已经复用，复用也不等于已经有效。只有经验实际改变本次判断或动作时才报告“本次复用”，只有本轮结果提供证据时才报告有效。

## Token 控制

- 续接：3 份短摘要，最多 5 条相关经验。
- 进化经验：最多 3 个候选。
- 搜索总候选：最多 5 个，只展开 1～2 份。
- 原始会话：先按项目和关键词定位，只输出有限片段。
- 覆盖检查：默认一行计数，详情按需展开。
- 同一问题本轮只查一次；普通任务不查历史。

## 已验证范围

Codex/gpt-6-astra 的本次行为用例通过。本机 Claude Code/MiniMax-M3 显式保存可用，但自动沉淀未通过，检索读取量也未严格遵守约束。原生 Claude 验收由用户决定延期。安装成功不等于所有模型均能可靠自动执行；完整结果保存在源码仓库的 `acceptance-review.md` 和 `behavior-verification.md`。

## 验证

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```
