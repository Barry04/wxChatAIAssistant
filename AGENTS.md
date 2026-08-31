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
| wechat-local-auto-reply | `skill/wechat-local-auto-reply/SKILL.md` | 修改微信本地读取、蒸馏、群聊触发、监听、dry-run、游标、自动发送链路或 LangSmith 追踪隔离 |
| girls-chat-expression-style | `skill/girls-chat-expression-style/SKILL.md` | 应用基于聊天记录蒸馏出的表达类型风格到新用户或新对话 |

## Cursor UI Skills（`.cursor/skills/`）

前端设计与 UI 审计类 Skill，安装于本项目，供 Cursor Agent 自动发现。

| Skill | 路径 | 何时用 |
|---|---|---|
| ui-ux-pro-max | `.cursor/skills/ui-ux-pro-max/SKILL.md` | 设计系统、配色、字体、UX 模式、Dashboard / Landing Page 等 UI/UX 决策 |
| frontend-design | `.cursor/skills/frontend-design/SKILL.md` | 从 0 设计或重塑页面视觉：美学方向、排版、避免模板化默认样式 |
| web-design-guidelines | `.cursor/skills/web-design-guidelines/SKILL.md` | 审查已有 UI 是否符合 Web Interface Guidelines（可访问性、交互、排版） |
| shadcn | `.cursor/skills/shadcn/SKILL.md` | 使用 shadcn/ui 组件库时（需 `components.json`）；当前前端未接入，迁移 Tailwind + shadcn 后启用 |

推荐组合：`ui-ux-pro-max` → `frontend-design` → `shadcn`（设计决策 → 视觉落地 → 组件实现）。

## Agent 入口

详细规则见 `docs/harness/` 与上述 Skills；现有 `skills/relationships/*.yaml` 是运行时关系配置，不是 Agent Skill。`skills/*/SKILL.md` 是 Harness 生成知识，`skill/*/SKILL.md` 是项目专用 Skill。

## 收尾

任务收尾时阅读全局 `evolving-skill`；若有可复用经验，先征得用户同意，再写入本项目 `skill/`。
