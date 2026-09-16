# 真实 Agent 行为验收

日期：2026-09-16。结论：Codex 本次场景通过；Claude Code 当前模型部分通过。整个跨 Agent 自动化要求尚未全部达成。

## 方法与范围

使用独立临时项目与每次新启动的任务。普通修改只安装用户级入口；经验场景同时存在用户级和项目级安装。自然触发提示没有指定 Skill 名称或搜索关键词；显式调用仅作对照，不能充当自动沉淀成功证据。

测试材料根据真实历史失败类型构造，明确标为隔离验收材料，不能冒充生产测量。业务项目没有写入。没有提交或推送，也没有更换用户全局模型。

Codex 使用桌面应用内置 CLI 0.154.0-alpha.6.2 和既有 gpt-6-astra。原 shell CLI 0.150.1 在模型运行前拒绝版本兼容，因此改用现有内置版本；未升级全局 CLI。

Claude Code 返回的实际模型为 MiniMax-M3（日志中带 1m 上下文标记），不能将结果推广到原生 Claude 模型。保留默认环境，并额外用仅当前进程禁用 hooks 的对照排除干扰；没有修改全局 hooks。

## 结果

| 用例 | 观测 | 判定 |
|---|---|---|
| Codex 普通修改，26.03 秒 | 只修改指定标题，没有历史检索 | 通过 |
| Codex 自然纠正，98.07 秒 | 自主加载 Skill/save 路由，创建经验、索引、日志，保存检查通过并告知用户 | 通过 |
| Codex 新任务错误记忆，28.87 秒 | 一次受限搜索，引用事实，拒绝写入错误结论；旧计划/日志哈希不变 | 通过 |
| Codex 失败后换路线，77.39 秒 | 检索已有经验和证据，提出补充分阶段计时，告知复用 | 通过 |
| Claude 普通修改，14.27 秒 | 修改指定标题，没有历史检索 | 通过 |
| Claude 自然纠正 | 加强入口措辞后仍只改 README；禁用 hooks 后 17.61 秒同样未沉淀 | 失败 |
| Claude 显式调用，114.12 秒 | 实际调用 Skill、创建经验和记录；发现断链后修复，coverage/save-report 通过并反馈 | 保存能力通过，不是自动触发通过 |
| Claude 新任务错误记忆，23.53 秒 | 引用原文与经验，拒绝错误结论，旧历史哈希不变；没有走受限搜索而读了多个完整文件 | 事实核对通过，检索效率部分不符合 |

单次总时长含模型推理与工具调用，不能据此归因到 Skill 脚本或报告 Token 节省率。Claude 输出额外询问是否撤销经验，不代表已撤销；实际未修改事实。本轮未单独验收 Claude 失败重试、推翻旧决策或其他 Agent。

## 剩余问题与处理边界

当前证据将问题限定为：本机 Claude Code/MiniMax 的自然入口执行不可靠；不是安装缺失，也不是保存脚本不能运行。即便规则可被显式读出，也不能据此声称自动触发已生效。继续无限增补措辞没有可靠依据。

保留显式调用作为已验证可用路径。若要求当前模型也可靠自动执行，需要另行选择可遵循规则的运行模型并验收，或讨论额外触发机制；本次不擅自更换模型，不引入违背轻量要求的逐消息 hooks。这个缺口保持开放。

## 原始证据

本机隔离运行目录（临时路径，可能随系统清理失效）：

`/private/var/folders/r6/qgw1rpbj2q51tgk942d0vz4w0000gn/T/context-keeper-behavior-0jkn9mfr`

- `codex-{normal,capture,reuse,failure}.jsonl` 与对应 `.result.json`、`.final.txt`。
- `claude-normal.jsonl`、`claude-capture.jsonl`、`claude-capture-isolated.jsonl`。
- `claude-diagnose.jsonl`：可读出安装入口，仅为诊断，不是自动执行证明。
- `claude-explicit-isolated.jsonl`、`claude-reuse-isolated.jsonl` 及对应结果。
- `codex-before-reuse-hashes.json`、`claude-before-reuse-hashes.json`：复用前历史指纹，复用后核对一致。
- 各 `*-learning` / `claude-isolated` 子目录保留 Markdown 产物与原始测试证据。

原始对话依据：本会话 ID `01a0a9eb-2928-7b73-a4af-6764fcb1e4f6` 的本地原始记录；重新对照最终方案与后续用户修正，验收映射见 acceptance-review.md。报告没有复制模型思考内容或账户信息。

## 原生 Claude 渠道补查

用户明确不使用复杂 hooks 后，尝试仅对测试进程使用原生 Claude，未修改任何全局模型、认证或 hooks。

- 当前已配置代理的模型列表返回 3 个模型，没有 Claude 模型；用户设置中的三种模型别名均指向 MiniMax-M3。列表不能证明供应商绝对没有其他模型，但本机当前配置没有提供可验证的 Claude 入口。
- 普通 `claude auth status` 显示已登录；隔离用户设置及代理环境变量后，实际最小调用返回 `Not logged in · Please run /login`，模型用量为空，报告费用为 0。不能把此前的登录状态当作原生渠道已可用。
- 因认证阻断，没有执行原生 Claude 的行为验收，也不能据此判断原生 Claude 的 Skill 效果。需要用户提供可用原生渠道或完成官方登录后，继续同组隔离用例。
- 最小调用证据：`/var/folders/r6/qgw1rpbj2q51tgk942d0vz4w0000gn/T/ck-native-claude-5e3ej25o/native-preflight.json`。

继续保留轻量入口与显式调用，不添加 hooks。

## 后续验收安排

用户在渠道补查后明确决定：“这个今天不用验收了，等我实际用的时候再让你验收和测试。”原生 Claude 行为验收按用户决定延期，今天停止渠道探测和模型调用；不要求用户现在登录或配置渠道。待用户实际使用时再启动验收，现有失败及未验证状态保持不变。
