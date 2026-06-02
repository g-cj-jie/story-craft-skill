# Batch Chapter Review & Fix Patterns

## Overview

When reviewing and fixing large batches of chapters (10+ chapters), use `delegate_task` with batches of 3 parallel subagents. This session successfully fixed 49 chapters (51-100) in ~10 batches over ~2 hours.

## Workflow

### Step 1: Categorize Issues

From the review report, classify chapters into priority tiers:

| Tier | Description | Count (example) | Priority |
|------|-------------|-----------------|----------|
| Hard-blocked | Word count >6000 or <3000 | 16 | Highest |
| Needs modification | Missing scenes, hooks, foreshadowing | 32 | High |
| Passed | Score ≥80 | 2 | Skip |

### Step 2: Process in Batches of 3

Use `delegate_task` with 3 tasks per batch (max concurrent for this user):

```python
delegate_task(tasks=[
    {"goal": "精简小说第N章正文，从XXXXX字精简到3000-5000字范围...", "toolsets": ["terminal", "file"]},
    {"goal": "修改小说第M章正文，补充章纲要求的关键场景...", "toolsets": ["terminal", "file"]},
    {"goal": "修改小说第K章正文...", "toolsets": ["terminal", "file"]}
])
```

### Step 3: Context for Each Subagent

Each subagent needs:
- **Chapter outline path**: `/mnt/e/AI项目工程/小说/艾泽拉斯：死灵法师之路/故事大纲/章纲/ch-NN.md`
- **Chapter text path**: `/mnt/e/AI项目工程/小说/艾泽拉斯：死灵法师之路/章节正文/第NN章.md`
- **Specific instructions**: What to fix (trim, rewrite, supplement)
- **Style requirements**: Short sentences, em-dash ≤3 per 1000 chars, 3000-6000 word target

### Step 4: Track Progress

Use `todo` tool to track batches. Report progress every 10 chapters.

## Common Patterns Found

### Pattern A: Outline-Text Mismatch (~40% of chapters)
- Chapter outline describes one story (e.g., "Defias investigation")
- Chapter text tells a completely different story (e.g., "Naxxramas battle")
- **Fix**: Rewrite the chapter text to match the outline, using the outline's key scenes

### Pattern B: Excessive Word Count (~30% of chapters)
- Chapters with 6000-16000 characters (target: 3000-6000)
- Usually caused by excessive environment descriptions, repeated mental analysis
- **Fix**: Trim by removing redundant descriptions, compressing dialogue, cutting repeated analysis

### Pattern C: Missing Narrative Elements (~50% of chapters)
- Missing 3 key scenes from outline
- Missing ending hook (结尾钩子)
- Missing foreshadowing operations (伏笔操作)
- **Fix**: Read outline, identify gaps, add missing elements

## Subagent Prompt Template

```
章纲路径：/mnt/e/AI项目工程/小说/艾泽拉斯：死灵法师之路/故事大纲/章纲/ch-NN.md
正文路径：/mnt/e/AI项目工程/小说/艾泽拉斯：死灵法师之路/章节正文/第NN章.md

整改要求：
- 读取章纲了解关键场景、结尾钩子、伏笔操作
- 读取当前正文
- 对照章纲，补充缺失的关键场景
- 补充结尾钩子
- 确保伏笔操作在正文中体现
- 调整字数到3000-5000字范围
- 保持文风一致（短句、破折号≤3个/千字）
- 写入修改后的正文到原文件路径
```

## Performance Metrics (from this session)

- 49 chapters fixed in ~2 hours
- Average ~2.5 minutes per chapter (parallel processing)
- Batch size: 3 concurrent subagents
- 10 batches total
- Success rate: 100% (all chapters completed)

## Pitfalls

1. **Subagent context limits**: Each subagent reads 2+ files (outline + text). Keep outlines concise.
2. **Max iterations**: Complex chapters may hit max_iterations. The subagent will still complete the work.
3. **File write verification**: Always verify the file was actually written by checking word count after.
4. **Outline-text mismatch**: Very common (~40%). Decide upfront whether to match text to outline or vice versa.
