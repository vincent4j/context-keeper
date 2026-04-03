# context-keeper

Claude Code skill — 对话上下文管理工具，帮助在多个对话之间保持项目上下文的连续性。

## 背景

Claude Code 的每次对话都是独立的，无法自动感知上次做了什么。常见解法是把项目状态写进 `CLAUDE.md`，但这会导致每次对话都自动加载大量内容，浪费 token。

`context-keeper` 采用**按需加载**策略：
- 结束工作时，保存一份精简摘要（~150 tokens）到工作日志末尾
- 开启新对话时，只读这份摘要，快速恢复状态
- 需要深入了解时，再按需加载完整文档

## 功能

- **保存上下文**：分析对话历史和 git 变更，生成需求文档（`docs/plans/`）和工作日志（`docs/worklog/`），并按需更新 README 等相关文档
- **加载上下文**：只读取最新工作日志的"快速摘要"章节（~150 tokens），快速恢复项目状态

## 安装

```bash
git clone https://github.com/vincent4j/context-keeper ~/.claude/skills/context-keeper
```

或软链接（推荐，修改后立即生效）：

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
- `2` — 加载最近一次的工作摘要

## 生成的文件

**保存操作**会在项目中生成以下文件（文件名含时间戳，支持同一天多次保存）：

```
docs/
├── plans/
│   └── YYYY-MM-DD-HHmm-[功能模块]需求.md     # 需求文档（7 章节）
└── worklog/
    └── YYYY-MM-DD-HHmm-[功能模块].md          # 工作日志（7 章节 + 快速摘要）
```

**快速摘要**格式（写在工作日志末尾，~150 tokens）：

```markdown
## 快速摘要（用于下次对话）

**完成：** 一句话描述完成的工作
**问题：** 遇到的主要问题及解决方案
**下一步：** 下一步计划
**文件：** 新增/修改的关键文件
```

## Token 消耗对比

| 场景 | 方案 | Token 消耗 |
|------|------|-----------|
| 每次对话自动加载 | CLAUDE.md | 2000–5000 tokens |
| 新对话恢复状态 | context-keeper 加载 | ~150 tokens |
| 需要完整历史 | 按需加载工作日志 | ~2000 tokens |
| 需要完整需求 | 按需加载需求文档 | ~3000 tokens |

## 文件结构

```
context-keeper/
├── SKILL.md          # Skill 主文件（Claude Code 读取）
└── README.md
```
