# 跨平台同步：Hermes ↔ Claude Code

## 目录映射

| Hermes (WSL) | Claude Code (Windows) |
|---|---|
| `~/.hermes/skills/novel-writing/` | `E:\AI项目工程\小说\.claude\skills\` |

两个目录包含相同的6个skill子目录：novel-context, novel-design, novel-leader, novel-prep, novel-review, novel-write

## 同步方法

### 从 Hermes 同步到 Claude Code

```python
import shutil
from pathlib import Path

hermes = Path("/root/.hermes/skills/novel-writing")
claude = Path("/mnt/e/AI项目工程/小说/.claude/skills")

# 全量同步（覆盖同名文件，新增不同文件）
for src in hermes.rglob("*"):
    if src.is_file() and '__pycache__' not in str(src) and src.suffix != '.pyc':
        dst = claude / src.relative_to(hermes)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
```

### 从 Claude Code 同步到 Hermes

```python
for src in claude.rglob("*"):
    if src.is_file() and src.suffix != '.pyc':
        dst = hermes / src.relative_to(claude)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
```

## 注意事项

1. **Python脚本路径**：`batch_review.py` 中的 `DEFAULT_BASE` 使用绝对路径 `/mnt/e/...`，在Windows端运行时需注意WSL路径兼容性
2. **API密钥**：`llm_reviewer.py` 中的API密钥硬编码在脚本中，两端同步后都会生效
3. **规则更新日志**：`rules_update_log.json` 只在运行端产生，不会自动同步
4. **__pycache__**：同步时排除 `__pycache__/` 和 `.pyc` 文件
5. **CLAUDE.md**：项目根目录的 `CLAUDE.md` 是 Claude Code 的项目说明，Hermes端不需要
