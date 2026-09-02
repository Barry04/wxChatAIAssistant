const { chromium } = require("C:\\Users\\12897\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\node\\node_modules\\playwright\\index.js");
(async () => {
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  const page = await browser.newPage();
  await page.goto("file:///F:/wxChatAssistant/articles/wxchat-readme-article/article/article.html", { waitUntil: "networkidle" });
  const r = await page.evaluate(() => {
    const txt = document.body.innerText;
    return {
      hasRunPs1: txt.includes("run.ps1"),
      hasGetContent: txt.includes("Get-Content"),
      hasModelCalls: txt.includes("model-calls.jsonl"),
      sample: txt.split("\n").filter(l => l.includes("run.ps1") || l.includes("Get-Content") || l.includes("model-calls")).slice(0, 8),
      preCount: document.querySelectorAll("pre").length,
    };
  });
  console.log(JSON.stringify(r, null, 2));
  await browser.close();
})().catch(e => { console.error("ERR", e); process.exit(1); });
