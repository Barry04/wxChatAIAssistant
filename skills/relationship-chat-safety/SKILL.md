---
name: relationship-chat-safety
description: >-
  本地关系聊天草稿的风险分级、关系策略、LangGraph 多角色生成、模型调用和隐私边界。Use when 修改回复生成、
  风险关键词、关系 YAML、Ollama、OpenAI-compatible、app/agent 或数据隐私规则。
---

# 关系聊天安全

> project-to-harness-skill | 2026-08-03 | 证据：`app/services.py`、`app/agent/`、`config/safety.yaml`、`skills/relationships/*.yaml`
> Qualification: 19/20 | [已验证]

## Purpose

确保手工草稿与自动回复都遵守白名单、dry-run 和 L0-L3 风险边界。

## 触发词

`generate_reply`、`app/agent`、`LangGraph`、`风险分级`、`L3`、`草稿`、`关系 Skill`、`Ollama`、`OpenAI-compatible`、`隐私`、`模型回退`。

## 规则

### 多角色生成

- [已验证] `generate_reply()` 委托 `app/agent/graph.py` 的 LangGraph 图：`understand → style → writer → reviewer`。
- [已验证] L3 在 understand 后短路，不进入 writer。
- [已验证] reviewer 可 `accept` / `revise`（最多 1 次）/ `block`；角色与工具不得发送微信。发送只经 `app/operator`，且必须已有用户或策略批准的原文。
- [已验证] API 兼容原字段，并返回 `agent_mode`、`trace`、`review`、`style_brief`。

### 风险分级

- [已验证] 先执行场景识别与风险分级，再生成候选。
- [已验证] L0 允许普通草稿；只有白名单、启用、关闭 dry-run、已确认真实发送，且 PolicyGate 判定 `auto_send` 时才交给 Operator。
- [已验证] L1 和 L2 只能进入待确认状态，不得自动发送。
- [已验证] L3 不得生成可直接发送的候选，必须返回空候选和风险警告；Policy 输出 `blocked`，不得把可发送候选交给 Operator。
- [已验证] 自动回复 Hub 只能调度 Watch/Memory/Draft，不能选择联系人、调用发送工具或绕过 PolicyGate；实际自动发送仅允许 L0。
- [已验证] 高风险覆盖金钱、凭据、医疗、法律与合同相关内容；修改规则时同步检查优先级与测试。

### 关系策略

- [已验证] 关系类型限定为 `partner`、`friend`、`family`，并通过 `skills/relationships/<relationship>.yaml` 加载。
- [已验证] 关系 YAML 提供沟通原则和模式，但不能绕过风险分级。
- [已验证] 不得编造位置、行程、健康、金钱决定或重大关系承诺。
- [已验证] 用户档案中没有确认的昵称、事实或边界，不应由生成逻辑自行补全。

### 模型与回退

- [已验证] `demo` 模式不调用外部模型。
- [已验证] Ollama 使用 `/api/chat`；OpenAI 兼容模式使用 `/chat/completions`（见 `app/agent/llm.py`）。
- [已验证] 模型输出需解析为恰好三个候选；异常、无效 JSON 或候选不足时回退本地模板并返回警告。
- [已验证] 模型提示词必须继续约束“仅生成私人聊天草稿”和“不编造事实或承诺”。

### 隐私

- [已验证] 本地微信数据库通过 `wechat-cli` 读取，不使用 OCR。
- [已验证] 导入和反馈数据仅保存到本地 `data/`。
- [已验证] API Key 仅保存在本地 SQLite 配置中，应用重启后需要重新配置。
- [已验证] 自动回复默认关闭、默认 dry-run、默认空白名单、默认仅允许 L0。
- [已验证] 未经用户明确批准具体联系人和测试文本，不执行真实发送测试。

## 不要假设

- 不要把 `config/safety.yaml` 当作运行时关键词唯一来源；当前关键词实际定义在 `app/services.py`。
- 不要把演示模板的语气当作真实用户画像；历史反馈和联系人边界优先。
- 不要因为模型调用可用而跳过本地规则或用户最终确认。
- 不要在 agent 节点中直接调用微信发送。
- 不要给 LLM 配备 `send_message` 工具，也不要引入 LLM Supervisor 自行选会话发送。

## 维护

调整风险、关系模板、模型协议、角色图或隐私边界时，同步更新 `docs/harness/architecture.md`、`docs/superpowers/specs/2026-08-09-langgraph-multi-agent-design.md` 和相关测试。日常新增经验按 `evolving-skill` 流程，经用户确认后写入项目 `skill/`。
