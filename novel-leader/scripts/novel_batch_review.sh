#!/bin/bash
# 批量评审章节正文 - 使用 mimo-v2.5 模型
# 每章读取章纲+正文，7维度评分，写入审查报告
#
# 用法：
#   bash novel_batch_review.sh [章节列表文件]
#   
#   章节列表文件默认: /tmp/need_review.txt（每行一个章节号）
#   如不提供，评审所有缺失审查报告的章节

BASE="/mnt/e/AI项目工程/小说/艾泽拉斯：死灵法师之路"
REVIEW_LIST="${1:-/tmp/need_review.txt}"

# 如果没有列表文件，自动生成
if [ ! -f "$REVIEW_LIST" ]; then
    python3 -c "
import os
base = '${BASE}/章节正文'
need = []
for ch in range(1, 201):
    if not os.path.exists(os.path.join(base, f'第{ch}章_审查报告.md')):
        need.append(ch)
for ch in need:
    print(ch)
" > "$REVIEW_LIST"
fi

CHAPTERS=$(cat "$REVIEW_LIST" | tr '\n' ' ')
TOTAL=$(wc -l < "$REVIEW_LIST")
COUNT=0
SUCCESS=0
FAIL=0

for CH in $CHAPTERS; do
    COUNT=$((COUNT + 1))
    echo "[$COUNT/$TOTAL] 评审第${CH}章..."
    
    PROMPT="你是小说评审助手。请对第${CH}章进行7维度评审。

1. 读取正文：${BASE}/章节正文/第${CH}章.md
2. 读取章纲：${BASE}/故事大纲/章纲/ch-${CH}.md
3. 按以下7维度评分（总分100分）：
   - 章纲一致性（30分）：章纲目标是否达成、关键场景是否覆盖
   - 三层叙事完整性（20分）：主线推进+结构呼应+章末钩子
   - 世界观一致性（15分）：魔兽世界设定是否正确
   - 人物一致性（10分）：角色行为是否合理
   - 文风一致性（10分）：破折号密度≤3/千字、无序号分段、无陈词滥调
   - 字数达标（5分）：3000-5000中文字
   - 伏笔/子剧情（10分）：章纲指定的伏笔操作是否执行
4. 用 write_file 将审查报告写入：${BASE}/章节正文/第${CH}章_审查报告.md

审查报告格式：
# 第${CH}章审查报告
## 评分汇总
| 维度 | 得分 | 满分 | 备注 |
|------|------|------|------|
| 章纲一致性 | X | 30 | [扣分原因] |
| 三层叙事完整性 | X | 20 | [扣分原因] |
| 世界观一致性 | X | 15 | [扣分原因] |
| 人物一致性 | X | 10 | [扣分原因] |
| 文风一致性 | X | 10 | [扣分原因] |
| 字数达标 | X | 5 | [实际字数] |
| 伏笔/子剧情 | X | 10 | [扣分原因] |
| **总分** | **XX** | **100** | |
## 判定: 通过(≥80) / 需修改(<80)
## 问题清单（如有）
## 亮点记录（如有）

必须用 write_file 写入文件。"

    RESULT=$(timeout 120 hermes chat -q "$PROMPT" --model mimo-v2.5 --provider custom -Q 2>&1)
    
    REVIEW_FILE="${BASE}/章节正文/第${CH}章_审查报告.md"
    if [ -f "$REVIEW_FILE" ]; then
        SCORE=$(python3 -c "
import re
with open('$REVIEW_FILE','r') as f: c=f.read()
m=re.search(r'总分.*?(\d+)', c)
print(m.group(1) if m else '?')
" 2>/dev/null)
        echo "  ✅ 审查报告已生成 (总分${SCORE}分)"
        SUCCESS=$((SUCCESS + 1))
    else
        echo "  ❌ 审查报告未生成"
        FAIL=$((FAIL + 1))
    fi
    
    sleep 1
done

echo ""
echo "=== 批量评审完成 ==="
echo "成功: $SUCCESS/$TOTAL"
echo "失败: $FAIL/$TOTAL"
echo "$(date '+%Y-%m-%d %H:%M:%S')" > /tmp/novel_review_done.txt
