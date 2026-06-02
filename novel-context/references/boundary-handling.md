# 边界处理与新会话恢复

## 篇结束时

novel-context 输出"篇结束包"：
1. 清理归档：所有已填伏笔、已完成子剧情移入 archive/
2. 更新 current-position：篇号+1，章号=1
3. 生成新篇的 arc-brief-current.md（需要 novel-design 提供新篇纲）
4. 输出篇统计：总章数、总字数、子剧情完成情况、伏笔操作统计
5. 回报 leader，暂停等待用户审查

## 卷结束时

在篇结束基础上增加：
1. 生成卷级摘要到 `state/volume-summary-X-Y.md`：
   - 人物状态变化总览
   - 势力格局变化总览
   - 待填伏笔总览
2. 回报 leader，暂停等待用户审查

## 部结束时

在卷结束基础上增加：
1. 生成部级摘要到 `state/part-summary-X.md`
2. 状态转为 REVIEW_PART
3. 回报 leader，暂停等待用户审查

## 新会话恢复

state/ 目录在任意时刻都是完整的"当前状态快照"。新会话中 leader 只需：

1. 读 `state/current-position.md` → 知道写到哪里
2. 读 `state/recent-summary.md` → 知道最近发生了什么
3. 读 `state/arc-brief-current.md` → 知道当前篇上下文
4. 读其他 state/ 文件 → 知道当前所有活跃的人物/势力/伏笔/子剧情
5. 读 `outline/` 下的当前篇纲 → 知道接下来的写作计划

**不需要任何对话历史**。第一章到第五百章都适用。
