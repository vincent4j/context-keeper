# 2026-11-04 收尾审核检查点（Agent 支持范围调整）

## 结论与范围

**限定范围完成，一项 P2 文档收口。** 本轮把安装器 Agent 范围由旧七家（Codex、Claude Code、Cursor、WorkBuddy、Hermes、OpenCode、OpenClaw）调整为六家（Codex、Claude Code、WorkBuddy、ZCode、DeepSeek Harness、OpenCode），并为六家全部启用自动入口写入；代码与测试可关闭，SKILL.md 首次使用段残留旧口径（SKILL-01），待用户授权修复。

- 审核基线：提交 `495bbbb` 加未提交工作区改动（本会话产物，尚未提交）；提交后需按最终 SHA 补记。
- 范围：`scripts/install.py`、`README.md`、`references/install.md`、`tests/test_install.py`、`tests/test_workbuddy_install.py`、`manifest.json`，及六家口径的全仓一致性。
- 目录与入口合同来源：mem-sharing `scripts/agents.json`（ZCode `.zcode`、DSH `.dsh`、OpenCode `.config/opencode`，项目级原生四家共用根 `AGENTS.md`）。
- 本轮审核只读核查源码与文档，仅新增本检查点；未修源码或现有文档、未删文件、未提交推送或发布。
- 更正记录：上一轮会话曾误报“docs/verification 历史验收报告还提到旧三家”，经全仓复核为零命中，误报源于 grep 大小写不敏感命中 ZCode；历史验收报告未改动，维持原样。

## 六项审核状态

| 审核单元 | 状态 | 结论与证据 |
| --- | --- | --- |
| 代码正确性、边界与兼容 | 完成 | 六家桥接路径、共用 AGENTS.md 单写去重、`kept_shared` 部分卸载保留、OpenCode 嵌套用户目录定位、写回滚语义均有实现与测试覆盖；150 项回归通过。 |
| 当前文档与历史材料分工 | 待修复 | SKILL.md 首次使用段仍按旧三家＋“其余四个宿主”描述，与六家自动入口实现矛盾。见 SKILL-01。 |
| 文件删留与缓存 | 完成 | 无应删未删项；`dist/context-keeper-1.0.0.zip` 已随本轮重算重建（未跟踪），沿上一检查点“待核实用途”裁定。 |
| 验证证据 | 限定范围完成 | 150 项脚本回归＋隔离 HOME 冒烟为脚本级证据；ZCode、DeepSeek Harness、OpenCode 真机运行时验收未做，README 已如实标注。 |
| 风险与阶段交付 | 限定范围完成 | 无代码阻断；SKILL-01 阻断“全仓六家口径一致”声明。版本未升（OBS-01）。 |
| 授权与续审记录 | 完成 | 本检查点记录基线、待办与失效条件；修复与提交推送均待当轮授权。 |

## 实质发现

### SKILL-01：P2，SKILL.md 首次使用段残留旧七家口径

- 状态：待修复。
- 位置：[SKILL.md](../../SKILL.md) 行 27、33。
- 证据：行 27 “当前宿主是 Codex、Claude Code 或 WorkBuddy 时……按宿主选 `--codex`、`--claude` 或 `--workbuddy`（只选一个）”；行 33 “其余四个宿主只依赖原生 Skill 发现机制，不写未验证的自动入口。”
- 影响：ZCode、DeepSeek Harness、OpenCode 会话按此段不会执行入口补齐，与本轮“六家全部自动入口”的实现和 README 直接矛盾；SKILL.md 在打包清单内，修复须同步 manifest 哈希。
- 修订方向：行 27 扩为六家宿主旗标（补 `--zcode`、`--dsh`、`--opencode`）；行 33 改述为六家入口语义（项目级原生四家共用根 `AGENTS.md` 同一受控区块）并保留“配置成功不代表运行时验收”边界。不扩大常驻入口内容。
- 复核方式：只核对该段与 install.md、install.py 旗标一致性，重算打包哈希，定向跑 install 与 package 测试，不重做全量回归。

### OBS-01：P3，行为变化未升版本

- 状态：非阻断，交付决策。
- 位置：`manifest.json` `"version": "1.0.0"`。
- 证据：本轮变更安装范围（七家→六家）与入口行为（+3 家自动入口），版本号未变。
- 影响：如沿用 1.0.0 发布，已装用户无法凭版本区分行为差异。
- 修订方向：由用户决定发布口径；发布检查不在本轮范围。

### OBS-02：P3，旧三家存量安装缺少迁移说明

- 状态：非阻断，文档建议。
- 位置：[references/install.md](../../references/install.md)。
- 证据：`--cursor`、`--hermes`、`--openclaw` 旗标与目录已移除，文档未说明此前用旧旗标安装的机器如何清理残留链接与目录。
- 影响：存量机器残留的旧三家 Skill 链接无法用新安装器卸载，需手动清理。
- 修订方向：在安装说明补一段存量清理指引；也可不处理，由用户按受众决定。

