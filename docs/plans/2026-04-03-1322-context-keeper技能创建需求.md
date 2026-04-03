# context-keeper 技能创建需求文档

**创建日期：** 2026-04-03
**项目：** context-keeper
**功能模块：** context-keeper 技能创建与发布

## 一、需求概述

需要一个 Claude Code skill，在每次 session 工作结束时自动生成文档（需求文档、工作日志）并更新项目相关文档，同时支持在开启新对话时快速加载上次的工作摘要，且 token 消耗尽可能少。

核心诉求：
1. Session 结束时保存上下文：生成需求文档、工作日志，更新 README 等相关文档
2. 新对话快速恢复状态：只加载精简摘要（~150 tokens），按需再加载完整文档
3. 支持同一天多次保存：文件名含时间戳（HHmm），每次独立快照

## 二、功能结构

```
/context-keeper
├── 操作 1：保存上下文
│   ├── 分析对话历史 + git 变更
│   ├── 生成需求文档（docs/plans/）
│   ├── 生成工作日志（docs/worklog/，含快速摘要）
│   ├── 按需更新相关文档（README、architecture 等）
│   └── 询问是否提交并推送代码
└── 操作 2：加载上下文
    ├── 查找最新工作日志
    ├── 只读"快速摘要"章节（~150 tokens）
    └── 按需加载完整文档
```

## 三、数据来源

- 对话历史：提取任务目标、技术决策、问题解决过程
- Git 变更：`git status`、`git diff HEAD`、`git log --oneline -10`

## 四、技术要求

- Skill 文件：`~/.claude/skills/context-keeper/SKILL.md`
- 文件命名格式：`YYYY-MM-DD-HHmm-[功能模块].md`
- 快速摘要：控制在 100–150 tokens
- 不使用 CLAUDE.md，避免自动加载

## 五、设计要求

- 交互简洁：展示菜单，用户输入 1 或 2 即可
- 错误友好：git 失败、目录不存在等情况给出明确提示
- 通用性：不绑定特定项目，适用于任何有 `docs/worklog/` 和 `docs/plans/` 目录的项目

## 六、验证标准

- `/context-keeper` 正确展示菜单
- 操作 1 生成文档格式正确，含快速摘要
- 操作 2 只读快速摘要，token < 200
- 保存结束后询问是否提交推送
- 错误情况有友好提示

## 七、参考资料

- Skill 文件：`SKILL.md`
- GitHub 仓库：https://github.com/vincent4j/context-keeper
- 技能创建指南：`superpowers:writing-skills`
