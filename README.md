# context-keeper

Claude Code skill — 对话上下文管理工具，帮助在多个对话之间保持项目上下文的连续性。

## 设计理念

Claude Code 每次对话都是全新开始——它不记得上次做了什么，不知道踩过哪些坑，也不清楚下一步该往哪走。

常见的解法是把项目状态写进 `CLAUDE.md`，让它每次自动加载。但这意味着每次对话都要消耗 2000–5000 tokens，不管你这次是否真的需要那些信息。

context-keeper 的设计围绕两个核心原则：

**1. 跨会话记忆** — 每次工作结束时，把关键信息压缩成精简摘要存入工作日志，同时积累经验教训索引。下次开启新对话，立刻能看到最近几次做了什么、遇到了什么问题、学到了什么——就像有了持久记忆。

**2. 节省 token** — 采用按需加载策略。新对话默认只读最近 3 次摘要 + 近期经验（~750 tokens），需要深挖时再按需加载完整文档。相比 `CLAUDE.md` 方案，日常使用节省 70–90% 的上下文 token。

## 功能

- **保存上下文**：分析对话历史和 git 变更，生成需求文档（`docs/plans/`）和工作日志（`docs/worklog/`），更新经验教训索引（`docs/memory-keeper.md`），并按需更新 README 等相关文档
- **加载上下文**：读取最近 3 次工作日志的"快速摘要"章节 + 近期经验教训，快速恢复项目状态

## 安装

```bash
npx skills add vincent4j/context-keeper
```

或手动克隆：

```bash
git clone https://github.com/vincent4j/context-keeper ~/.claude/skills/context-keeper
```

软链接（推荐用于本地开发，修改后立即生效）：

```bash
git clone https://github.com/vincent4j/context-keeper ~/path/to/context-keeper
ln -s ~/path/to/context-keeper ~/.claude/skills/context-keeper
```

## 使用

在 Claude Code 中输入：

```
/context-keeper
```

然后选择：
- `1` — 保存当前对话的工作上下文
- `2` — 加载最近工作摘要

## 生成的文件

**保存操作**会在项目中生成/更新以下文件：

```
docs/
├── plans/
│   └── YYYY-MM-DD-[功能模块]需求.md        # 需求文档（7 章节）
├── worklog/
│   └── YYYY-MM-DD-[功能模块].md             # 工作日志（7 章节 + 快速摘要）
└── memory-keeper.md                        # 经验教训索引（主题摘要 + 时间线）
```

同一对话多次保存覆盖同一文件；文件名冲突时末尾加序号（`-2`、`-3`）。

**快速摘要**格式（写在工作日志末尾，~150 tokens）：

```markdown
## 快速摘要（用于下次对话）

**类型：** feature | 项目：my-project
**完成：** 一句话描述完成的工作
**问题：** 遇到的主要问题及解决方案（事实描述）
**经验：** 学到了什么 + 下次怎么做（经验提炼）
**下一步：** 下一步计划
**文件：** 新增/修改的关键文件
```

类型：`feature`（新功能）/ `bugfix`（问题修复）/ `refactor`（重构优化）/ `research`（调研探索）/ `config`（配置环境）

**经验教训索引**（`docs/memory-keeper.md`）结构：

```markdown
## 主题摘要（按类型）

**bugfix（N条）：** 关键词1，关键词2，关键词3
**refactor（N条）：** 关键词1，关键词2

## 时间线（最新在前）

## YYYY-MM-DD - [功能模块] `[类型]`
- **经验：** 关键经验，分号分隔
- **详见：** [worklog/...](...)
```

## Token 消耗对比

| 场景 | 方案 | Token 消耗 |
|------|------|-----------|
| 每次对话自动加载 | CLAUDE.md | 2000–5000 tokens |
| 新对话恢复状态（默认） | context-keeper 加载 | ~750 tokens |
| 需要完整历史 | 按需加载工作日志 | ~2000 tokens |
| 需要完整需求 | 按需加载需求文档 | ~3000 tokens |

## 文件结构

```
context-keeper/
├── SKILL.md          # Skill 主文件（Claude Code 读取）
└── README.md
```

## 更新日志

### v0.1.0 — 2026-05-15

首次发布。

- 保存上下文：生成需求文档、工作日志，更新经验教训索引（`docs/memory-keeper.md`）
- 加载上下文：读取最近 3 次工作摘要 + 近期经验教训（~750 tokens）
- 快速摘要支持类型标签（feature/bugfix/refactor/research/config）
- 经验教训索引支持主题摘要区块（按类型聚合）和时间线
- 支持 `npx skills add vincent4j/context-keeper` 安装
