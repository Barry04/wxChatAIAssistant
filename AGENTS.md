# wxChatAssistant

本地优先的关系型微信聊天回复草稿助手。回答必须使用中文。
Harness 已于 2026-08-11 按当前代码状态复核；优先相信 `docs/harness/` 中标注为 `[已验证]` 的事实。

## 阅读顺序

1. `docs/harness/architecture.md`
2. `docs/harness/commands.md`
3. 按任务查阅下方 Skills 索引

## Docs

| 文档 | 路径 |
|---|---|
| 架构 | `docs/harness/architecture.md` |
| 命令 | `docs/harness/commands.md` |
| 约定 | `docs/harness/conventions.md` |
| 知识索引 | `docs/harness/knowledge-index.md` |
| Skill 登记 | `docs/harness/skill-registry.md` |

## Skills

| Skill | 路径 | 何时用 |
|---|---|---|
| architecture | `skills/architecture/SKILL.md` | 调整后端、存储、API 或前端集成边界 |
| relationship-chat-safety | `skills/relationship-chat-safety/SKILL.md` | 修改草稿生成、风险分级、模型接入、LangGraph 多角色或隐私策略 |
| langgraph-multi-agent | `docs/superpowers/specs/2026-08-09-langgraph-multi-agent-design.md` | 修改 `app/agent/` 角色图、trace、审核重写边 |
| wechat-local-auto-reply | `skill/wechat-local-auto-reply/SKILL.md` | 修改微信本地读取、蒸馏、群聊触发、监听、dry-run、游标或自动发送链路 |
| girls-chat-expression-style | `skill/girls-chat-expression-style/SKILL.md` | 应用基于聊天记录蒸馏出的表达类型风格到新用户或新对话 |

## Agent 入口

详细规则见 `docs/harness/` 与上述 Skills；现有 `skills/relationships/*.yaml` 是运行时关系配置，不是 Agent Skill。`skills/*/SKILL.md` 是 Harness 生成知识，`skill/*/SKILL.md` 是项目专用 Skill。

## 收尾

任务收尾时阅读全局 `evolving-skill`；若有可复用经验，先征得用户同意，再写入本项目 `skill/`。
