---
name: context-keeper
description: 保存进度、续接上下文、检索经验；保存并提交或推送时，提炼用户可能尚未意识到的复盘、隐患和决策影响，避免复述已知进度
---

# Context Keeper — 对话上下文管理工具

帮助你在多个对话之间保持项目上下文的连续性。支持保存当前对话的工作成果、在新对话中继续上次进度，也支持按当前问题查找历史相似经验。

## Token 预算与读取纪律

Context Keeper 的目标是轻量续接，不是全仓回放。默认先看文件名、标题、摘要和统计，再按需读取小段正文。

- `rg` / `find` 只先用于定位文件和条目，不当正文读取器。
- 不默认运行 `rg '<关键词>' .`、`rg --hidden '<关键词>' .`、`cat docs/memory-keeper.md`、`cat docs/worklog/*.md`、未过滤的大段日志读取或未限定文件的 `git diff HEAD`。
- 工作日志默认只读最近 3 个文件的"快速摘要"；项目记忆默认只读"主题摘要"和最多 5 条时间线条目。
- 单次正文读取通常不超过 80 行；如果需要更多，先说明原因并按文件/章节继续分段读取。
- API 响应、sidecar logs、browser logs、测试产物和大型 JSON 先落盘到 `/tmp/<project>-*`，对话里只输出关键统计、路径和少量摘录。
- 优先运行 `scripts/context_keeper_probe.py` 的 `resume` / `search` / `status` 子命令获取限量输出；脚本不满足时再手工 `rg` / `sed` 小段读取。

## 按操作加载

先判断用户要执行的操作，只读取对应 reference，不预读其他操作说明。

- 保存本次上下文：先运行 `scripts/context_keeper_probe.py status --root <repo>`，再读取 `references/save.md`
- 继续上次进度：优先运行 `scripts/context_keeper_probe.py resume --root <repo>`，需要细节时再读取 `references/resume.md`
- 查找相似经验：优先运行 `scripts/context_keeper_probe.py search --root <repo> --query '<关键词>'`，需要细节时再读取 `references/search.md`

## 交互菜单

当用户只调用 `/context-keeper` 或 `context keeper`，且没有说明具体动作时，展示以下菜单：

```
Context Keeper - 保存进度、延续上下文、查找历史经验的项目记忆助手

功能：
1. 保存本次上下文 — 生成需求文档、工作日志，并更新项目记忆
2. 继续上次进度 — 读取最近工作摘要和近期经验
3. 查找相似经验 — 基于当前会话或用户描述检索历史经验

也可以直接输入：
- context keeper 保存
- context keeper 继续
- context keeper 查找

请选择操作（输入 1-3）：
```

等待用户输入，然后执行对应操作。

直接命令映射：

- `context keeper 保存` / `context-keeper 保存`：直接执行操作 1。
- `context keeper 继续` / `context-keeper 继续`：直接执行操作 2。
- `context keeper 查找` / `context-keeper 查找` / “我记得这个问题以前遇到过，帮我查一下”：直接执行操作 3。

---

## 操作 1：保存本次上下文

读取 `references/save.md` 并执行。不要预读 `references/resume.md` 或 `references/search.md`。

保存操作有不可跳过的用户可见复盘门禁：

1. 工作日志必须包含“给用户看的增量认知”，只写用户可能尚未意识到的盲点、复盘、隐患、决策影响或合同候选；不要复述完成项、测试结果、文件清单和 Git 状态。
2. 文档写入后运行 `scripts/context_keeper_probe.py save-report --root <repo> --worklog <worklog>`。
3. 命令非 0 时停止，不得提交、推送或宣称保存完成。
4. 用户尚未授权提交时，将增量认知与提交询问一起输出；用户已明确要求提交或推送时，内部保留校验结果，不在 commentary 重复输出。
5. 最终回复只输出一次增量认知，并附最短必要 Git 结果。只给文件链接或只报告 commit/push 均不算完成；不得复述用户已经知道的进度。

---

## 操作 2：继续上次进度

读取 `references/resume.md` 并执行。不要预读保存模板或查找流程。

---

## 操作 3：查找相似经验

读取 `references/search.md` 并执行。不要预读保存模板或续接流程。

---

## 上下文优化原则

- **不使用 CLAUDE.md**：避免每次对话自动加载大量内容
- **分层加载**：
  - 继续上次进度默认加载最近 3 次快速摘要（约 450 个上下文 token）+ 主题摘要区块（约 150 个上下文 token）+ 近期经验 5 条（约 150 个上下文 token）≈ 750 个上下文 token
  - 按需加载完整工作日志（约 2000 个上下文 token）
  - 按需加载需求文档（约 3000 个上下文 token）
- **先索引再读取**：
  - `find` / `rg --files` / `rg -n -m` 用来定位文件、标题和少量命中行
  - `sed -n` / scoped `awk` 用来读取确定需要的小段内容
  - 命中过多时先收窄关键词，不用扩大读取范围来碰运气
- **项目记忆索引**：
  - 主题摘要区块提供类型级别的快速概览（约 150 个上下文 token）
  - 按类型过滤后只加载相关经验，节省 50-80% 上下文 token
  - 查找相似经验时，全文件范围搜索 `memory-keeper.md`，只读取命中条目，不受最近条目限制

---

## 错误处理

- 找不到 `docs/worklog/` 目录或为空 → 提示用户尚无工作日志，建议先执行保存操作
- 找不到 `docs/memory-keeper.md` → 查找相似经验时提示尚无项目记忆，建议先执行保存操作
- git 命令失败（非 git 仓库等）→ 跳过 git 分析，仅基于对话历史生成文档，并在文档中注明
- 功能模块名称不确定 → 询问用户确认后再生成

## 全操作完成门禁

- 执行结束前，对照本次读取的 reference 检查每一项用户可见交付，不以文件已写入或命令已成功代替对话输出。
- 最终回复必须自包含本次操作结果；用户不应依赖已折叠的 commentary 才能知道重要信息。
- 任何必填输出遗漏时，状态仍是未完成；先补齐输出，再提交、推送或结束回合。
