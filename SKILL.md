---
name: context-keeper
description: 续接项目进度，查找历史事实，自动沉淀经验，让 AI 在使用中持续自我进化。
---

# Context Keeper

用有限上下文保存进度、恢复工作、检索历史事实，并在有证据时积累可复用经验。普通新需求不自动搜索历史。

## 首次使用：补齐自动入口

本会话首次调用本 Skill 时，先运行下面的一次性检查，再显示菜单或执行用户指定动作。`<skill-dir>` 使用当前实际加载的 Skill 目录（优先保留安装路径，不主动解析软链接），`<repo>` 为当前项目；按当前宿主选 `--codex` 或 `--claude`，只能选一个，不根据机器上装了哪些程序猜宿主。

```bash
python3 <skill-dir>/scripts/install.py --ensure-bridge --skill-dir <skill-dir> --root <repo> --codex
```

Claude Code 将最后的 `--codex` 换成 `--claude`。这属于首次使用初始化：按安装位置自动判断用户级或项目级，补齐当前宿主的短入口，不复制 Skill、不创建项目记录、不迁移数据。无需额外要求用户输入安装命令。

返回 `created/appended/updated` 时简短告知“已配置自动入口”，然后继续原操作；`unchanged` 时静默继续。同一会话已检查成功就复用结果，不在每条消息里重复检查。未知宿主、范围不明或写入失败时如实说明未启用自动入口，按需读 [安装说明](references/install.md)，不擅自扩大为全局安装。不要将配置成功说成模型行为已验证，也不要声称新规则已经被宿主重新加载。

## 事实边界

- 用户记忆与记录不一致时查找过去事实；不迎合记忆，不猜测或编造。
- 原始记录、历史摘要和本轮推断分开。只找到摘要时标明“摘要”；未找到时只说“当前检索未找到证据”。
- `plans/` 保存用户真实诉求及围绕这些诉求形成的实施计划，不发散新需求。
- `worklogs/` 保存本会话实际工作、结果、用户反馈和证据。
- 同一会话、同一主题可以更新同一记录；跨会话必须新增并链接旧记录。
- 经验只在用户明确纠正、失败后出现可核验新结果，或旧经验被新证据修正时沉淀。Agent 猜测只能标为待验证。

## 默认结构

第一次保存前，先向用户展示默认记录位置并取得确认，再调用 `init`：

```bash
# 询问模式（默认）：打印建议路径，不创建任何目录，等待用户回复；rc=5
python3 <skill-dir>/scripts/context_keeper_probe.py init --root <repo>

# 用户同意默认位置：加 --approved 确认创建
python3 <skill-dir>/scripts/context_keeper_probe.py init --root <repo> --approved

# 用户想换位置：用 --store-dir 指到自定义路径（同样需 --approved）
python3 <skill-dir>/scripts/context_keeper_probe.py init --root <repo> --store-dir <自定义路径> --approved
```

**init 返回值语义**：rc=0 已创建或已就绪；rc=2 拒绝（迁移需 `--migrate`、配置无效、目标冲突）；**rc=5 需要用户确认**——Agent 必须向用户说明建议位置，等用户同意默认位置则重跑加 `--approved`，用户想换位置则改 `--store-dir <path> --approved`。`init --root <repo>` 在项目已有记录库时直接 rc=0 输出"记录库已就绪"，不进入询问。

`init` 任何时候都不能跳过询问直接创建；Agent 也不允许因为"用户已说过想保存"就自动加 `--approved`，除非看到用户明确同意。

**migrate 返回值语义**：rc=0 完成；rc=3 预览完成但未批准——Agent 需把预览结果（含文件级映射、外部链接修改列表）告知用户，等用户明确同意后加 `--approved` 重跑；rc=2 拒绝（目标非法、目标非空、旧结构含软链接）。脚本自动发现记录库：依次检查 `<repo>/docs/context-keeper/` 与 `<repo>/context-keeper/`（按目录内 `memory-keeper.md`、`worklogs/`、`plans/`、`evolution/`、`migration-manifest.json` 等标记识别，同名空目录不算）；两处同时存在会明确报错，此时用 `--store-dir` 指定其一。**所有命令都支持 `--store-dir` 显式指定记录目录，位置不限**。`init`/`migrate` 的目标在两个候选位置内不写任何配置文件，只有指到候选之外才写 `context-keeper.json`（后续命令靠它或 `--store-dir` 找到该位置）。已有记录改位置必须显式使用 `--migrate`，目标冲突时停止。

**migrate 默认目标**：不传 `--store-dir` 时迁到 `docs/context-keeper/`（与新 init 默认一致）；迁回根目录位置用 `--store-dir context-keeper`；其他自定义路径同样支持但不能是 docs/ 下的非 context-keeper 子路径（避免覆盖项目文档）。

```text
docs/context-keeper/
├── memory-keeper.md
├── plans/
│   └── YYYY-MM-DD-中文主题.md
├── worklogs/
│   └── YYYY-MM-DD-中文主题.md
└── evolution/
    ├── index.md
    └── 中文主题.md
```

