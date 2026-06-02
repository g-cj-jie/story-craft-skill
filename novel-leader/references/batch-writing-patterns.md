# 批量写作模式详细指南

## 模型配置（三级）

| 用途 | 模型 | hermes CLI 参数 |
|------|------|----------------|
| 写正文 | mimo-v2.5 | `--model mimo-v2.5 --provider custom` |
| 单章审查（7维度） | mimo-v2.5 | `--model mimo-v2.5 --provider custom` |
| 每50章批量审查 | mimo-v2.5-pro | 主会话 execute_code 调用 |

**glm-4-flash 禁止用于小说创作。** 已验证其不可靠：写入截断、不调用工具、审查报告不保存。

## hermes CLI 调用方式

当需要特定模型执行子任务时，用 `hermes chat -q` CLI 替代 delegate_task：

```bash
hermes chat -q "你的prompt" --model mimo-v2.5 --provider custom -Q
```

- `-Q` 静默模式
- `--model` 和 `--provider` 直接指定，绕过 delegation config
- 返回值可靠，工具调用正确执行
- 适合批量操作（写入文件、执行命令）

### 批量章节重写脚本模板

```bash
BASE="/mnt/e/AI项目工程/小说/艾泽拉斯：死灵法师之路"
for CH in 1 6 7 8; do
    # Step 1: 写正文 (mimo-v2.5)
    hermes chat -q "你是小说写作助手。
1. 读取章纲：${BASE}/故事大纲/章纲/ch-${CH}.md
2. 用 write_file 写正文到：${BASE}/章节正文/第${CH}章.md（3500-4500中文字）
3. 用 write_file 写变动清单到：${BASE}/章节正文/第${CH}章_变动清单.md
正文要求：纯故事文本，禁止序号分段，破折号每千字≤3个" \
        --model mimo-v2.5 --provider custom -Q

    # Step 2: 单章审查 (mimo-v2.5)
    hermes chat -q "审查第${CH}章，7维度评分，写审查报告到：
${BASE}/章节正文/第${CH}章_审查报告.md" \
        --model mimo-v2.5 --provider custom -Q

    sleep 1
done
```

每章约60-120秒（写+审）。可在后台运行。

## delegate_task 批量并行模板（仅限可靠模型）

**当前 delegation.model = mimo-v2.5**，已验证通过 hermes CLI 可靠。delegate_task 可能仍使用缓存的旧模型，建议优先用 hermes CLI。

每批3章并行（受 max_concurrent_children=3 限制）：

```python
delegate_task(tasks=[
    {"goal": "写第N章...", "toolsets": ["file", "terminal"]},
    {"goal": "写第N+1章...", "toolsets": ["file", "terminal"]},
    {"goal": "写第N+2章...", "toolsets": ["file", "terminal"]},
])
```

**注意**：delegate_task 使用 config.yaml 中 delegation.model 指定的模型。如果该模型不可靠，改用 hermes CLI 方式。

## 速率限制处理

并行3个子Agent时，HTTP 429 错误常见（特别是使用免费/低配模型时）。

### 处理策略
1. **检查每个task的status**：`completed` 正常处理，`max_iterations` 或 `timeout` 需重试
2. **重试时降为单章执行**（不并行）
3. **如果连续多批都429**：改为每次只写1章，甚至暂停等待速率窗口

### 重试模板
```python
# 第一轮：3章并行
results = delegate_task(tasks=[ch_N, ch_N+1, ch_N+2])
# 检查失败的
failed = [r for r in results if r['exit_reason'] == 'max_iterations']
# 逐个重试
for task in failed:
    result = delegate_task(goal=task['goal'])
```

## 子Agent可靠性分级（2026-06-02实测）

### glm-4-flash（智谱免费模型）
- ✅ 读取文件：可靠
- ❌ 写入文件：50%概率只在回复中输出而不调用write_file
- ❌ 写入大文件：几乎必定截断（只写开头100-200字）
- ❌ 审查报告/状态更新：几乎从不执行
- **结论：不适合需要写入文件的子Agent任务**

### mimo-v2.5-pro（通过 hermes CLI）
- ✅ 读取文件：可靠
- ✅ 写入文件：可靠，内容完整
- ✅ 工具调用：正确执行
- ⚠️ 字数：有时略低于目标（2600-2800 vs 3000+）
- **结论：推荐用于小说写作，通过 hermes CLI 调用**

## 字数验证（必须执行）

**关键陷阱**：Python 的 `len(content)` 统计所有字符（含空格、标点、ASCII），不是中文字数。必须用正则统计纯中文字：

```python
import re
with open('章节正文/第N章.md', 'r', encoding='utf-8') as f:
    content = f.read()
chinese_chars = len(re.findall(r'[\u4e00-\u9fa5]', content))  # ✅ 正确
total_chars = len(content)  # ❌ 包含空格标点，不准确
```

**实测差异**：一章 14943B 的文件，`len(content)` = 5213，但纯中文字只有 4288。差距约20%。

**不要用** `read_file` 的 hermes_tools 版本做字数统计——它返回的行数格式可能干扰正则匹配。用 `open()` 直接读取。

### 达标标准
- 正文：≥3000 中文字
- 破折号密度：≤3/千字
- 不合格章节标记为需重写

## 后台进程输出捕获

`terminal(background=true)` 启动的后台进程，脚本中的 `echo` 输出**不会自动显示在 process log 中**。

### 正确做法

**方案A：重定向到文件**
```bash
bash script.sh > /tmp/output.log 2>&1 &
```
然后用 `cat /tmp/output.log` 查看。

**方案B：用 process(action='log')**
```python
process(action='log', session_id='proc_xxx', limit=50)
```
但注意：如果脚本的 stdout 被管道缓冲，可能延迟显示。

**方案C：写标记文件**
```bash
echo "$(date)" > /tmp/done.txt  # 完成标记
```
主会话检查文件是否存在判断完成。

### 推荐
对于长时间运行的批量脚本，同时使用方案A+C：重定向日志 + 写完成标记文件。

## 禁止跳步

**每章写完后必须执行完整流程**：
```
写正文 → 评审 → 修改(如需) → 变动清单 → 状态更新 → 压缩包重写
```

即使并行写作，每章的后续步骤也不得跳过。如果速率限制导致无法继续并行，改为串行执行。

### 主会话承担审查职责

当子Agent不可靠时，主会话（mimo-v2.5-pro）应承担：
1. **审查报告生成**：用 execute_code 读取正文+章纲，7维度评分，写入审查报告文件
2. **状态文件更新**：用 execute_code 批量更新写作状态/下所有文件
3. **字数验证**：写完后立即用 Python 验证实际字数

子Agent只负责正文+变动清单的写入（如果模型可靠）。
