#!/bin/bash
# 批量重写不完整章节 - 使用 mimo-v2.5 模型
# 写正文 + 变动清单 + 单章审查
#
# 用法：
#   bash novel_batch_rewrite.sh [章节列表文件]
#   
#   章节列表文件默认: /tmp/incomplete_chapters.txt（每行一个章节号）
#   如不提供，重写所有字数不足的章节

BASE="/mnt/e/AI项目工程/小说/艾泽拉斯：死灵法师之路"
REWRITE_LIST="${1:-/tmp/incomplete_chapters.txt}"

# 如果没有列表文件，自动生成（字数<3000的章节）
if [ ! -f "$REWRITE_LIST" ]; then
    python3 -c "
import os, re
base = '${BASE}/章节正文'
need = []
for ch in range(1, 201):
    path = os.path.join(base, f'第{ch}章.md')
    if os.path.exists(path):
        with open(path, 'r') as f: content = f.read()
        if len(re.findall(r'[\u4e00-\u9fa5]', content)) < 3000:
            need.append(ch)
    else:
        need.append(ch)
for ch in need:
    print(ch)
" > "$REWRITE_LIST"
fi

CHAPTERS=$(cat "$REWRITE_LIST" | tr '\n' ' ')
TOTAL=$(wc -l < "$REWRITE_LIST")
COUNT=0
SUCCESS=0
FAIL=0

for CH in $CHAPTERS; do
    COUNT=$((COUNT + 1))
    echo "[$COUNT/$TOTAL] 写第${CH}章..."
    
    # Step 1: 写正文 + 变动清单
    WRITE_PROMPT="你是小说写作助手。请执行以下任务：
1. 读取章纲：${BASE}/故事大纲/章纲/ch-${CH}.md
2. 用 write_file 写正文到：${BASE}/章节正文/第${CH}章.md
3. 用 write_file 写变动清单到：${BASE}/章节正文/第${CH}章_变动清单.md

正文要求：
- 纯故事文本，必须写满3500-4500中文字（少于3500字不合格）
- 禁止序号分段（不要用## 一、1.、第一幕等）
- 破折号——每千字最多3个
- 细腻感官描写，禁止陈词滥调
- 段落长短交替
- 章节标题格式：# 第${CH}章：标题"

    RESULT=$(timeout 180 hermes chat -q "$WRITE_PROMPT" --model mimo-v2.5 --provider custom -Q 2>&1)
    
    if [ $? -ne 0 ]; then
        echo "  ❌ 写正文超时/失败"
        FAIL=$((FAIL + 1))
        continue
    fi

    FILE="${BASE}/章节正文/第${CH}章.md"
    if [ ! -f "$FILE" ]; then
        echo "  ❌ 正文文件未创建"
        FAIL=$((FAIL + 1))
        continue
    fi
    
    CHARS=$(python3 -c "
import re
with open('$FILE','r') as f: content=f.read()
print(len(re.findall(r'[\u4e00-\u9fa5]',content)))
")
    
    if [ "$CHARS" -lt 3000 ]; then
        echo "  ⚠️ 正文${CHARS}字(需≥3000)，重试..."
        RESULT=$(timeout 180 hermes chat -q "${WRITE_PROMPT} 之前的版本只有${CHARS}字，不够。请重写，确保至少3500中文字。" --model mimo-v2.5 --provider custom -Q 2>&1)
        CHARS=$(python3 -c "
import re
with open('$FILE','r') as f: content=f.read()
print(len(re.findall(r'[\u4e00-\u9fa5]',content)))
")
    fi

    # Step 2: 单章审查
    REVIEW_PROMPT="你是小说评审助手。审查第${CH}章。

读取正文：${BASE}/章节正文/第${CH}章.md
读取章纲：${BASE}/故事大纲/章纲/ch-${CH}.md

按7维度评分（章纲一致性30/三层叙事20/世界观15/人物10/文风10/字数5/伏笔10），总分100分。

用 write_file 将审查报告写入：${BASE}/章节正文/第${CH}章_审查报告.md"

    timeout 120 hermes chat -q "$REVIEW_PROMPT" --model mimo-v2.5 --provider custom -Q > /dev/null 2>&1
    
    REVIEW_FILE="${BASE}/章节正文/第${CH}章_审查报告.md"
    if [ -f "$REVIEW_FILE" ]; then
        SCORE=$(python3 -c "
import re
with open('$REVIEW_FILE','r') as f: c=f.read()
m=re.search(r'总分.*?(\d+)', c)
print(m.group(1) if m else '?')
" 2>/dev/null)
        echo "  ✅ 第${CH}章: ${CHARS}字, 评审${SCORE}分"
    else
        echo "  ✅ 第${CH}章: ${CHARS}字, 审查报告未生成"
    fi
    SUCCESS=$((SUCCESS + 1))
    
    sleep 1
done

echo ""
echo "=== 批量写作完成 ==="
echo "成功: $SUCCESS/$TOTAL"
echo "失败: $FAIL/$TOTAL"
echo "$(date '+%Y-%m-%d %H:%M:%S')" > /tmp/novel_batch_done.txt
