# LangChain、LangGraph 与 LangSmith 流式生成改造方案

## 1. 决策摘要

在现有 LangGraph 四角色草稿生成流程基础上，引入 LangChain 作为统一模型调用、消息模板和结构化输出层；保留 LangGraph 作为唯一编排层。将 `POST /api/generate` 改为 SSE 实时流接口，使前端能够逐步展示生成过程。

LangSmith 只作为可选调试追踪能力，默认关闭。关闭时不初始化 LangSmith、不上传任何追踪数据；项目既有本地 `trace` 继续保留。

## 2. 保持不变的边界

- 图结构继续为 `understand -> style -> writer -> reviewer`。
- L3 风险在 `understand` 后短路，不进入 `writer`，最终不返回可发送候选。
- `reviewer` 只能 `accept`、`revise` 或 `block`；`revise` 最多回到 `writer` 一次。
- 自动回复继续调用内部 `generate_reply()`，不得经由 HTTP/SSE，也不得因本次改造改变白名单、dry-run、人工确认或 L0-L3 约束。
- 不引入开放式 Tool Calling、RAG、向量库、远程记忆或允许 Agent 直接发送微信的能力。
- `demo` 模式保持纯本地模板生成，不访问外部模型或追踪服务。

## 3. LangChain 模型层

- 新增模型工厂，根据既有 `RuntimeSettings.provider` 和请求级凭据依赖创建运行时模型。传入 LangGraph state 的设置只能包含 `provider`、`base_url`、`model` 等非敏感字段；模型提供方 API Key 只在实际模型调用前从请求级依赖解析，不得进入可序列化 state。
- `ollama` 使用 `langchain-ollama` 的 `ChatOllama`；`openai-compatible` 使用 `langchain-openai` 的 `ChatOpenAI`，继续使用现有 `base_url`、`model` 与本地 SQLite 中的 API Key。API Key 通过不写入 state、trace 或事件流的请求级依赖交给模型工厂。
- `writer` 使用 LangChain 消息模板构建提示词，并用 Pydantic 模型校验三条候选草稿的结构化输出。
- 模型调用失败、输出无法解析或有效候选不足三条时，返回本地模板候选并带 warning；任何回退都不能绕过候选清洗和审核。

## 4. LangGraph 与 SSE 接口

- `POST /api/generate` 改为 `text/event-stream`；请求体仍为 `contact_id`、`conversation`、`style_preset_id`。
- 新增服务层异步迭代器（例如 `stream_generate_reply()`）：它以与 `generate_reply()` 相同的非敏感业务字段构造经过清洗的初始 state，模型 API Key、LangSmith 凭据和 tracing context 均不得进入 state；随后执行 LangGraph 的 `astream`，同时订阅 `updates` 与 `values`。由于 `values` 会产生完整 state 快照，state 的构造和每个节点更新都必须保持无凭据。每个角色完成后，从该角色新增的本地 trace 产出一个内部 `step` 事件；最后一个完整 state 经与现有返回结构共用的纯转换函数生成内部 `result` 事件。不得在 SSE 路由中先调用 `generate_reply()` 或在流结束后再次执行图。
- `generate_reply()` 改为消费上述内部事件流并仅返回最终 `result`，以保持自动回复等非 HTTP 调用方的现有完整结果契约。自动回复不得订阅、转发或依赖 SSE 事件。
- `app/main.py` 只负责把内部 `meta`、`step`、`result`、`error` 事件编码为 SSE；请求断开时检测 `Request.is_disconnected()`，关闭内部异步迭代器并取消未完成的图任务。若没有收到 `result`，路由不得合成候选或发送 `result` 事件。
- 事件协议：
  - `meta`：本次生成的非敏感摘要与流程元信息。
  - `step`：单个角色完成后输出的本地 trace 事件，包含角色、状态、耗时与摘要。
  - `result`：最终完整生成结果，包含候选、风险、审核、风格摘要和 trace。
  - `error`：安全化错误信息；不得返回 API Key 或原始敏感配置。
