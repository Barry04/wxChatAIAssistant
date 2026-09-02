const { chromium } = require("C:\\Users\\12897\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\node\\node_modules\\playwright\\index.js");
(async () => {
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  const page = await browser.newPage();
  await page.goto("file:///F:/wxChatAssistant/articles/wxchat-readme-article/article/article.html", { waitUntil: "networkidle" });
  const r = await page.evaluate(() => {
    const pres = [...document.querySelectorAll("pre")];
    return pres.map((p, i) => {
      const tc = p.textContent;
      return { i, len: tc.length, head: tc.slice(0, 90), hasBackslash: tc.includes("\\"), htmlHead: p.innerHTML.slice(0, 200) };
    });
  });
  console.log(JSON.stringify(r, null, 2));
  await browser.close();
})().catch(e => { console.error("ERR", e); process.exit(1); });
