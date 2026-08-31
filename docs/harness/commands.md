# 命令

所有命令均应在项目根目录 `F:\wxChatAssistant` 执行。

## 后端运行

```powershell
.\run.ps1
```

脚本会使用 `.venv\Scripts\python.exe`，并启动：

```text
uvicorn app.main:app --host 127.0.0.1 --port 8787
```

服务地址为 `http://127.0.0.1:8787`。若虚拟环境不存在，脚本会直接报错，不会自动安装依赖。

## 日志

模型调用元数据写入 `data/model-calls.jsonl`，自动回复动作写入
`data/automation-events.jsonl`。两者均可用 PowerShell 实时查看：

```powershell
Get-Content .\data\model-calls.jsonl -Tail 20 -Wait
Get-Content .\data\automation-events.jsonl -Tail 20 -Wait
```

HTTP 查看入口：

```text
GET /api/logs/model-calls?limit=50
GET /api/automation/events?limit=50
```

自动化事件使用 `orchestration_mode=langgraph-hub` 标记 Hub 编排，并在
`hub_trace` 中记录 Task → Hub 的受控路由原因；事件仍不保存模型 API Key、提示词或
完整聊天正文之外的新增 Hub 推理内容。

模型调用日志不保存 API Key、提示词、聊天正文或模型回复。

Windows 微信 4.1 自绘界面的发送前会话验证由
`tools/read_wechat_title.ps1` 调用系统内置简体中文 OCR 完成。脚本只截取右侧顶部标题栏，临时图像识别后立即删除。

## Python 测试

若虚拟环境尚未安装依赖，先执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

再执行：

```powershell
.\.venv\Scripts\python.exe -m pytest
```

当前测试位于 `tests/test_services.py`，覆盖场景识别、风险分级、纯文本导入和演示模式生成。异步服务测试通过标准库 `asyncio.run` 执行，不依赖额外 pytest 异步插件。

## 前端开发与构建

```powershell
Set-Location frontend
npm install
npm run dev
```

```powershell
Set-Location frontend
npm run build
```

前端独立开发服务器默认由 Vite 决定端口；后端 CORS 当前允许 `127.0.0.1:5173` 与 `localhost:5173`。构建完成后，后端会托管 `frontend/dist`。

## 前端检查

```powershell
Set-Location frontend
npm run lint
```

当前 React 工作台已接入联系人、导入、草稿、反馈与设置流程；`npm run lint` 检查的是业务页面，不是 Vite 模板。
