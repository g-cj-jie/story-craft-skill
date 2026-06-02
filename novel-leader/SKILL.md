---
name: novel-leader
description: "长篇小说写作调度中心。维护写作阶段状态机，自动串行调度子Skill（prep/design/write/review/context），支持批量写作循环。用户只需对话交互，无需手动调用子Skill。"
version: "2.0"
author: "hermes-agent"
tags: ["novel", "orchestrator", "workflow"]
---

# novel-leader

## 适用边界

触发条件：用户提及"写小说""开始写""继续写""写下一章""开始写第X篇""写完这一篇"等，或项目处于写作进行中。

不适用：单篇短篇小说（<3万字）、非小说的写作任务。

## 执行主流程

### 步骤1：判断当前阶段

读 `写作状态/当前位置.md`，确定当前处于 INIT / PREP / DESIGN / WRITING / REVIEW_PART / COMPLETE 哪个阶段。

### 步骤2：按阶段调度

- **INIT**：收集题材、类型、篇幅、目标读者信息，完成后转 PREP
- **PREP**：调用 novel-prep 进行资料准备，完成后用户确认转 DESIGN
- **DESIGN**：调用 novel-design 生成部纲→卷纲→篇纲→章纲，篇纲就绪后用户说"开始写"转 WRITING
- **WRITING**：执行写作循环（步骤3），到达部边界转 REVIEW_PART
- **REVIEW_PART**：输出部级汇总，等候用户审查决定

### 步骤2.5：进度检查与写前准备

#### 进度查询（用户问"写完了吗""进度如何"时）

用 Python 统计章节正文文件，不要用 shell sort（中文文件名排序有坑）：

```python
python3 -c "
import os, re
dir_path = '章节正文目录'
files = [f for f in os.listdir(dir_path) if re.match(r'第\d+章\.md$', f)]
chapters = sorted([int(re.search(r'(\d+)', f).group(1)) for f in files])
missing = [i for i in range(1, max(chapters)+1) if i not in chapters]
print(f'已完成: {len(chapters)}章, 最新: 第{max(chapters)}章')
if missing: print(f'缺失: {missing}')
"
```

**不要用** `ls | sort -t'第'` — `sort` 的 `-t` 不支持多字节字符作为分隔符。同样避免 `sort -t'章'`，会报错 "multi-character tab"。

#### 变动清单/审查报告覆盖检查

同时检查评审流程是否完整执行：
```python
import os, re
chapter_dir = '章节正文/'
dongqing = [int(re.search(r'(\d+)', f).group(1)) for f in os.listdir(chapter_dir) if '_变动清单.md' in f]
shencha = [int(re.search(r'(\d+)', f).group(1)) for f in os.listdir(chapter_dir) if '_审查报告.md' in f]
print(f'变动清单覆盖: {len(dongqing)}章, 审查报告覆盖: {len(shencha)}章')
```
如果覆盖数远小于章节数，说明评审流程被跳过。

#### 写前检查（每次"写小说"触发时）

用户说"写小说"时，**在开始新章节前**先执行以下检查：

1. **评审报告检查**：扫描 `评审报告/` 目录，按时间排序。如果有比上次写作更新的报告，先执行整改再写新章。
2. **状态文件一致性**：读 `写作状态/当前位置.md`，确认进度与实际章节正文文件数一致。
3. **章纲就绪**：确认下一章的章纲文件（ch-N.md）存在。

### 步骤3：写作循环（WRITING阶段核心）

**强制约束：每章必须串行执行完整流程，任何环节不得跳过。**

#### 强制单章流程（不可跳过）

