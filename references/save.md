# 保存本次上下文

## 1. 初始化与会话边界

命令返回“需要迁移”（退出码 3）时停止，按 [迁移说明](migrate.md) 预览并取得用户确认；不得绕过门禁读写旧记录。

首次保存前必须先初始化并取得用户确认记录库位置：

```bash
# 询问模式（默认）：打印建议路径，不创建任何目录；rc=5 需要用户确认
python3 <skill-dir>/scripts/context_keeper_probe.py init --root <repo>
# 用户同意默认位置后加 --approved；或用 --store-dir 指到自定义路径（同样需 --approved）
python3 <skill-dir>/scripts/context_keeper_probe.py init --root <repo> --approved
python3 <skill-dir>/scripts/context_keeper_probe.py status --root <repo>
```

init 返回值语义：rc=0（已创建或已就绪）/ rc=2（拒绝：迁移需 `--migrate`、配置无效、目标冲突）/ **rc=5（需要用户确认）**。Agent 看到 rc=5 必须先向用户展示建议位置，等用户回复后再用 `--approved` 或 `--store-dir` 重跑。`init --root <repo>` 在项目已有记录库时直接 rc=0 输出"记录库已就绪"。

脚本按 `<repo>/docs/context-keeper/`、`<repo>/context-keeper/` 的顺序自动发现已有记录库（凭目录内标记识别），所有命令统一 `--root <repo>`，无需按位置区分参数；记录库不在候选位置或两处歧义时，任何命令都可加 `--store-dir <path>` 显式指定，位置不限。首次创建前默认建议位置为 `docs/context-keeper/`，但脚本不会自动创建，必须用户明确同意（加 `--approved`）。用户修改已有记录位置时运行 `init --store-dir <path> --migrate --approved`；不能直接创建第二套记录。`--store-dir` 指到候选位置之外时才写 `context-keeper.json`，候选位置内零配置文件。迁移若会改变历史文件中外部证据链接的指向，脚本会停止并保留原目录；不为迁移改写旧会话记录。

为当前会话使用稳定的 `session-id`（优先平台当前会话 ID，不复制旧记录的 ID）。第一次写入前运行 `record-path` 或 `record-guard`，建立旧计划和日志的内容指纹；指纹保存在用户缓存，不写入项目。缺少基线不能宣称历史保护已经验证。脚本会直接创建带会话标识的文件：

```bash
python3 <skill-dir>/scripts/context_keeper_probe.py record-path \
  --root <repo> --kind plan --title '<中文主题>' --session-id '<session-id>'
python3 <skill-dir>/scripts/context_keeper_probe.py record-path \
  --root <repo> --kind worklog --title '<中文主题>' --session-id '<session-id>'
```

编辑已有 plan 或 worklog 前必须运行：

```bash
python3 <skill-dir>/scripts/context_keeper_probe.py record-guard \
  --root <repo> --path <record> --session-id '<session-id>'
```

非 0 表示该文件不属于当前会话，不得修改；重新运行 `record-path` 创建新记录并链接旧文件。

## 2. Plan 内容

只有存在需要保留的明确需求或实施方案时才创建，不因任务类型是 feature/research 就机械创建。已有权威文档时，只记录本轮变化并链接来源，不复制完整正文。Plan 包含：

- 用户真实诉求、明确范围、确认、否定和验收期望。
- 围绕这些明确事实形成的实施步骤、技术选择、风险和验证方式。
- 尚未确定的内容标为待确认。
- 用户原话、忠实转述和 Agent 判断保持可区分。

Plan 使用以下短章节，暂无的内容写“无”，不为补齐格式编造需求：

```markdown
## 用户需求
用户原话或忠实总结，注明来源。
## 范围
已确认要做和不做的内容。
## 实施计划
围绕上述需求的步骤。
## 验证方式
可观察的验收结果。
## 待确认
无，或尚未确认的问题。
```

校验只能证明字段存在；是否忠于用户事实仍需逐项核对当前对话。

同一会话、同一主题可以更新。同一会话中能够独立实施、独立验收或需要单独检索的主题分别建 plan；连续澄清继续写同一文件。跨会话必须新增记录。

## 3. Worklog 内容

记录本会话实际发生的工作、结果、用户反馈和证据。不要把计划写成已完成，也不要把工具成功写成用户认可。

至少包含任务概述、实际结果、问题与处理、未完成事项、关键文件、下一步，以及以下两段。

```markdown
## 给用户看的增量认知

- **盲点：** 一句认知，不超过 120 字。
  - **影响：** 一句影响，不超过 80 字。
```

