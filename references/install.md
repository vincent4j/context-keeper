# 安装与自动入口

Context Keeper 的核心流程不依赖特定 Agent。安装器分别完成两件事：让 Agent 从当前 Git 源码目录加载 Skill，以及写入短入口规则。源码仓库是唯一真实副本，不向安装目录复制 Skill 文件。

## 推荐入口：复制给 Agent

把下面这段话发给有本机文件和命令操作能力的 Agent：

```text
请从 https://github.com/vincent4j/context-keeper 克隆最新的 main 分支。运行 scripts/install.py --all 预览写入范围，告诉我当前提交和将改动的文件；等我确认后，再加 --approved 执行安装。
```

以下命令供 Agent 执行。第一次运行只预览，用户确认后才能加入 `--approved` 再运行：

```bash
git clone --branch main https://github.com/vincent4j/context-keeper.git <source-dir>
git -C <source-dir> rev-parse HEAD
python3 <source-dir>/scripts/install.py --all
```

安装器也接受声明文件哈希全部匹配的市场安装包；不会接受未经验证的复制目录。用户首次选择 `/context-keeper` 后，Agent 按 SKILL.md 预览自动入口配置：

```bash
python3 <skill-dir>/scripts/install.py --ensure-bridge --skill-dir <skill-dir> --root <repo> --codex
```

当前宿主是 Claude Code 时使用 `--claude`。得到用户确认后再加 `--approved` 写入。Cursor、WorkBuddy、Hermes、OpenCode 和 OpenClaw 当前只安装原生 Skill 目录，不写自动入口规则。

- 用户级安装对应用户级规则；项目级安装对应安装项目的规则，不以当前工作目录猜安装范围。
- 目标 Agent 必须显式选择，安装器不会根据 PATH、用户目录或项目文件猜测宿主。
- 支持的原生目录见下表；这些位置必须从当前 Git 源码目录加载。
- 安装位置已正确配置时保持不变；发现真实复制目录时不自动删除，避免丢失局部修改，必须先核对差异。
- 宿主只提供实际源码路径时，从当前项目及其祖先、用户安装位置找回同一来源的安装位置，项目优先。
- 同一会话检查一次；规则已是当前版本时不写文件，不重复通知。更新版本时替换自己的区块并读回检查，保留区块外原文。
- 未知路径、宿主不明、损坏或重复标记时停止配置，说明原因；不得猜测全局范围或覆盖用户内容。
- `--ensure-bridge` 不复制 Skill、不初始化记录、不迁移项目、不触发 hooks。显示菜单及后续动作由调用它的 Agent 继续执行。
- 首次运行依赖 Agent 遵循 Skill 指令；配置成功不证明宿主已重新加载规则。后续新会话才有机会按宿主机制加载入口，不承诺所有模型可靠自动触发。

以下命令默认只预览影响；用户确认后加 `--approved` 执行。

## 用户级

对当前用户的所有项目生效：

```bash
python3 scripts/install.py --all
```

也可指定 `--codex`、`--claude`、`--cursor`、`--workbuddy`、`--hermes`、`--opencode` 或 `--openclaw`。用户级入口目前只写入 Codex 和 Claude Code 的用户规则文件，项目历史仍存放在各项目自己的记录目录，不跨项目自动混合。

## 项目级

只对指定项目生效：

```bash
python3 scripts/install.py --project <repo> --all
```

项目级安装让项目的 Agent Skill 目录从源码仓库加载；选择 Codex 或 Claude Code 时，才会把短入口规则写入项目根目录的规则文件。用户级和项目级同时存在时，Agent 只执行一次检索或沉淀流程。

Skill 已通过统一安装或其他方式可用，只需启用 Codex 或 Claude Code 自动入口时：

```bash
python3 scripts/install.py --codex --claude --bridge-only
```

卸载时只删除 Context Keeper Skill 和自己的受控入口区块，保留用户其他内容：

```bash
python3 scripts/install.py --all --uninstall
```

多个 Agent 共用同一安装位置时，只能一起卸载；针对其中一个 Agent 的卸载请求会停止，并保留该位置。其他来源的同名配置和无法确认归属的目录也不会被删除。

## 验收

安装结果必须分别报告：

- Skill 文件安装到哪里。
- 自动入口写到哪里。
- 哪些 Agent 已验证，哪些没有验证。

| Agent | 用户级目录 | 项目级目录 | 自动入口 |
|---|---|---|---|
| Codex | `~/.agents/skills`、`~/.codex/skills` | `.agents/skills`、`.codex/skills` | 支持 |
| Claude Code | `~/.claude/skills` | `.claude/skills` | 支持 |
| Cursor | `~/.cursor/skills` | `.cursor/skills` | 未启用 |
| WorkBuddy | `~/.workbuddy/skills` | `.workbuddy/skills` | 未启用 |
| Hermes | `~/.hermes/skills` | `.agents/skills` | 未启用 |
| OpenCode | `~/.config/opencode/skills` | `.opencode/skills` | 未启用 |
| OpenClaw | `~/.agents/skills` | `.agents/skills` | 未启用 |

这些目录的安装验证只证明 Skill 文件可被对应宿主发现；自动入口和真实触发必须分别在该宿主的新任务中验收。安装器会拒绝替换同名的其他来源配置，也不会猜测该为哪个 Agent 写入规则。

入口规则只包含触发条件和 Token 边界，不嵌入项目历史。重复安装更新受控区块，不重复追加；卸载只移除受控区块；不会覆盖受控区块之外的用户内容。

安装输出 `configured_agents` 只证明文件与入口配置成功；不能证明 Agent 在新任务中实际触发。运行时验收需观察真实工具调用、产物和用户可见反馈，分别记录各 Agent 的结果。

## 当前实测限制

2026-09-16：Codex/gpt-6-astra 的普通任务、自动沉淀、跨任务复用及失败后检索用例通过。本机 Claude Code/MiniMax-M3 显式保存可用，但自然纠正未自动沉淀，检索也未严格遵守读取预算。不得将安装成功描述为所有模型均可自动运行。详见仓库 `behavior-verification.md`。