```
┌──────────────────────────────────────────────────────────────┐
│              每章强制流程（串行，不可跳步）                      │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  1. [子Agent] novel-write → 写入 章节正文/第N章.md            │
│              ↓                                               │
│  2. [脚本] 单章内容评审（两阶段评审）                          │
│     ├─ 阶段1：字数判断（3000-6000字，否则硬阻断→重写）         │
│     ├─ 阶段2：脚本评审正文对照章纲关键信息缺失                  │
│     └─ 阶段3：脚本失败内容送LLM判断                            │
│              ↓                                               │
│  3. 评审结果分流：                                            │
│     ├─ ✅ 通过 → 继续第4步                                    │
│     └─ ❌ 不通过 → 根据评审问题修改正文 → 回到第2步重新评审     │
│              ↓                                               │
│  4. [子Agent] novel-context → 更新写作状态/全部文件             │
│              ↓                                               │
│  5. 记录变动清单 + 审查报告                                    │
│              ↓                                               │
│  6. 继续下一章（回到第1步）                                    │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**关键约束：**
- novel-write、novel-review、novel-context 以子Agent方式运行，拥有独立干净上下文
- **单章修改最多3次**：3次评审仍不通过则暂停，上报leader决策
- **任何环节不得跳过**。即使批量写作，也必须逐章完成上述全流程

#### 两阶段评审细则（步骤2展开）

##### 阶段1：字数判断（脚本硬阻断）

用 Python 脚本检查章节字数：
- **3000-6000字**：通过，进入阶段2
- **<3000字 或 >6000字**：硬阻断，直接标记不通过，必须重写/扩充/拆分
- 硬阻断章节不进入LLM评审，直接返回重写

```python
# 字数检查（集成在 batch_review.py 中）
def check_hard_blocks(ch):
    if ch["word_count"] < 3000:
        return f"字数严重不足：{ch['word_count']}字（<3000字，需扩充）"
    elif ch["word_count"] > 6000:
        return f"字数严重超标：{ch['word_count']}字（>6000字，需拆分）"
    return None
```

##### 阶段2：脚本评审正文对照章纲（关键词匹配）

用关键词匹配检测正文是否覆盖章纲关键信息：
- 章纲关键场景是否在正文中出现（同义词匹配）
- 伏笔操作是否体现
- 世界观违规检测（现代物品、其他世界内容）
- 主角姓名是否出现
- 结尾钩子是否存在
- 破折号密度、序号标记、重复句式检测

评分≥80分 → 通过。评分<80分 → 进入阶段3（LLM复核）。

##### 阶段3：LLM判断（语义复核）

章节正文送LLM进行语义评审：
- **LLM认为通过（误报）** → 脚本规则过于严格，自动更新脚本规则（扩充同义词/放宽关键词），章节标记为通过
- **LLM认为失败（确认）** → 章节标记为不通过，根据LLM评审意见重写正文，回到阶段1重新评审
- **LLM判定不一致** → 暂停，上报leader人工决策

##### 评审结果输出

```
┌──────────────────────────────────────────┐
│  单章评审结果分类                          │
├──────────────────────────────────────────┤
│  ✅ 直接通过：字数达标 + 脚本评分≥80       │
│  ✅ LLM通过：脚本误报，LLM判定合格         │
│  🔴 硬阻断：字数<3000或>6000，必须重写     │
│  ❌ 确认失败：LLM判定不合格，根据意见重写   │
│  ⚠️ 需人工：LLM判定不一致，暂停处理        │
└──────────────────────────────────────────┘
```

#### 批量写作模式

批量写作时，**每章仍必须串行完成上述全流程**，不可并行跳过评审环节。

**两种执行方式**（根据模型可靠性选择）：

**方式A：hermes CLI 脚本（推荐）**

```bash
for CH in $CHAPTERS; do
    hermes chat -q "写第${CH}章..." --model mimo-v2.5-pro --provider custom -Q
done
```

详见 references/batch-rewrite-patterns.md。

**方式B：delegate_task 串行**

```
1. 读取上下文压缩包 + 章纲
2. delegate_task 写入章节正文
3. 执行两阶段评审（脚本+LLM）
4. 通过 → delegate_task 更新上下文/状态/记录
5. 不通过 → delegate_task 修改正文 → 回到步骤3
6. 继续下一章
```

**速率限制处理**：连续429时降速为单章串行，不跳步。

**QQ汇报时机**：每批完成后通过 `hermes send --to qqbot` 发送简要进度，不要每章都发。

### 步骤3.5：批量评审（对已完成但未评审的章节）

对已写完但跳过了评审流程的章节，使用两阶段批量评审脚本补审：

```bash
# 两阶段评审（脚本+LLM，自动处理误报）
python3 .claude/skills/novel-review/references/two_stage_review.py \
  --start 1 --end 100 --update-rules

# 只运行脚本检测（不调用LLM，快速预览）
python3 .claude/skills/novel-review/references/two_stage_review.py \
  --start 1 --end 100 --report-only
