# 批量重写模式

## 场景

当大量章节需要重写/扩充时（如质量不达标、字数不足、模型更换后重写），使用 bash 脚本批量调用 hermes CLI。

## 核心脚本模板

```bash
#!/bin/bash
BASE="/mnt/e/AI项目工程/小说/艾泽拉斯：死灵法师之路"
CHAPTERS="1 6 7 8 9 11 12 13 14 15"  # 需重写的章节号列表

for CH in $CHAPTERS; do
    echo "写第${CH}章..."
    
    # Step 1: 写正文 + 变动清单
    hermes chat -q "你是小说写作助手。
1. 读取章纲：${BASE}/故事大纲/章纲/ch-${CH}.md
2. 用 write_file 写正文到：${BASE}/章节正文/第${CH}章.md
3. 用 write_file 写变动清单到：${BASE}/章节正文/第${CH}章_变动清单.md
正文要求：3500-4500中文字，纯故事文本，禁止序号分段，破折号每千字≤3个" \
        --model mimo-v2.5 --provider custom -Q
    
    # Step 2: 单章审查
    hermes chat -q "你是小说评审助手。读取 ${BASE}/章节正文/第${CH}章.md 和 ${BASE}/故事大纲/章纲/ch-${CH}.md，按7维度评分，用 write_file 写审查报告到 ${BASE}/章节正文/第${CH}章_审查报告.md" \
        --model mimo-v2.5 --provider custom -Q
    
    sleep 1
done
```

## 字数验证

hermes CLI 写入后必须验证字数：

```python
import re
with open(f"第{ch}章.md", 'r') as f:
    content = f.read()
chinese_chars = len(re.findall(r'[\u4e00-\u9fa5]', content))
# 达标标准：≥3000字
```

## 重试策略

如果字数不足（<3000字），在 prompt 中追加字数不足的提示并重试：
```bash
hermes chat -q "$PROMPT 之前的版本只有${CHARS}字，不够。请重写，确保至少3500中文字。" \
    --model mimo-v2.5 --provider custom -Q
```

## 每50章批量审查

写完一批章节后，用 mimo-v2.5-pro 做整体审查：

```bash
hermes chat -q "你是小说审查助手。
读取以下文件：
- 大纲总览：${BASE}/故事大纲/部纲/第一部_穿越与新手期.md
- 篇纲：${BASE}/故事大纲/篇纲/第X篇_xxx.md
- 第1-50章正文：${BASE}/章节正文/第1章.md ~ 第50章.md

检查：
1. 章纲一致性：正文是否偏离大纲规划
2. 人物发展线：角色行为是否连贯
3. 伏笔追踪：伏笔是否正确埋设/推进
4. 世界观一致性：是否有矛盾
5. 节奏把控：快慢是否合理

输出审查报告到 ${BASE}/评审报告/batch_review_1-50.md" \
    --model mimo-v2.5-pro --provider custom -Q
```

### 批量单章审查脚本模板

当需要对大量章节做章纲对比评审时（如171章需评审），用 bash 脚本：

```bash
#!/bin/bash
BASE="/mnt/e/AI项目工程/小说/艾泽拉斯：死灵法师之路"
CHAPTERS="5 6 8 9 10 ..."  # 需评审的章节号

for CH in $CHAPTERS; do
    PROMPT="你是小说评审助手。请对第${CH}章进行7维度评审。

1. 读取正文：${BASE}/章节正文/第${CH}章.md
2. 读取章纲：${BASE}/故事大纲/章纲/ch-${CH}.md
3. 按7维度评分（章纲一致性30/三层叙事20/世界观15/人物10/文风10/字数5/伏笔10）
4. 用 write_file 写审查报告到：${BASE}/章节正文/第${CH}章_审查报告.md

格式：评分汇总表 + 判定(通过≥80/需修改<80) + 问题清单 + 亮点记录"

    timeout 120 hermes chat -q "$PROMPT" --model mimo-v2.5 --provider custom -Q
    sleep 1
done
```

脚本模板：`~/.hermes/scripts/novel_batch_review.sh`

## 进度追踪

```python
import os, re
chapter_dir = "章节正文/"
complete = 0
for ch in range(1, 201):
    path = os.path.join(chapter_dir, f"第{ch}章.md")
    if os.path.exists(path):
        with open(path, 'r') as f:
            content = f.read()
        if len(re.findall(r'[\u4e00-\u9fa5]', content)) >= 3000:
            complete += 1
print(f"完成: {complete}/200章")
```

## 状态更新

批量写完后，必须更新写作状态文件：
1. 当前位置.md — 更新到最新章节
2. 近期摘要.md — 最近3章摘要
3. 上下文压缩包.md — 重写
4. 人物状态.md — 更新出场人物
5. 伏笔台账.md — 更新伏笔状态
6. 当前篇简报.md — 更新篇进度

状态更新在主会话用 execute_code 执行（不委托子Agent）。

## 历史教训

### 2026-06-02：glm-4-flash 导致147章跳步

- 使用 glm-4-flash 模型批量写章节时，子Agent只写了正文，跳过了评审和状态更新
- 结果：147章（52-198章）无审查报告、无变动清单、状态文件冻结
- 修复：切换到 mimo-v2.5 模型，用 hermes CLI 脚本批量处理
- 根因：glm-4-flash 的 tool calling 不可靠

### 2026-06-02：delegate_task model override 不生效

- delegate_task 的 model 参数被忽略，始终使用 config 中的 delegation.model
- 修复：改用 hermes chat CLI 直接调用
