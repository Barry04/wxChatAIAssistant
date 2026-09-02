const { chromium } = require("C:\\Users\\12897\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\node\\node_modules\\playwright\\index.js");

(async () => {
  const url = "file:///F:/wxChatAssistant/articles/wxchat-readme-article/article/article.html";
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 2400 } });
  const errors = [];
  page.on("console", m => { if (m.type() === "error") errors.push(m.text()); });
  page.on("pageerror", e => errors.push("PAGEERROR: " + e.message));
  await page.goto(url, { waitUntil: "networkidle" });
  await page.waitForTimeout(600);

  const result = await page.evaluate(() => {
    const txt = document.body.innerText;
    const html = document.body.innerHTML;
    // TOC 条目：找目录里出现的章节标题
    const tocItems = [...document.querySelectorAll("nav a, .ra-toc a, a[href^='#']")]
      .map(a => a.innerText.trim())
      .filter(t => /^0\d|^1[0-4]/.test(t));
    // 章节标题（Section h2）
    const headings = [...document.querySelectorAll("h2")].map(h => h.innerText.trim()).filter(t => /^0\d|^1[0-4]/.test(t));
    // 关键信息保留检查
    const mustHave = [
      "本地优先的关系型微信 AI 聊天助手",
      "默认不发送消息",
      "自动回复默认关闭、默认 dry-run",
      "L1/L2 必须人工确认，L3 直接拦截",
      "understand", "style", "writer", "reviewer",
      "待确认回复中心",
      "Watcher", "Orchestrator", "Operator",
      "watch", "memory", "draft", "policy", "operator/queue",
      "演示模式可离线体验",
      "Ollama", "OpenAI 兼容", "回退到本地模板",
      "短时缓存在浏览器本地",
      "持续读取本地状态",
      "L0", "L1 / L2", "L3",
      "不具备微信发送能力", "无模型的 Operator",
      "未经对方同意的自动化沟通",
      "Windows、Python 3.10+ 和 Node.js",
      "python -m venv .venv",
      "npm run build",
      ".\\run.ps1",
      "http://127.0.0.1:8787",
      "npm run dev",
      "partner", "friend", "family",
      "data/config.sqlite3",
      "data/messages.jsonl", "data/feedback.jsonl",
      "data/self-skill/",
      "data/automation-state.json", "data/automation-events.jsonl",
      "private/", ".runtime/", "暂存区",
      "Get-Content .\\data\\model-calls.jsonl",
      "/api/logs/model-calls?limit=50",
      "/api/automation/events?limit=50",
      "API Key", "提示词", "聊天正文", "模型回复",
      "OCR", "会话标题", "临时图像",
      "pytest", "compileall", "lint", "build",
      "app/agent/", "app/runtime/", "app/operator/", "frontend/",
      "skills/relationships/", "data/", "tests/", "docs/",
      "架构说明", "常用命令", "关系型微信助手设计",
    ];
    const missing = mustHave.filter(k => !txt.includes(k));
    return {
      textLen: txt.length,
      hasMissing: html.includes("未指定"),
      tocItems,
      headings,
      missing,
      bodyScrollW: document.body.scrollWidth,
      bodyClientW: document.body.clientWidth,
    };
  });

  console.log(JSON.stringify({ errors, ...result }, null, 2));
  await browser.close();
})().catch(e => { console.error("ERR", e); process.exit(1); });
