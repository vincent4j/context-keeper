# 安装与自动入口

Context Keeper 的核心流程不依赖特定 Agent。安装器分别完成两件事：把 Agent 的 Skill 入口软连接到当前 Git 源码目录，以及写入短入口规则。源码仓库是唯一真实副本，不向安装目录复制 Skill 文件。

## 推荐入口：Git 源码仓库＋软连接

```bash
git clone https://github.com/vincent4j/context-keeper.git <source-dir>
python3 <source-dir>/scripts/install.py --all
```

已有源码仓库时跳过 `git clone`。安装器必须从带 `.git` 的 Context Keeper 源码仓库运行，并为各 Agent 创建指向该源码目录的软连接；从复制目录运行会被拒绝。用户首次选择 `/context-keeper` 后，Agent 按 SKILL.md 执行以下检查（用户不需要手动执行）：

```bash
python3 <skill-dir>/scripts/install.py --ensure-bridge --skill-dir <skill-dir> --root <repo> --codex
```

当前宿主是 Claude Code 时使用 `--claude`。只配置当前宿主，不使用 `--all`。

- 用户级安装对应用户级规则；项目级安装对应安装项目的规则，不以当前工作目录猜安装范围。
- 支持 `.agents/skills`、对应宿主的 `.codex/skills` 或 `.claude/skills`；这些位置必须是指向当前 Git 源码目录的软连接。
- 安装位置已经是正确软连接时保持不变；发现真实复制目录时不自动删除，避免丢失局部修改，必须先核对差异再人工迁移为软连接。
- 宿主只提供软链接解析后的源码路径时，从当前项目及其祖先、用户安装位置找回指向同一源码的别名，项目优先。
- 同一会话检查一次；规则已是当前版本时不写文件，不重复通知。更新版本时替换自己的区块并读回检查，保留区块外原文。
- 未知路径、宿主不明、损坏或重复标记时停止配置，说明原因；不得猜测全局范围或覆盖用户内容。
- `--ensure-bridge` 不复制 Skill、不初始化记录、不迁移项目、不触发 hooks。显示菜单及后续动作由调用它的 Agent 继续执行。
- 首次运行依赖 Agent 遵循 Skill 指令；配置成功不证明宿主已重新加载规则。后续新会话才有机会按宿主机制加载入口，不承诺所有模型可靠自动触发。

以下命令用于手动管理或排查，不需要放在面向用户的快速安装步骤中。

## 用户级

对当前用户的所有项目生效：

```bash
python3 scripts/install.py --all
```

也可只指定 `--codex` 或 `--claude`。用户级入口分别写入对应 Agent 的用户规则文件，项目历史仍存放在各项目自己的记录目录，不跨项目自动混合。

## 项目级

只对指定项目生效：

```bash
python3 scripts/install.py --project <repo> --all
```

项目级安装在项目的 Agent Skill 目录创建指向源码仓库的软连接，并把短入口规则写入项目根目录的规则文件。用户级和项目级同时存在时，Agent 只执行一次检索或沉淀流程。

Skill 已经通过软链接或其他方式安装，只需启用入口时：

```bash
python3 scripts/install.py --all --bridge-only
```

卸载时只删除 Context Keeper Skill 和自己的受控入口区块，保留用户其他内容：

```bash
python3 scripts/install.py --all --uninstall
```

## 验收

安装结果必须分别报告：

- Skill 文件安装到哪里。
- 自动入口写到哪里。
- 哪些 Agent 已验证，哪些没有验证。

安装器当前明确支持 Codex 和 Claude Code。其他能够读取 `AGENTS.md` 或兼容 Skills 目录的 Agent 可能复用项目级入口，但未实测时不能宣称已支持。

入口规则只包含触发条件和 Token 边界，不嵌入项目历史。重复安装更新受控区块，不重复追加；卸载只移除受控区块；不会覆盖受控区块之外的用户内容。

安装输出 `configured_agents` 只证明文件与入口配置成功；不能证明 Agent 在新任务中实际触发。运行时验收需观察真实工具调用、产物和用户可见反馈，分别记录各 Agent 的结果。

## 当前实测限制

2026-09-16：Codex/gpt-6-astra 的普通任务、自动沉淀、跨任务复用及失败后检索用例通过。本机 Claude Code/MiniMax-M3 显式保存可用，但自然纠正未自动沉淀，检索也未严格遵守读取预算。不得将安装成功描述为所有模型均可自动运行。详见仓库 `behavior-verification.md`。
