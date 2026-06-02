# 模型配置与调用方式

## 三级模型架构

| 用途 | 模型 | 调用方式 | 说明 |
|------|------|---------|------|
| 写正文 | mimo-v2.5（非pro） | `hermes chat -q` CLI | 创意写作，性价比最优 |
| 单章审查 | mimo-v2.5（非pro） | `hermes chat -q` CLI | 7维度评分，快速反馈 |
| 每50章批量审查 | mimo-v2.5-pro | 主会话直接执行 | 对照大纲/部纲/章纲做整体一致性审查 |

## 禁用模型

**glm-4-flash 禁止用于任何小说创作操作。** 

### 失败模式（2026-06-02 实测）

1. **不写文件**：子Agent声称用 write_file 写入了文件，但实际未调用工具（tool_trace 中无 write_file 调用）。概率约50%。
2. **字数不足**：生成内容只有摘要级别（100-300字），远达不到3000字要求。
3. **不写审查报告**：生成评分内容在回复文本中，但不写入文件。
4. **不更新状态文件**：声称更新了6个状态文件，实际一个都没写。

### 根因

glm-4-flash 模型的 tool calling 能力弱——它能正确生成 write_file 调用的参数，但经常不实际发出调用，而是把内容放在回复文本中。这是模型层面的问题，不是 prompt 或配置问题。

## delegate_task 的 model override 问题

**delegate_task 的 `model` 参数不生效。** 即使传入：
```python
delegate_task(goal="...", model={"model": "mimo-v2.5", "provider": "custom"})
```
子Agent仍使用 config.yaml 中 delegation.model 配置的模型。

### 正确调用方式

用 `hermes chat -q` CLI 替代 delegate_task：

```bash
hermes chat -q "写第N章正文..." --model mimo-v2.5 --provider custom -Q
```

优点：
- 模型切换100%可靠
- 支持超时控制（timeout 180）
- 可在 bash 脚本中循环调用
- 输出可通过日志捕获

缺点：
- 每次调用启动新进程（~3秒开销）
- 无工具集限制（会使用所有可用工具）
- 需要在脚本中处理文件名转义

## 配置命令

```bash
# 设置 delegation 模型（影响 delegate_task）
hermes config set delegation.model mimo-v2.5
hermes config set delegation.provider custom

# 设置主会话模型
hermes config set model.default mimo-v2.5-pro
hermes config set model.provider custom
```

## 模型端点

```yaml
# config.yaml
model:
  provider: custom
  base_url: https://token-plan-cn.xiaomimimo.com/anthropic
  api_key: <mimo-api-key>
  default: mimo-v2.5-pro

custom_providers:
  - name: zhipu
    api_format: openai
    base_url: https://open.bigmodel.cn/api/paas/v4
    api_key: <zhipu-api-key>

delegation:
  model: mimo-v2.5
  provider: custom
  max_iterations: 50
```
