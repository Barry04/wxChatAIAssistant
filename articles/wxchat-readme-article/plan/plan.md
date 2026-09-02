# Plan — wxChatAIAssistant README → Beautiful Article

## Brief

- 目标读者：想了解 / 评估 / 上手 wxChatAIAssistant 的开发者与用户，带着"这是什么、安不安全、怎么跑起来"的问题来读
- 目标语言：跟随源语言（中文），不翻译
- 文章类型：longform（验证场景，默认 100% 信息保留，不丢内容）
- 信息保留比例：100%（标配 longform）
- 必须保留的信息（指向 source.md）：
  - 定位句 + 默认安全声明（"默认不发送消息…L3 直接拦截" 引言块）
  - 新版能力 6 条（关系化工作台 / 多角色草稿生成 / 待确认回复中心 / 受控自动化链路 / 本地演示与模型回退 / 更顺畅的本地体验）
  - 安全模型表格（L0 / L1/L2 / L3 三行）+ 草稿 Agent 无发送能力声明 + 合规提示
  - 快速开始：环境要求（Windows / Python 3.10+ / Node.js）+ 3 步命令 + dev 命令（两段 CodeBlock）
  - 使用流程 5 步
  - 本地数据与隐私：data/ 目录 5 个文件说明 + 仓库红线清单
  - 日志与排查：2 条 PowerShell 命令 + 2 个 API 端点 + 隐私承诺（不保存 API Key / 提示词 / 正文 / 回复；OCR 校验与临时图像删除）
  - 检查：pytest / compileall / lint / build 4 条命令
  - 项目结构目录树（8 个目录）+ 进一步阅读 3 个链接
- 可删减的信息：无（100% 保留；仅按章节重组，不删句）
- 语气：克制分析、工程文档、冷静可信（贴合工具的安全敏感属性）
- 主要观点：① 这是一款"本地优先 + 人工确认"的关系型回复助手；② 发送能力与草稿能力物理隔离，安全由流程保证；③ 全部个人数据留在本机
- 阅读目标：读完能判断它是否适合自己、理解其安全边界、并跑起本地 demo
- 版式宽度：wide（含安全模型表格 + 多处代码块，适合数据/代码密集阅读）
- TOC：开（14 章长文需要导航）
- 配图策略：none（技术 / 证据型文章，靠正文 + Raw + 表格表达；Raw 照常使用）
- 封面：开。构图想法：tufte 风格、SVG 抽象"本地边界 + 人工确认闸门"的关系流示意（D 几何拼贴 / 线框式），主视觉用 SVG 画"联系人 → 草稿 → 人工确认 → 发送"的细线流程图，只用 --ra-* token

## Outline

- Hero：标题「wxChatAIAssistant」；副标题「本地优先的关系型微信 AI 聊天助手」；meta：项目 README · 来源 F:\wxChatAssistant
- Lead：一句话框定 —— 它把"按关系写回复"这件事做成一个本地、可审计、默认不自动发送的工作台
- Summary：结论先行 TL;DR —— 草稿由多角色 Agent 生成、发送由无模型 Operator 执行、默认 dry-run + 人工逐条确认

### Sections

1. 01 这是怎样一个助手
   - 保留信息：定位句 + 默认安全声明引言块（source.md 第 1-3 段）
   - 需要的组件：Section + 一个 Callout（默认安全声明）
   - 是否需要 Raw：是 —— 小 SVG 画"本地 vs 云端"边界示意，服务"本地优先"论点
2. 02 关系化联系人工作台
   - 保留信息："新版能力"第 1 条（source.md 新版能力-关系化）
   - 需要的组件：Section 正文
   - 是否需要 Raw：否
3. 03 多角色草稿生成
   - 保留信息："新版能力"第 2 条（understand → style → writer → reviewer）
   - 需要的组件：Section + CodeBlock（角色链）
   - 是否需要 Raw：是 —— SVG 流水线图展示四个角色的审查顺序，服务"多角色审核"论点
4. 04 待确认回复中心
   - 保留信息："新版能力"第 3 条
   - 需要的组件：Section 正文
   - 是否需要 Raw：否
5. 05 受控自动化链路
   - 保留信息："新版能力"第 4 条（Watcher / Orchestrator / Operator）
   - 需要的组件：Section + CodeBlock（编排链）
   - 是否需要 Raw：是 —— SVG 链路图 watch→memory→draft→policy→operator/queue，服务"受控"论点
6. 06 本地演示与模型回退
   - 保留信息："新版能力"第 5、6 条（演示模式 / Ollama+OpenAI 回退 / 本地缓存与队列）
   - 需要的组件：Section 正文
   - 是否需要 Raw：否
7. 07 安全模型（核心）
   - 保留信息：安全模型表格 3 行 + 无发送能力声明 + 合规提示（source.md 安全模型整节）
   - 需要的组件：Section + Table（L0/L1/L2/L3）+ Quote（合规提示）
   - 是否需要 Raw：是 —— SVG 风险分级条（L0 可发 / L1-L2 待确认 / L3 拦截），服务"安全分级"论点
8. 08 快速开始
   - 保留信息：环境要求 + 3 步命令 + dev 命令（source.md 快速开始整节，含两段 CodeBlock）
   - 需要的组件：Section + 2 个 CodeBlock
   - 是否需要 Raw：否
9. 09 使用流程
   - 保留信息：5 步流程（source.md 使用流程整节）
   - 需要的组件：Section 正文（步骤列表）
   - 是否需要 Raw：否
10. 10 本地数据与隐私
    - 保留信息：data/ 目录 5 项 + 仓库红线清单（source.md 本地数据与隐私整节）
    - 需要的组件：Section + 文件清单
    - 是否需要 Raw：否
11. 11 日志与排查
    - 保留信息：2 条命令 + 2 个 API 端点 + 隐私承诺 + OCR 校验说明（source.md 日志与排查整节）
    - 需要的组件：Section + CodeBlock + 端点列表
    - 是否需要 Raw：否
12. 12 检查
    - 保留信息：pytest / compileall / lint / build（source.md 检查整节）
    - 需要的组件：Section + CodeBlock
    - 是否需要 Raw：否
13. 13 项目结构
    - 保留信息：8 目录目录树（source.md 项目结构整节）
    - 需要的组件：Section + 目录列表
    - 是否需要 Raw：否
14. 14 进一步阅读
    - 保留信息：3 个链接（source.md 进一步阅读整节）
    - 需要的组件：Section + 链接列表
    - 是否需要 Raw：否

- 结尾方式：Conclusion —— 收束"本地优先 + 人工确认"的安全立场，指向快速开始 / 架构文档

## Theme

- 选定主题：tufte
- 理由：README 是技术 / 证据型项目文档，含安全模型表格、风险分级、命令代码块；tufte 的 bestFor 命中 longform / explainer / review / tutorial，克制、数据优先、低装饰的气质与"安全敏感工具"的冷静语气最贴合
- 与源材料的冲突：无（gif 动态演示图不用外部图片，改由 Raw SVG 承担图解职能，符合 tufte 媒体风格）
- 当前信息密度下的表现建议：100% longform 克制长文为主，正文为主体，Raw 只在 01/03/05/07 四处点亮关键概念，数据表格与代码块按 tufte 精密标本风格呈现

## Assets

- 策略：none
- 一句话说明：不使用外部图片（含 README 内 gif 动态图），靠正文 + Raw（SVG 图解 / 表格 / 代码块）表达；Raw 自由层照常使用，不受配图策略影响