```

**两阶段流程（同步骤2的展开版）：**
1. **阶段1 - 字数脚本**：字数<3000或>6000 → 硬阻断，标记重写，不送LLM
2. **阶段2 - 内容脚本**：关键词匹配章纲一致性、世界观、文风等，评分≥80通过
3. **阶段3 - LLM复核**：评分<80的送LLM语义评审
   - LLM通过（误报）→ 自动扩充脚本规则，章节通过
   - LLM失败（确认）→ 标记需重写
   - LLM不一致 → 标记需人工复核

**输出报告分类：**
- 🔴 硬阻断：字数<3000或>6000，需扩充/拆分
- ❌ LLM确认失败：内容问题，需重写
- ✅ 脚本误报：内容合格，规则已更新，无需修改

### 步骤4：上下文组装

从 `写作状态/` 和 `故事大纲/` 加载当前上下文包。**绝对禁止加载前文章节全文。** 总Token控制在4000~6000。详见 references/context-assembly.md。

### 步骤5：新会话恢复

无历史上下文时，读取 `写作状态/` 全部文件恢复写作进度。

## 严重警告：禁止跳步写入

**绝对禁止只写正文不更新状态。** 历史教训：批量写作时跳过评审和状态更新，导致147章（ch52-198）无状态跟踪、无评审、无变动清单，状态文件冻结在第51章。事后补救成本远高于事前评审。

### 每章必须执行的完整流程（不可裁剪）

```
写正文 → 两阶段评审（字数脚本+内容脚本+LLM复核）
       ↓
    通过(≥80分) → 变动清单 → 状态更新 → 压缩包重写 → 下一章
       ↓
    不通过(<80分) → 根据评审意见修改正文 → 重新评审（最多3次）
       ↓
    3次仍不通过 → 暂停，上报leader决策
```

**任何环节不得跳过。** 如果因速率限制等原因无法并行，宁可放慢速度（单章串行），也不能跳步。

### 硬阻断红线（不可覆盖）

以下情况直接判定不通过，不送LLM复核：
- 字数 < 3000字 → 扩充至3000字以上
- 字数 > 6000字 → 拆分或精简
- 出现严重世界观破坏（异世界出现手机、电脑等现代物品）
- 正文完全偏离章纲（关键场景全部缺失）

### 状态文件一致性检查（每次写前必做）

用 Python 统计实际章节数，与 `写作状态/当前位置.md` 对比：

```python
python3 -c "
import os, re
dir_path = '章节正文目录'
files = [f for f in os.listdir(dir_path) if re.match(r'第\\d+章\\.md$', f)]
chapters = sorted([int(re.search(r'(\\d+)', f).group(1)) for f in files])
print(f'实际章节: {len(chapters)}章, 最新: 第{max(chapters)}章')
"
```

如果实际章节数远大于当前位置记录，说明存在跳步写入，需要先恢复状态再继续。

### 状态文件恢复流程（当检测到严重断层时）

1. 读取最新几章正文，重建近期摘要
2. 从正文中提取当前人物/伏笔/势力状态
3. 更新 `写作状态/` 所有文件
4. 重建上下文压缩包
5. 确认恢复后再继续写作

## 扩展引用规则

| 时机 | 文件 | 说明 |
|------|------|------|
| 需要判断阶段转换条件时 | references/state-machine.md | 查状态定义、转换条件、暂停条件 |
| 需要组装上下文包和子Agent调用时 | references/context-assembly.md | 查加载清单、Token控制、子Agent调用模板、项目文件结构 |
| 需要了解子Skill详细能力时 | 对应子Skill的 SKILL.md | novel-prep/design/write/review/context |
| 需要运营/管理/发布的方法论时 | references/operations.md | 查编辑决策、运营策略、读者反馈、市场分析、发布流程 |
| 批量并行写作时 | references/batch-writing-patterns.md | delegate_task模板、速率限制处理、QQ汇报时机、字数验证 |
| 处理评审报告时 | references/review-fix-patterns.md | 报告分类、并行修复模板、选项B策略 |
| 配置写作模型/调用方式时 | references/model-config.md | 三级模型架构、glm-4-flash禁用原因、hermes CLI调用、delegate_task限制 |
| 批量并行写作时 | references/batch-writing-patterns.md | delegate_task模板、速率限制处理、QQ汇报时机、字数验证 |
| 批量重写/扩充章节时 | references/batch-rewrite-patterns.md | bash脚本模板、字数验证、重试策略、每50章批量审查 |
| 批量评审/整改章节时 | references/batch-review-fix-patterns.md | delegate_task并行处理、常见问题分类、subagent模板 |
| 两阶段评审（脚本+LLM） | novel-review skill | 使用 two_stage_review.py，硬阻断跳过LLM，误报自动更新规则 |
| 跨平台协作时 | references/cross-platform-sync.md | Windows agent协作、技能同步、任务队列与重启恢复 |

## 输出要求

每次执行结束输出：
1. 当前阶段和进度位置
2. 本轮执行结果（完成的操作、章节数、字数）
3. 下一步建议动作
4. 如需用户决策，明确列出选项
