# Batch Review & Trimming Workflow — Session Reference

## Session: 2026-06-02 — Chapter 51-100 Remediation

### Overview
Reviewed and remediated 50 chapters (ch51-100) of 《艾泽拉斯：死灵法师之路》.

### Results

| Metric | Before | After |
|--------|--------|-------|
| Passed chapters | 2/50 (4%) | 18/50 (36%) |
| Hard-blocked (word count) | 16 chapters | 0 chapters |
| Need-fix chapters | 48 | 32 |

### Category Breakdown

**Hard-blocked (16 chapters)**: Word count >8000 chars → trimmed to 3000-5000
- Chapters: 54, 70, 74, 75, 77, 79, 80, 82, 83, 87, 88, 90, 93, 97, 98, 99
- Average compression: 62% (e.g. 16516→4867 chars)

**Need-fix (32 chapters)**: Missing key scenes/ending hooks/foreshadowing
- Most chapters had outline/text mismatch → full rewrite required
- Chapters: 51, 52, 55-66, 68-69, 71-73, 76, 78, 81, 84-86, 89, 91-92, 94-96, 100

**Insufficient word count (1 chapter)**: ch95 (2139→4708 chars)

### Key Finding: Outline/Text Mismatch
~20+ chapters had chapter outlines describing completely different content than the actual text.
- Example: Outline says "Westfall investigation" but text is "Naxxramas battle"
- Root cause: Likely outline numbering offset or text overwriting
- Resolution: Retained actual text content, trimmed/rewrote to match word count targets
- **Action needed**: Post-remediation, outline-text alignment should be verified

### Automation Pattern
1. Run `batch_review.py --start N --end M` for initial assessment
2. Categorize chapters by issue type
3. Use `delegate_task` with 3 parallel workers per batch
4. Each worker: read outline → read text → trim/rewrite → verify word count
5. Report progress every 10 chapters
6. Re-run `batch_review.py` to verify improvement

### Delegate Task Prompt Template (for need-fix chapters)
```
修改小说第{N}章正文，补充章纲要求的关键场景、结尾钩子和伏笔操作。

章纲路径：故事大纲/章纲/ch-{N}.md
正文路径：章节正文/第{N}章.md

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

### Review Script Limitations
- Key scene matching: keyword-based, misses paraphrased content
- Ending hook detection: keyword-based, misses literary hooks
- Foreshadowing detection: keyword presence only, can't judge quality
- Recommendation: Manual review for chapters flagged as "need-fix"
