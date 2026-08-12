# Skill 登记

生成日期：2026-08-03；最近复核：2026-08-11

| Skill Name | Domain | Evidence | Source Files | Qualification Score | Score Breakdown | Merge From | Status | Verification State |
|---|---|---|---|---:|---|---|---|---|
| architecture | 架构与本地存储 | 路由、服务和存储模块相互引用；README 说明本地运行 | `app/main.py`、`app/services.py`、`app/storage.py`、`README.md` | 17 | R4 / E4 / X4 / S5 / B0 | 本地存储、API 托管 | generated | [已验证] |
| relationship-chat-safety | 关系聊天安全与模型生成 | 风险规则、关系 YAML、生成提示词、模型回退和隐私说明相互印证 | `app/services.py`、`app/agent/`、`app/models.py`、`config/safety.yaml`、`skills/relationships/*.yaml`、`README.md` | 19 | R5 / E5 / X4 / S5 / B0 | 风险分级、关系策略、模型接入、隐私边界、多角色审核 | generated | [已验证] |
| wechat-local-auto-reply | Windows 微信本地读取与安全自动回复 | 微信数据库读取、结构化问答、Persona 蒸馏、群聊规则、游标监听和安全动作均有实现与测试 | `app/wechat_cli_bridge.py`、`app/chat_analysis.py`、`app/self_skill.py`、`app/automation.py`、`tests/test_wechat_cli_bridge.py`、`tests/test_automation.py` | 20 | R5 / E5 / X5 / S5 / B0 | 微信读取、Self Skill 蒸馏、群聊触发、自动回复安全流程 | generated | [已验证] |
| girls-chat-expression-style | 受边界约束的表达风格蒸馏 | 近 365 天私聊候选、12 小时互道晚安筛选、风格统计和身份隔离均有实现与测试 | `app/self_skill.py`、`tests/test_api.py`、`skill/girls-chat-expression-style/SKILL.md` | 13 | R4 / E4 / X3 / S5 / B-3 | 表达类型提取、风格预设、隐私边界 | existing-project-skill | [已验证] |
| python-test-conventions | 测试约定 | 服务层测试覆盖基础路径，但异步执行配置未在依赖中显式声明 | `tests/test_services.py`、`requirements.txt` | 11 | R3 / E3 / X2 / S3 / B0 | - | convention-only | [已验证] |
| local-run-frontend | 本地运行与前端构建 | 启动脚本、CORS 配置、Vite 脚本和前端 API 接入相互印证 | `run.ps1`、`app/main.py`、`frontend/package.json`、`frontend/src/App.jsx` | 11 | R3 / E3 / X2 / S3 / B0 | - | convention-only | [已验证] |
| contact-crud-routes | 单一业务路由 | 路由实现仅限联系人 CRUD | `app/main.py` | 1 | R1 / E1 / X0 / S4 / B-5 | - | discarded | [已验证] |
| relationship-yaml-copy | 单一配置文案 | 配置内容可直接读取，缺少跨模块工程规则 | `skills/relationships/*.yaml` | 3 | R1 / E1 / X1 / S5 / B-5 | - | discarded | [已验证] |
| vite-template-ui | 模板页面细节 | 前端已是业务工作台，不应将组件细节单独升格为 Skill | `frontend/src/App.jsx` | 0 | R1 / E1 / X0 / S3 / B-5 | - | discarded | [已验证] |

`skills/relationships/*.yaml` 是应用运行时配置；`skills/*/SKILL.md` 是 Harness 生成的 Agent 可复用知识；`skill/*/SKILL.md` 是由 evolving-skill 维护的项目专用 Skill。三者按文件名和目录用途区分，避免重复生成同名 Skill。
