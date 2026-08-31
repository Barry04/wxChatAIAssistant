---
name: architecture
description: >-
  本项目的 FastAPI、本地 JSON/JSONL 存储与前端托管架构。Use when 修改后端路由、
  服务层、存储结构、数据流或前端 API 集成边界。
---

# 架构与本地存储

> project-to-harness-skill | 2026-08-03 | 证据：`app/main.py`、`app/services.py`、`app/storage.py`
> Qualification: 17/20 | [已验证]

## Purpose

在不破坏“本地优先、用户确认后发送”边界的前提下，维护后端 API、服务层、本地数据文件和前端托管关系。

## 触发词

`FastAPI`、`API`、`联系人`、`导入`、`JSONL`、`数据存储`、`frontend/dist`、`CORS`、`前端接入`。

## 规则

### 分层

- [已验证] `app/main.py` 只负责 HTTP 路由、请求编排和静态文件托管；业务判断放在 `app/services.py`；自动回复循环委托 `app/runtime/orchestrator.py`，发送只经 `app/operator`。
- [已验证] 自动回复由 `app/runtime/hub_graph.py` 编排 Watch/Memory/Draft Task；Hub 只能在代码白名单内路由，PolicyGate 与 Operator 保持确定性硬门禁。
- [已验证] 新增或修改请求体时，先在 `app/models.py` 定义 Pydantic 模型。
- [已验证] 文件路径、默认数据和 JSON/JSONL 读写统一放在 `app/storage.py`。联系人事实记忆使用同一 `config.sqlite3`（`app/memory.py`），按 `contact_id` 隔离，不参与发送决策。

### 本地数据

- [已验证] 结构化单对象或列表使用 JSON 并通过 `write_json` 原子替换。
- [已验证] 聊天样本和反馈使用 JSONL 并通过 `append_jsonl` 追加。
- [已验证] 新存储文件必须由 `ensure_storage` 初始化，避免首个请求出现路径或文件不存在错误。
- [已验证] 运行设置中的 API Key 不得落盘；仅允许保存提供方、地址和模型名。

### 前后端边界

- [已验证] 前端开发服务器允许的来源当前限定为 `127.0.0.1:5173` 与 `localhost:5173`。
- [已验证] 只有 `frontend/dist/assets` 存在时后端才挂载构建产物。
- [已验证] `frontend/src/App.jsx` 已接入核心 API。扩展前端时先核对 API 响应结构，并保持桌面与移动端交互验证。

## 不要假设

- 不要假设 `data/` 已存在；服务启动时才会创建。
- 不要假设新增的 `/api/*` 端点会自动出现在前端；路由变更后同步检查工作台调用。
- 不要绕过 `storage.py` 直接以不同格式读写应用数据。

## 维护

修改模块职责、存储格式或前端托管方式后，更新 `docs/harness/architecture.md` 与本文件的证据状态。日常新增经验按 `evolving-skill` 流程，经用户确认后写入项目 `skill/`。
