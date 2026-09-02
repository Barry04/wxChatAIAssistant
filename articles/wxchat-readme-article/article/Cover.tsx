// Cover.tsx —— 文章封面（独立于 Article，位于 TOC + 正文 + colophon 之上）
//
// 定制封面（tufte 主题）：视觉主体 = "本地 → 多角色草稿 → 人工确认闸门 → 发送" 的
// 细线流程示意 + 数据点网格；文字层 = 项目名 + 英文 tagline + 底部安全声明。
// 呼应正文主旨：本地优先、关系化回复、默认人工确认后才发送。
// 外壳（3:4 比例 / 定位 / PDF 分页）保持不变；只用 --ra-* token。

export function Cover() {
  return (
    <section
      className="ra-cover"
      aria-label="文章封面"
      data-ra-cover=""
      style={{
        position: "relative",
        width: "100%",
        maxWidth: "min(100%, 48rem, calc((100vh - 8rem) * 3 / 4))",
        margin: "0 auto var(--ra-space-7, 3rem) auto",
        aspectRatio: "3 / 4",
        overflow: "hidden",
        background: "transparent",
        color: "var(--ra-color-fg, inherit)",
        borderRadius: "var(--ra-radius-md, 0)",
        border: "1px solid var(--ra-color-border, currentColor)",
        isolation: "isolate",
      }}
    >
      {/* 背景层：细网格 + 散点数据（tufte 数据墨水气质） */}
      <svg
        viewBox="0 0 1200 1600"
        preserveAspectRatio="xMidYMid slice"
        aria-hidden="true"
        style={{
          position: "absolute",
          inset: 0,
          width: "100%",
          height: "100%",
          color: "var(--ra-color-border, currentColor)",
          opacity: 0.5,
          zIndex: 0,
        }}
      >
        <defs>
          <pattern id="ra-cov-grid" width="80" height="80" patternUnits="userSpaceOnUse">
            <path d="M 80 0 L 0 0 0 80" fill="none" stroke="currentColor" strokeWidth="0.6" />
          </pattern>
        </defs>
        <rect width="1200" height="1600" fill="url(#ra-cov-grid)" />
        {/* 散点数据：暗示"一条条对话消息" */}
        <g fill="var(--ra-color-accent, currentColor)" opacity="0.5">
          <circle cx="140" cy="240" r="4" />
          <circle cx="260" cy="180" r="3" />
          <circle cx="380" cy="300" r="5" />
          <circle cx="520" cy="210" r="3" />
          <circle cx="660" cy="270" r="4" />
          <circle cx="820" cy="190" r="3" />
          <circle cx="960" cy="330" r="5" />
          <circle cx="1090" cy="250" r="4" />
        </g>
        {/* 左上角小 sparkline：回复节奏 */}
        <g fill="none" stroke="var(--ra-color-accent, currentColor)" strokeWidth="2" opacity="0.7">
          <polyline points="60,420 120,400 180,410 240,380 300,392 360,360 420,372" />
        </g>
      </svg>

      {/* 内容层：flex 纵向自适应，不写死像素位置 */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          zIndex: 1,
          display: "flex",
          flexDirection: "column",
          padding: "7% 9%",
          gap: "0",
        }}
      >
        {/* 上部：文字钩子 */}
        <div style={{ marginTop: "2%" }}>
          <span
            style={{
              fontSize: "var(--ra-text-xs, 0.72rem)",
              letterSpacing: "0.26em",
              textTransform: "uppercase",
              color: "var(--ra-color-muted, inherit)",
            }}
          >
            Project Readme · Longform
          </span>
          <h1
            style={{
              margin: "1.4rem 0 0 0",
              fontSize: "clamp(1.9rem, 6vw, 3.4rem)",
              lineHeight: 1.04,
              fontWeight: "var(--ra-font-weight-bold, 700)",
              color: "var(--ra-color-fg, inherit)",
            }}
          >
            wxChatAIAssistant
          </h1>
          <p
            style={{
              margin: "1.1rem 0 0 0",
              fontSize: "var(--ra-text-sm, 0.92rem)",
              letterSpacing: "0.14em",
              textTransform: "uppercase",
              color: "var(--ra-color-muted, inherit)",
              lineHeight: 1.6,
            }}
          >
            Local-First · Relationship · Human-in-the-Loop
          </p>
        </div>

        {/* 下部：流程示意（视觉主体） */}
        <div
          style={{
            flex: 1,
            display: "flex",
            alignItems: "flex-end",
            minHeight: 0,
          }}
        >
          <svg viewBox="0 0 800 330" width="100%" role="img" aria-label="本地草稿经人工确认闸门后发送的流程">
            <g stroke="var(--ra-color-fg, currentColor)" strokeWidth="1.5">
              {/* 本地数据 */}
              <rect x="24" y="110" width="150" height="76" fill="none" />
              <text x="99" y="142" textAnchor="middle" fontSize="24" fill="var(--ra-color-fg, currentColor)">本地</text>
              <text x="99" y="168" textAnchor="middle" fontSize="15" fill="var(--ra-color-muted, currentColor)">联系人 · 画像</text>
              {/* 草稿 */}
              <rect x="218" y="110" width="150" height="76" fill="none" />
              <text x="293" y="142" textAnchor="middle" fontSize="24" fill="var(--ra-color-fg, currentColor)">草稿</text>
              <text x="293" y="168" textAnchor="middle" fontSize="15" fill="var(--ra-color-muted, currentColor)">多角色 Agent</text>
              {/* 人工确认闸门（accent 强调 + 虚线） */}
              <rect x="412" y="110" width="150" height="76" fill="var(--ra-color-accent, currentColor)" opacity="0.1" />
              <rect x="412" y="110" width="150" height="76" fill="none" stroke="var(--ra-color-accent, currentColor)" strokeWidth="1.5" strokeDasharray="6 4" />
              <text x="487" y="142" textAnchor="middle" fontSize="24" fill="var(--ra-color-accent, currentColor)">确认</text>
              <text x="487" y="168" textAnchor="middle" fontSize="15" fill="var(--ra-color-muted, currentColor)">人工闸门</text>
              {/* 发送 */}
              <rect x="606" y="110" width="170" height="76" fill="none" />
              <text x="691" y="142" textAnchor="middle" fontSize="24" fill="var(--ra-color-fg, currentColor)">发送</text>
              <text x="691" y="168" textAnchor="middle" fontSize="15" fill="var(--ra-color-muted, currentColor)">无模型 Operator</text>
              {/* 箭头 */}
              <path d="M 176 148 H 214" stroke="var(--ra-color-fg, currentColor)" strokeWidth="1.5" markerEnd="url(#ra-cov-arrow)" />
              <path d="M 370 148 H 408" stroke="var(--ra-color-fg, currentColor)" strokeWidth="1.5" markerEnd="url(#ra-cov-arrow)" />
              <path d="M 564 148 H 602" stroke="var(--ra-color-accent, currentColor)" strokeWidth="1.5" markerEnd="url(#ra-cov-arrow)" />
              {/* 底部细线标注 */}
              <line x1="24" y1="250" x2="776" y2="250" stroke="var(--ra-color-border, currentColor)" strokeWidth="1" strokeDasharray="2 4" />
              <text x="24" y="280" fontSize="15" fill="var(--ra-color-muted, currentColor)">数据留在本机</text>
              <text x="776" y="280" textAnchor="end" fontSize="15" fill="var(--ra-color-muted, currentColor)">默认不自动发送</text>
            </g>
            <defs>
              <marker id="ra-cov-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--ra-color-fg, currentColor)" />
              </marker>
            </defs>
          </svg>
        </div>
      </div>
    </section>
  );
}
