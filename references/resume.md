# 继续上次进度

## 步骤

1. **读取最近 3 次工作摘要**
   - 优先运行脚本获取限量输出：

   ```bash
   scripts/context_keeper_probe.py resume --root <repo>
   ```

   - 默认是短输出；需要问题/经验细节时加 `--details`，需要完整快速摘要时加 `--full`。
   - 如果脚本不可用，再按下面命令手工读取。
   - 查找 `docs/worklog/` 下最新 3 个工作日志文件，按文件名排序取最后 3 个；不足 3 个则全取。
   - 每个文件只读取"快速摘要"章节，不加载完整文档。
   - 推荐命令：

   ```bash
   find docs/worklog -maxdepth 1 -type f -name '*.md' | sort | tail -3
   awk '/^## 快速摘要/{flag=1} flag{print}' <file>
   ```

2. **读取近期经验**
   - 如果 `docs/memory-keeper.md` 存在，先读顶部"主题摘要"区块：

   ```bash
   sed -n '/^## 主题摘要/,/^---/p' docs/memory-keeper.md
   ```

   - 根据用户触发语句推断任务类型：`feature` / `bugfix` / `refactor` / `research` / `config`。
   - 能推断类型时，展示同类型最近 3 条 + 不限类型最近 2 条。
   - 无法推断类型时，展示最近 5 条。
   - 先定位条目标题，再只读取需要的条目：

   ```bash
   rg -n '^## [0-9]{4}-[0-9]{2}-[0-9]{2}' docs/memory-keeper.md
   ```

3. **输出简洁续接摘要**

   ```text
   最近工作摘要：

   [1] YYYY-MM-DD - [类型] - [功能模块]
   完成：...
   下一步：...

   近期经验（最近 5 条）：
   - [类型] YYYY-MM-DD - [功能模块]：[关键经验]

   需要查看某次的完整工作日志或需求文档吗？
   ```

4. **按用户回应再加载更多**
   - 用户点名某次 worklog、plan 或具体问题时，再读取对应小段。
   - 不因"继续"默认展开完整工作日志、需求文档或全部 memory。
