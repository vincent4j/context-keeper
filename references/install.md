# 安装与自动入口

Context Keeper 的核心流程不依赖特定 Agent。安装器分别完成两件事：复制 Skill 文件，以及写入短入口规则。

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

项目级安装把 Skill 放入项目的 Agent Skill 目录，并把短入口规则写入项目根目录的规则文件。用户级和项目级同时存在时，Agent 只执行一次检索或沉淀流程。

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
