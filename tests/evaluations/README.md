# 无模型评估支持

本目录不包含真实模型调用、认证发现或本机历史目录默认值。

- `memory_baseline.py`：在新输出目录生成合成记录并运行当前probe；子进程使用新建隔离home。源码导出没有Git时提交标识为null，不妨碍执行。
- `evaluation_contract.py`：生成一致预算与保守的提示归属判定；混合输出交人工核查。
- `evaluation_support.py`：以显式路径准备合成项目、渲染保护profile、验证公开输入及回滚显式拥有的链接。调用者必须提供自己的模板/输入；它不发现配置、认证或历史批次，也不运行模型。

```bash
python3 tests/evaluations/memory_baseline.py --output /新的绝对输出目录
python3 -m unittest discover -s tests
```

真实文件系统回归使用临时合成内容。macOS的保护测试会真实调用sandbox-exec；不支持seatbelt的平台会按已有平台条件单列skip。不得用这些帮助函数的通过结果宣称真实CLI/provider、认证刷新、跨宿主或业务端到端验收完成。历史真实模型编排与运行证据保存在仓库外归档；本目录不依赖该归档即可运行合成回归。验证范围见[记忆可靠性PRD](../../docs/prd/memory-reliability.md)。
