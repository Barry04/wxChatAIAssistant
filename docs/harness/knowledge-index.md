# 知识索引

| ID | 知识 | 证据 | 状态 | 去向 |
|---|---|---|---|---|
| K01 | FastAPI 提供联系人、导入、生成、反馈、设置和静态文件路由 | `app/main.py` | [已验证] | architecture |
| K02 | 应用采用 JSON/JSONL 本地存储，并初始化演示数据 | `app/storage.py` | [已验证] | architecture、skills/architecture |
| K03 | 草稿生成组合场景、风险、关系 YAML、历史检索、画像和模型提供方 | `app/services.py`、`app/agent/` | [已验证] | skills/relationship-chat-safety |
| K04 | L0-L3 风险规则决定草稿、确认或阻止行为 | `app/services.py`、`config/safety.yaml` | [已验证] | skills/relationship-chat-safety |
| K05 | 支持 demo、Ollama 和 OpenAI 兼容模型，模型失败回退本地模板 | `app/services.py`、`app/models.py` | [已验证] | skills/relationship-chat-safety |
| K06 | 后端通过 `run.ps1` 运行，测试由 pytest 执行，前端由 Vite 构建 | `run.ps1`、`requirements.txt`、`frontend/package.json` | [已验证] | conventions |
| K07 | React 工作台已接入联系人、导入、生成、反馈、Self Skill、自动回复和运行设置 API | `frontend/src/App.jsx`、`app/main.py` | [已验证] | architecture、conventions |
| K08 | 群聊支持仅提及触发或全消息触发；原始群聊记录保留，但人数大于 10 或人数未知的群聊不进入个人 Self Skill 蒸馏 | `app/automation.py`、`app/wechat_cli_bridge.py`、`app/self_skill.py`、`tests/test_automation.py` | [已验证] | skill/wechat-local-auto-reply |
| K09 | Girls chat 风格只从近 365 天、私聊且双方 12 小时内互道晚安的候选中提取表达统计，不迁移身份、事实或历史记忆 | `app/self_skill.py`、`tests/test_api.py`、`skill/girls-chat-expression-style/SKILL.md` | [已验证] | skill/girls-chat-expression-style |

## 资格化结论

K02 归入架构与存储域；K03-K05 合并为“关系聊天安全”；K06 归入工程约定；K01 和 K07 作为架构文档事实保留，不单独生成 Skill；K08 复用现有 `wechat-local-auto-reply`；K09 复用现有项目 Skill，不新建同名目录。
