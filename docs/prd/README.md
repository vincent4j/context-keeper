# Context Keeper 项目 PRD

本文档体系描述当前有效需求、架构、操作入口和验收边界。开发与审查按模块定位；普通使用由 SKILL 和 references 路由，无需加载全部 PRD。

## 模块列表

| 模块 | 说明 | 主 PRD | 合同 / 不变量 | 相关 plans |
| --- | --- | --- | --- | --- |
| 产品与工作流 | 用户目标、触发边界、支持范围、非目标 | [product.md](product.md) | 正文需求与验收标准；无独立生效合同 | 无 |
| 记录与检索架构 | 数据职责、历史保护、分层读取、经验治理 | [architecture.md](architecture.md) | 正文约束；无独立生效合同 | 无 |
| 验收与能力边界 | 验收场景、已知限制、待验证项 | [acceptance.md](acceptance.md) | [合同说明](contracts/README.md) | 无 |

## 操作手册

- [Skill 入口](../../SKILL.md)：触发条件与完成门禁。
- [保存](../../references/save.md)、[续接](../../references/resume.md)、[检索](../../references/search.md)。
- [安装与卸载](../../references/install.md)、[旧记录迁移](../../references/migrate.md)。

PRD 维护需求与理由，references 维护具体命令和格式，避免重复维护执行手册。过程报告、模型输出、补丁和哈希清单不进入长期文档；历史原件通过 Git 历史恢复。