最多 3 条。没有新增认知时只写：

```text
本轮未发现需要额外提醒的盲点或隐患。
```

不能重复历史上完全相同的提醒；确有必要再次提醒时加入本次的新场景或新证据。

如果本轮沉淀、复用或修正了经验，加入：

```markdown
## 自我进化

- **已沉淀：** [新经验如何形成；链接到对应 evolution 文件]
- **本次复用：** [经验如何改变本轮判断或动作；链接到对应 evolution 文件]
- **修正经验：** [旧范围如何被新证据修正；链接到对应 evolution 文件]
```

每条只链接一个实际存在的经验文件。读到经验但没有影响行为时，不写“本次复用”；同一经验已经沉淀过时，只能记录复用或修正。

末尾写短摘要：

```markdown
## 快速摘要（用于下次对话）

**类型：** [feature|bugfix|refactor|research|config] | 项目：[项目名]
**完成：** [已完成事实]
**问题：** [问题与已验证处理；没有则省略]
**经验：** [有证据的经验；没有则省略]
**下一步：** [未完成事项或下一步]
**文件：** [关键文件]
```

## 4. Memory 与未完成事项

`memory-keeper.md` 保存当前进度和入口：

- 时间线按以下结构加入本次 plan/worklog 的 Markdown 链接（最新在前），方便续接识别类型和经验：

```markdown
## 时间线（最新在前）

## YYYY-MM-DD - 中文主题 `feature`
- **任务：** 本轮任务。
- **关键经验：** 有证据的结论；没有则省略。
- **详见：** [计划](plans/YYYY-MM-DD-中文主题.md)、[日志](worklogs/YYYY-MM-DD-中文主题.md)
```

只链接实际存在的文件；类型使用本轮实际类型。

- 保留 `evolution/index.md` 入口。
- 未完成事项使用以下格式，便于续接时按当前任务筛选：

```markdown
- <事项>；状态：<未开始/进行中/阻断/已完成/已取消>；触发：<什么时候需要处理>；完成：<关闭条件>；证据：<验证位置>。
```

局部完成不能关闭更大的待交付事项。索引可以更新，但不能借更新索引改写历史文件的含义。

## 5. Evolution

只有以下情况更新：用户明确纠正；失败后换方法并得到可核验结果；旧经验被新证据修正或失效。

先查 `evolution/index.md` 和同主题文件。索引每条保留主题、触发词、适用范围和真实 Markdown 链接，不复制正文。有则追加新证据或修正范围，没有才创建中文主题文件：

```markdown
# <经验主题>

- **编号：** CK-<唯一编号>
- **状态：** 待验证|已验证|已替代
- **触发条件：** <什么情况下检查>
- **已知事实：** <只写有证据的事实>
- **证据位置：** <原始记录或运行证据>
- **建议动作：** <下次具体做什么>
- **适用范围：** <项目、版本、输入和边界>
```

用户要求与技术验证分开：在已知事实里明确“用户确认的要求”“运行验证的结果”或“待验证推断”；用户纠正不能证明技术方法有效。

替代旧经验时，保留其原有事实和来源，增加 `- **替代为：** [新经验](新经验.md)`，状态改为已替代；链接必须指向当前有效主题，不能循环。更新同主题时保留新旧证据及日期。

同类错误再发生时依次检查：没记录、没命中、没采用、还是已不适用；只修复失效环节，不堆叠禁止规则。

用户明确确认可跨项目复用时才运行：

```bash
python3 <skill-dir>/scripts/context_keeper_probe.py promote-evolution \
  --root <repo> --source <evolution-file> --approved
```

## 6. 校验与交付

```bash
python3 <skill-dir>/scripts/context_keeper_probe.py coverage --root <repo>
python3 <skill-dir>/scripts/context_keeper_probe.py save-report \
  --root <repo> --worklog <worklog> --session-id '<session-id>'
```

`coverage` 默认只输出计数；需要定位时再加 `--details`。历史遗留缺口只报告，不批量修补。本次新增的计划缺项、重复经验、缺索引和断链必须修复；不能用“历史遗留”跳过本轮问题。`save-report` 非 0 时先修复本次记录，不能宣称保存完成。

保存检查会比较本会话开始记录的旧文件指纹，旧记录修改或删除都会阻断交付；该检查不是文件系统访问控制，不能阻止外部编辑器写入。

最终只输出一次增量认知和自我进化反馈，并附必要链接。用户已经授权提交或推送时按授权执行，只处理本轮相关文件。
