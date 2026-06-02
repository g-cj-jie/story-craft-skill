# 跨平台协作模式

## Windows Claude Agent + Hermes 协作

用户在 Windows 端运行 Claude Code agent，会自动生成评审报告并修改小说项目文件。
Hermes 在 WSL 中运行，通过 `/mnt/e/` 共享文件系统访问同一项目。

### 写前检查（每次"写小说"触发时必须执行）

1. **扫描评审报告目录**：`评审报告/` 按文件修改时间排序，检查是否有新报告
2. **读取新报告**：解析 P0/P1/P2 问题清单
3. **执行整改**：先修复问题，再写新章
4. **检查文件变动**：Windows agent 可能修改了章纲、状态文件、追踪表

### 技能同步

Windows 端的 Claude agent 会生成/更新 skills 在：
`E:\AI项目工程\小说\.claude\skills\`

需要定期同步到 Hermes：
```bash
rsync -av --delete '/mnt/e/AI项目工程/小说/.claude/skills/' '/root/.hermes/skills/novel-writing/'
```

注意 `--delete` 会删除源目录中不存在的文件。Hermes 独有的参考文件（如本目录下的 cross-platform-sync.md）会被删除，需要重新添加。

### 文件冲突处理

当两端同时修改同一文件时：
- 以 Windows agent 的修改为准（它通常在做评审和整改）
- Hermes 应专注于写新章节
- 如果发现冲突，先同步 Windows 的版本再继续

## 任务队列与重启恢复

### 任务记录

使用 `~/.hermes/scripts/task_queue.py` 管理任务：

```bash
python3 ~/.hermes/scripts/task_queue.py add "编写第X-Y章"
python3 ~/.hermes/scripts/task_queue.py start <id>
python3 ~/.hermes/scripts/task_queue.py complete <id>
python3 ~/.hermes/scripts/task_queue.py incomplete  # 查看未完成任务
```

### 重启恢复流程

网关重启后，`post_restart_recovery.sh` 会自动：
1. 检查任务队列中的未完成任务
2. 通过 QQ 发送恢复状态
3. Agent 应读取未完成任务并继续执行