旧版 `docs/plans/`、`docs/worklog/`、`docs/worklogs/` 和 `docs/memory-keeper.md` 不再兼容读取。每个操作命令都会检查旧结构，发现旧记录返回退出码 3 并停止；不得绕过脚本读取旧目录。

出现“需要迁移”时，先运行 `migrate --root <repo>` 展示目录、文件数量、受影响链接和备份范围，询问用户是否迁移；只有用户明确确认后运行 `migrate --root <repo> --approved`。拒绝或未回复则停止本 Skill。细节按需读取 [references/migrate.md](references/migrate.md)。迁移授权只对应当前项目，不代表允许批量迁移其他项目。

## Token 与耗时边界

- 续接默认最近 3 份短摘要和最多 5 条经验；指定类型时优先同类型 3 条，再补其他类型 2 条。
- 传入当前任务关键词时，只展示相关未完成事项和经验。
- 搜索首轮最多 5 个候选，其中进化经验最多 3 个；只展开最相关的 1～2 份记录。
- 同一问题本轮只检索一次，除非出现新错误、新证据或路线变化。
- 自动搜索零命中即停止。只有用户明确追溯原文或关键判断缺少事实证据时，才运行原始会话搜索。
- 普通新需求、文字修改和常规实现不触发历史搜索。
- `coverage` 默认只输出一行计数；只有排查缺口时加 `--details`。

## 操作路由

只读取当前操作需要的 reference：

- 保存（包括用户纠正后的自动沉淀）：先运行 `status`，再读 [references/save.md](references/save.md)。
- 继续：运行 `resume --query '<当前关键词>'`，需要细节时读 [references/resume.md](references/resume.md)。
- 查找：从当前上下文提取关键词运行 `search`，再读 [references/search.md](references/search.md)。
- 安装、卸载、用户级或项目级入口：读 [references/install.md](references/install.md)。

用户通过 `/context-keeper` 或其他方式只调用 Skill、没有说明动作时，展示以下菜单，并将用户下一条回复的 1、2、3 分别路由到保存、继续、查找：

```text
你想做什么？

1. 保存 —— 记下本次需求、进度和未完成事项，方便下次继续。
2. 继续 —— 找回上次进度，接着做没完成的任务。
3. 查找 —— 查找当前问题的历史记录和相关经验。

回复 1、2 或 3 即可。
```

用户已说明动作时直接执行，不重复展示菜单。直接命令 `context keeper 保存/继续/查找` 仍对应三个操作。

## 自动触发边界

入口规则只在以下节点调用本 Skill：

- 用户提到以前、上次、又出现、按之前的方法等历史信号。
- 当前处理失败，准备重复尝试或切换路线，且本轮证据不足。
- 准备推翻旧决策，但原依据不在当前上下文。
- 用户明确纠正事实、行为或遗漏，或新的处理方式已经得到可核验结果；在自然收尾点检查是否需要沉淀经验。

入口不让每条消息都运行 Context Keeper，也不在 Agent 规则文件中存放项目历史。

## 历史原文

项目 Markdown 不能支撑关键判断时，运行：

```bash
python3 <skill-dir>/scripts/context_keeper_probe.py history-search \
  --root <repo> --query '<关键词>'
```

该命令按项目隔离检索 Codex 和 Claude Code 原始会话，只输出有限命中片段及文件定位。找不到仍不能推断历史上未发生。

## 自我进化

经验文件必须包含编号、状态、触发条件、已知事实、证据位置、建议动作和适用范围。状态只有待验证、已验证、已替代；已替代经验保留替代链接和原证据。搜索优先已验证经验，排除已替代经验，标明待验证经验。

触发自动沉淀时必须执行保存路由，不以修改业务文件代替经验记录；没有新增事实时才跳过，不能因为用户没有说“保存”而省略。

同主题优先更新，不重复创建。沉淀、实际复用或修正后，在合适的进度节点或最终回复中说明它改变了什么判断或动作。严格区分“找到”“采用”“验证有效”。同一经验已经沉淀过时，不能再次宣称首次沉淀。

项目经验默认留在项目。只有用户明确确认可跨项目复用时，才运行 `promote-evolution --approved` 保存到用户级经验目录；用户级安装不自动汇总所有项目。

## 完成门禁

- 新记录必须使用 `record-path` 创建；第一次写入前运行 `record-path` 或 `record-guard` 建立会话历史指纹；写入已有记录前运行 `record-guard`。
- 新目录工作日志运行 `save-report` 时必须传当前 `--session-id`；检查历史指纹和本会话计划后才交付，校验不通过不得宣称保存完成。
- `coverage` 检查索引、摘要、会话标识、经验字段、重复编号、未完成事项字段和链接。历史遗留缺口只报告，不批量改写。
- 最终回复只输出一次增量认知和自我进化反馈，不重复工具清单。
- Context Keeper 不自动增加提交或推送权限。