- 前端使用 `fetch` 与 `ReadableStream` 解析 SSE；接收 `step` 时更新流程面板，接收 `result` 后才显示候选编辑、选择与反馈入口。
- 前端需处理连接中断、服务端错误、未收到最终结果和用户取消，不得将不完整候选呈现为可发送内容。

## 5. LangSmith 调试追踪

- 在运行设置中新增 `langsmith_tracing_enabled: bool = false`，继续保存到既有本地 SQLite；该字段只是用户授权开关，不包含任何 LangSmith 凭据。
- 设置页增加“启用 LangSmith 调试追踪”开关；开启前展示隐私说明：启用后，模型调用调试数据可能上传至 LangSmith。
- LangSmith 专用凭据只从启动进程环境读取：`LANGSMITH_API_KEY` 为必填，`LANGSMITH_ENDPOINT` 与 `LANGSMITH_PROJECT` 可选（缺省时使用 LangSmith SDK 默认 endpoint 和项目名）。模型提供方 API Key 绝不复用为 LangSmith API Key，也不通过设置 API 或前端提交。
- 仅当开关开启且 `LANGSMITH_API_KEY` 非空时，API 路由为该次**手工**生成创建短生命周期 `tracing_context(enabled=True)`，并以 LangChain/LangGraph 的请求级 `RunnableConfig` 传入模型和图调用；不得修改进程级环境变量或复用上一请求的 context。开关关闭、凭据缺失或初始化失败时，手工生成必须显式运行在 `tracing_context(enabled=False)` 中，不能只依赖“不创建 context”，从而覆盖启动环境中可能存在的 `LANGSMITH_TRACING=true`。
- tracing context、LangSmith API Key、endpoint、项目名和模型 API Key 不得写入 SQLite、LangGraph state、本地 trace、SSE `meta`/`step`/`result`/`error` 或任何 API 响应。设置页仅展示“已配置/未配置”的非敏感就绪状态。
- 自动回复调用 `generate_reply()` 时必须显式包裹 `tracing_context(enabled=False)`，不能仅靠不传 tracing context；即使用户已开启调试开关，或启动环境设置了 `LANGSMITH_TRACING=true`，自动回复、dry-run 和真实发送链路都不得启用 LangSmith。
- 未配置、配置不完整或初始化失败时，生成流程继续运行，并以本地 warning 提示追踪不可用。LangSmith 不替代本地 trace，也不用于默认生产运行或数据持久化。

## 6. 验证标准

- 覆盖 demo、Ollama、OpenAI-compatible 三种模型分支；demo 不发起网络请求。
- 覆盖结构化输出成功、无效输出、候选不足和模型异常时的安全回退。
- 覆盖四角色正常顺序、L3 短路、一次重写回环及既有风险边界。
- 覆盖 SSE 正常事件顺序、L3 结果、模型失败和客户端中断。
- 覆盖 LangSmith 默认关闭、开关与环境变量配置齐备时仅手工请求启用、关闭后新请求不追踪，以及自动回复始终不追踪的行为。专门在 `LANGSMITH_TRACING=true` 的启动环境下验证：开关关闭的手工请求和全部自动回复链路都由 `tracing_context(enabled=False)` 阻断；捕获实际 LangSmith run 的 inputs、outputs、metadata 和 events，断言模型 API Key、LangSmith 凭据及其他敏感配置不出现在 SQLite、state、trace、SSE、API 响应或远端追踪载荷中。
- 执行 Python 测试、前端 lint 与生产构建。

## 7. 兼容性说明

`POST /api/generate` 从同步 JSON 改为 SSE，前端和其他 HTTP 调用方必须统一迁移。内部 `generate_reply()` 保持返回完整结果，以维持自动回复调用链的安全性和稳定性。
