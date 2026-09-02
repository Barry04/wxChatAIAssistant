# wxChatAIAssistant

本地优先的关系型微信 AI 聊天助手。它帮助你按联系人关系、表达习惯和对话上下文生成回复草稿；微信读取、画像、设置和运行记录默认都留在自己的电脑上。

> 默认不发送消息。自动回复默认关闭、默认 dry-run；L1/L2 必须人工确认，L3 直接拦截。

![关系助手：Agent 流转图动态演示](docs/images/agent-flow-demo.gif)

## 📖 精美长文版（beautiful-article 重制）

本 README 已由 [beautiful-article](https://github.com/ConardLi/garden-skills/tree/main/skills/beautiful-article) 重制为**单文件 HTML 长文**：tufte 版式、封面 + 目录、共 14 章，可离线阅读。

- **在线阅读（渲染版）**：[打开精美长文](https://htmlpreview.github.io/?https://raw.githubusercontent.com/Barry04/wxChatAIAssistant/master/articles/wxchat-readme-article/article/article.html)
- **仓库内文件**：[`article.html`](articles/wxchat-readme-article/article/article.html)（下载后用浏览器打开）

<p align="center">
  <img src="articles/wxchat-readme-article/review/shot-01-hero.png" alt="精美长文首屏预览" width="720"/>
  <img src="articles/wxchat-readme-article/review/shot-08-quickstart.png" alt="快速开始章节预览" width="720"/>
</p>

## 新版能力

- **关系化联系人工作台**：为情侣、朋友、家人维护不同的称呼、边界、回复长度、表情和幽默偏好；可在左侧直接编辑关系类型或删除自己添加的联系人。
- **多角色草稿生成**：`understand → style → writer → reviewer` 依次识别场景与风险、组合关系和个人风格、生成候选，并进行安全与质量审核。
- **待确认回复中心**：默认按当前会话过滤，可切换查看全部会话；逐条查看上下文、修改候选，确认后才把批准文本交给发送执行器。
- **受控自动化链路**：Watcher 读取白名单消息，Orchestrator 按 `watch → memory → draft → policy → operator/queue` 编排；Operator 只接收已批准的原文，负责会话校验、发送与结果验证。
- **本地演示与模型回退**：演示模式可离线体验；也支持 Ollama 和 OpenAI 兼容接口，外部调用失败时回退到本地模板。
- **更顺畅的本地体验**：公开启动资料会短时缓存在浏览器本地；待确认队列仍持续读取本地状态，避免用过期信息确认发送。

## 安全模型

| 风险级别 | 行为 |
| --- | --- |
| L0 | 可生成普通草稿；只有白名单、明确开启、关闭 dry-run 且通过策略门时才可能自动发送。 |
| L1 / L2 | 进入待确认队列，必须由用户逐条确认或放弃。 |
| L3 | 拦截，不生成可直接发送的候选。 |

草稿 Agent 不具备微信发送能力；真实发送只由无模型的 Operator 执行，且必须已有批准的原文。请勿将本工具用于未经对方同意的自动化沟通。

## 快速开始

需要 Windows、Python 3.10+ 和 Node.js。微信本地读取与受控发送面向 Windows 微信环境。

1. 创建虚拟环境并安装后端依赖：

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

2. 构建前端并启动服务：

   ```powershell
   Set-Location frontend
   npm install
   npm run build
   Set-Location ..
   .\run.ps1
   ```

3. 打开 [http://127.0.0.1:8787](http://127.0.0.1:8787)。

开发前端时可改用：

```powershell
Set-Location frontend
npm run dev
```

## 使用流程

1. 新建联系人，选择 `partner`、`friend` 或 `family`，补充称呼和表达偏好。
2. 导入自己的聊天记录，或在演示模式下粘贴一段虚构对话。
3. 在“手动生成”中产出候选，选择或编辑最终草稿。
4. 如需监听微信消息，先只启用 dry-run，并从“待确认”工作台逐条审核。
5. 只有在你明确接受风险并完成相关配置后，才考虑启用真实发送。

## 本地数据与隐私

个人数据默认位于项目的 `data/` 目录：

- `data/config.sqlite3`：联系人、模型和自动回复设置。
- `data/messages.jsonl`、`data/feedback.jsonl`：导入记录与草稿反馈。
- `data/self-skill/`：全局、关系和联系人级表达画像。
- `data/automation-state.json`、`data/automation-events.jsonl`：自动化状态与动作记录。

公开仓库不应包含 `data/`、`private/`、`.runtime/`、日志、环境变量或私钥。提交前请再次检查暂存区是否含个人数据。

## 日志与排查

```powershell
Get-Content .\data\model-calls.jsonl -Tail 20 -Wait
Get-Content .\data\automation-events.jsonl -Tail 20 -Wait
```

服务运行后，也可查看：

```text
GET http://127.0.0.1:8787/api/logs/model-calls?limit=50
GET http://127.0.0.1:8787/api/automation/events?limit=50
```

模型调用日志不会保存 API Key、提示词、聊天正文或模型回复。Windows 微信 4.1 的真实发送会使用系统 OCR 校验右侧顶部会话标题；目标不一致时会中止，临时图像会在识别后删除。

## 检查

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q app
Set-Location frontend
npm run lint
npm run build
```

## 项目结构

```text
app/agent/              LangGraph 草稿生成图
app/runtime/            Watcher、PolicyGate 与自动化编排
app/operator/           受控微信发送与发送后验证
frontend/               React + Vite 工作台
skills/relationships/   关系类型沟通配置
data/                   本地个人数据（不会上传）
tests/                  自动化测试
docs/                   架构、命令和设计文档
```

## 进一步阅读

- [架构说明](docs/harness/architecture.md)
- [常用命令](docs/harness/commands.md)
- [关系型微信助手设计](docs/relationship-wechat-assistant-design.md)
