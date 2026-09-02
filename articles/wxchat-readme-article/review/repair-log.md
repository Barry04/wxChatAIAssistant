# 修复日志（Phase 7）— PowerShell 反斜杠丢失

## 问题

TSX 模板字符串中书写 `\.venv\Scripts` 等含反斜杠的命令时，JS 把 `\S`、`\r`、`\v`
等当作转义序列吞掉，渲染后命令被破坏：

- `.\.venv\Scripts\python.exe` → `.venvScriptspython.exe`
- `.\run.ps1` → `run.ps1`（`\r` 被当作回车）
- `Get-Content .\data\model-calls.jsonl` → `Get-Content .data...`

## 修复

在 code 模板字符串中把每个反斜杠写成双份 `\\`（JS 模板字符串中 `\\` 输出一个真实反斜杠）。

涉及文件（3 个）：

| 文件 | 修复内容 |
|---|---|
| `article/sections/08-quick-start.tsx` | venv 命令 `.\.venv\Scripts\python.exe`、启动命令 `.\run.ps1` |
| `article/sections/11-troubleshooting.tsx` | 2 条 `Get-Content .\data\...` 命令 |
| `article/sections/12-checks.tsx` | 2 条 `.\.venv\Scripts\python.exe` 命令 |

## 验证

- 重新 `npm run html` 构建成功
- Playwright + Chrome 实测 9 个 `<pre>`：`.\run.ps1`、`Get-Content .\data\model-calls.jsonl`、
  `.\.venv\Scripts\python.exe -m pytest -q` 等全部以正确反斜杠渲染
- 未涉及文件无需改动（`\n` 换行、`→` 链、目录树均无反斜杠）