## 证据核验与边界

### 本轮实查

| 核查 | 结果 | 含义 |
| --- | --- | --- |
| `python3 -m unittest discover -s tests` | 150 项通过，4.473 秒，退出码 0 | 含本轮新增 4 个用例（bridge-only 三家写入、OpenCode 嵌套用户入口、首用 user/project 双向、部分卸载保留共用区块）；脚本级证据。 |
| `git diff --check` | 无输出 | 无空白错误。 |
| `git status --short`（含未跟踪） | 6 个已跟踪文件修改，无非忽略未跟踪文件 | 改动集与授权范围一致；dist 与 `__pycache__` 为忽略项。 |
| manifest 逐项 SHA256 | 14 项与当前源码一致，版本 1.0.0 | 打包清单同步完成，不代表已发布。 |
| 全仓旧三家残留 | 内容与文件名零命中 | Cursor、Hermes、OpenClaw 已清干净；probe 中 `cursor` 为数据库游标变量，无关。 |
| 隔离 HOME 冒烟 | `--all` 六入口 `created`；`--ensure-bridge --zcode` 对已写入口返回 `unchanged` | 用户级默认安装与幂等零写成立。 |
| 共用区块单写 | 项目级 `--zcode --dsh --opencode --bridge-only` 仅 1 个 AGENTS.md 区块 | 共用文件去重生效。 |
| 部分卸载保留 | `--opencode --uninstall` 报 `kept_shared`，AGENTS.md 区块保留 | 共用入口不被单独卸载拆除。 |

### 保持开放的证据缺口

- ZCode、DeepSeek Harness、OpenCode 的真实新会话加载与自动触发验收未做（README、install.md 均已标注待验收）。
- 沿上一检查点延期项：真实宿主行为验收、“时间线填满”独立反例、缓存清理、dist 分发用途核实。

## 文件删留裁定

| 对象 | 裁定 | 依据及本轮动作 |
| --- | --- | --- |
| `docs/verification/` 全部历史报告 | 保留 | 带日期的历史验收，不改写；复核确认其中无旧三家残留。 |
| `DESIGN.md` 行 291 | 保留 | “2026-11-01 本机同步三家用户级受控块”是绑定日期的本机配置事实，非当前能力声明。 |
| `dist/context-keeper-1.0.0.zip` | 待核实用途 | 本轮已随 manifest 重算重建（未跟踪、可再生成）；是否用于外部分发仍待核实。 |
| `.DS_Store`、`scripts/__pycache__/`、`tests/__pycache__/` | 可删除 | 沿旧裁定，本轮未删。 |

## 续审位置与失效条件

1. 下一单元：SKILL-01 修复（行 27、33 两处＋打包哈希重算＋定向测试），待用户授权。
2. 交付：本轮 6 个文件改动与本检查点未提交；提交、推送按用户当轮授权执行，提交后在本文件补记最终 SHA。
3. 可选独立单元：OBS-01 版本决策、OBS-02 存量清理指引、真机验收（需用户恢复）、缓存清理、dist 用途核实。
4. 本轮代码结论绑定 `495bbbb`＋上述工作区 diff；相关源码、测试、模板再变化后增量重审。隔离 HOME 冒烟结论不外推到真实 HOME 配置。
5. 远端状态本轮未查询；不沿用历史推送授权。

## 追加修复与交付记录：2026-11-04

本节是原检查点之后的新状态，保留前文当时的审查结论，不回改。

- **授权：** 用户明确选择修复 SKILL-01 并提交推送；范围是 SKILL.md 两处行文、打包哈希重算、本检查点追加记录，不含 OBS-01 版本决策、OBS-02 迁移说明与延期真机验收。
- **SKILL-01：已修复。** 行 27 扩为六家宿主与六个旗标（补 `--zcode`、`--dsh`、`--opencode`）；行 33 尾句改为“项目级原生四家共用根 `AGENTS.md` 同一受控区块、用户级各写自己的规则文件；ZCode、DeepSeek Harness 与 OpenCode 的入口写入尚未完成真机运行时验收”。
- **打包同步：** 重新运行 package_skill.py，manifest 与 SKILL.md 哈希一致，文件集合仍 14 项、版本仍 1.0.0。
- **本轮实际验证：** `python3 -m unittest discover -s tests` 150 项通过（6.108 秒）；`git diff --check` 无输出。
- **复核裁定：** SKILL-01 关闭，文档与六家实现一致；OBS-01、OBS-02 保持开放待用户决策；真机运行时验收保持延期。
- **交付：** 本轮全部改动与本检查点按用户授权纳入同一提交并推送；最终提交与远端一致性以交付回执确认，不提前宣称推送成功，也不再回写本文件。
