# Context Keeper 本机同步与新会话验证

日期：2026-10-30，Asia/Singapore。源码：`165114d46b42cd4a9889515580de178e0a16449f`。

## 已安装来源与同步范围

检查到的四处用户级 Skill 入口均为符号链接，指向同一源码仓库 `$HOME/Tools/Source/context-keeper`：`~/.agents/skills/context-keeper`、`~/.claude/skills/context-keeper`、`~/.workbuddy/skills/context-keeper`、`~/.zcode/skills/context-keeper`。它们已经包含本次修复，无需复制或重新安装 Skill。ZCode 仅确认来源一致，未扩大为其客户端运行通过，也未新增安装器不支持的自动入口。

检查了 `~/Tools/Source` 下 Git 仓库及其存续 worktree，共 34 个根；这是本轮发现范围，不宣称覆盖任意未登记目录。

共同步 **15 份规则文件**：

- 用户级 3 份：更新 Codex 受控块；在 Claude Code 追加受控块；在 WorkBuddy 顶部补齐受控块。
- 项目/工作树 12 份：agent-group-memory、knowwind、poster-fit，以及 agent-group-memory 的 captain-review-20261029、guaji-m4-contract、tututu-m4-preflight 三个现存工作树，各自的 AGENTS.md、CLAUDE.md。
- 3 个主项目既存的 WorkBuddy 项目桥接块已是当前模板，保持不变。项目 Skill 别名也均指向当前源码。

所有目标先核对原始哈希、检查标记、备份，再通过安装器 bridge-only 更新；块外原文按字节保留。随后再次运行相同安装命令，15 个 action 均为 unchanged，字节与 mtime 均未变化。新会话验证后再核对，15 个文件仍与同步后的哈希一致。没有提交或推送其他项目的规则文件。

完整目标、备份文件、前后哈希及安装输出保留在本机私有备份目录，不随仓库发布。备份目录仅当前用户可访问，原始规则备份文件权限为 0600。

## 新会话验证

验证项目从前次受控验收的真实订单修复产物恢复。记录库已授权，订单有 5 项本地测试，客户入口故意保留 int 转换缺陷；所有真实上游样本仍未获得。提示为自然续接与同类入口修复，没有要求保存或创建经验。

Codex、Claude 和第一组 WorkBuddy 验证目录都没有项目级 AGENTS/CLAUDE 入口，也没有项目 Skill 别名，用于检查本机用户级安装。没有替换真实 HOME/CODEX_HOME 或屏蔽既有用户配置。

| 宿主 | 实际观察 | 验证边界 |
| --- | --- | --- |
| Codex 桌面新聊天 | 实际读取 `~/.agents/skills/context-keeper/SKILL.md`；ensure-bridge 返回 user/unchanged；实际执行多关键词 resume，直接返回最新合同及待办；修复后 11 项测试通过，自然整理 CK-ID-001 | 多关键词脚本调用、用户级加载和自动经验整理均有真实工具证据 |
| Claude Code 新 CLI 会话 | CLI 2.1.295，init 报告模型标签 `claude-sonnet-5-5[1m]`；实际读取 `~/.claude/skills/context-keeper/SKILL.md`，9 项测试通过，自动整理 CK-001 | 未观察到实际 resume 调用；不把它计作多关键词命令链通过。模型标签仅引用 CLI 报告，不推断上游模型身份 |
| WorkBuddy：仅用户级入口 | 快速模式，UI 报告 GLM-5.3-Flash；2m6s 完成、10 项测试通过、保存事实，但没有观察到读取 Skill 或生成编号经验 | 用户级单独入口未验证通过；业务修复成功不能代替自动入口生效 |
| WorkBuddy：项目桥接 | 在另一个全新目录配置与现有项目同样的 AGENTS + `.workbuddy/memory/MEMORY.md` 桥接，保持相同自然提示；5m25s 完成，10 项测试通过，自动新增 CK-001，UI 报告 coverage/save-report 通过 | 项目桥接路径已证实可触发本次重复验证整理规则；仍不宣称用户级单独入口可靠 |

Codex 验证聊天标题“Context Keeper 本机新会话验证”。最初派发漏替换路径占位符，已发送实际路径更正；聊天保留了初始路径失败与后续恢复，不将其包装为全程无误。记录写入阶段，验证聊天为遵守仅项目内写入的约束，将已安装脚本的历史指纹缓存放在验证项目内，源码未改。

WorkBuddy 两个实际新会话分别位于测试工作空间 workbuddy 和 workbuddy-project-bridge，标题为“修复订单和客户编号导入入口问题”和“修复订单编号和客户编号导入问题”。项目桥接组首次查找探针脚本的命令以 137 退出，随后定位到已安装脚本继续处理；原失败未删改。

四组最后均通过相同的 **12 条独立业务断言**。Codex、Claude、WorkBuddy 项目桥接组各有 1 份编号经验；WorkBuddy 用户级单独入口组为 0。四组的旧订单日志均保持原哈希。所有真实样本验收待办保留，未把本地测试推广为生产验收。

## 归档证据及边界

- [独立产物核验](results.json)：四组编号经验原文快照、旧日志不变检查、独立断言与入口检查结果。经验正文中的相对链接是原验证项目内容，不是本归档内的文件。
- [来源哈希](provenance.json)：本机原报告及原核验结果的 SHA-256，以及归档产物哈希。哈希用于对应原件，不独立证明运行行为。
- 原始配置、安装清单、Codex/Claude 工具摘录保留在本机私有备份，不发布用户配置、完整会话或账号信息。临时验证目录可能随清理失效。

本归档由本机报告整理，移除用户绝对路径与聊天标识。用户随后授权提交、推送本次文件，因此将脱敏报告和核验结果纳入仓库；原始备份不上传。没有保存 WorkBuddy 的窗口 URL、账号快照或认证信息。未重建已退役的 agents-group 共享 Skill 副本，未执行会同时改动无关 MCP 的旧全局同步器；现有入口直接链接已更新源码。本轮不代表未验证宿主、其他模型或所有项目均已行为验收通过。
