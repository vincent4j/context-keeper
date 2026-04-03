# context-keeper

Claude Code skill — 对话上下文管理工具，帮助在多个对话之间保持项目上下文的连续性。

## 功能

- **保存上下文**：分析对话历史和 git 变更，生成需求文档和工作日志，并按需更新相关文档
- **加载上下文**：只读取最新工作日志的快速摘要（~150 tokens），快速恢复项目状态

## 安装

```bash
cp -r . ~/.claude/skills/context-keeper
```

或软链接（推荐，修改后立即生效）：

```bash
ln -s $(pwd) ~/.claude/skills/context-keeper
```

## 使用

在 Claude Code 中输入：

```
/context-keeper
```

然后选择：
- `1` — 保存当前对话的工作上下文
- `2` — 加载最近一次的工作摘要

## 文件结构

```
context-keeper/
├── SKILL.md          # Skill 主文件
└── README.md
```
