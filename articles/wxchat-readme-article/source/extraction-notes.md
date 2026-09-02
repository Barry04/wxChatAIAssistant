# Extraction Notes

- 输入类型: Markdown (F:\wxChatAssistant\README.md)
- 提取方式: 轻量 fallback 脚本 `source-to-markdown.py`（机械抽取, 未过度改写）
- 源语言: 中文（简体）
- 目标语言: 跟随源语言（中文）—— 不翻译
- 可能丢失的信息: 无。README 本身为纯文本 Markdown，无复杂版式
- 图片: 1 张占位 `![关系助手：Agent 流转图动态演示](docs/images/agent-flow-demo.gif)`
  （本地路径，位于项目 docs/images/ 下；配图模式若为 none 则不用外部图片）
- 表格: 安全模型表（L0 / L1/L2 / L3）完整保留
- 代码块: 快速开始 / 日志排查 / 检查 三处 PowerShell 代码块完整保留
- 链接: 3 个 docs 相对链接保留（架构说明 / 常用命令 / 关系型微信助手设计）
- 元数据: 标题 `wxChatAIAssistant`；README 无作者 / 时间字段
- 需要用户补充: 无
