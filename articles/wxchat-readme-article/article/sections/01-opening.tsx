import { Section, Aside, Raw } from "reacticle";

// One Section per file. In parallel builds a single subagent owns this file and
// must not touch Article.tsx or other section files. See references/section-build.md.
//
// 第一节：这是怎样一个助手 —— 定位句 + 默认安全声明（source.md 第 1-3 段）。
// 正文为主体；Aside 承载默认安全声明（原引言块）；Raw 画「本地 vs 可选外部模型」边界，
// 服务「本地优先」论点。tufte 气质：细线、发丝参考线、低装饰，只用 --ra-* token。
export function SectionOpening() {
  return (
    <Section index="01" title="这是怎样一个助手">
      <p>
        wxChatAIAssistant 是一个<strong>本地优先的关系型微信 AI 聊天助手</strong>。它不做
        通用的「一键群发」，而是回到回复这件事的最小单位——一段与某个具体联系人的对话——
        帮助你按<strong>联系人关系、表达习惯和对话上下文</strong>生成回复草稿。
      </p>
      <p>
        「关系化」是它区别于普通聊天助手的起点：对情侣、朋友、家人，称呼、边界、回复长度、
        表情和幽默偏好都不一样。它把「为谁写」放在「写什么」之前——草稿不是从一个通用模型
        里生成再套话术，而是先识别你与对方的相处方式，再据此组织语言。
      </p>
      <p>
        更重要的是它的「本地优先」承诺：<strong>微信读取、画像、设置和运行记录默认都留在
        自己的电脑上</strong>。项目把个人数据放进本机的 <code>data/</code> 目录，不依赖云端
        账号，也不把聊天内容送上服务器——这是后面所有安全讨论的地基。
      </p>

      <Aside tone="warning" label="默认安全声明">
        默认不发送消息。自动回复默认关闭、默认 dry-run；L1/L2 必须人工确认，L3 直接拦截。
      </Aside>

      <Raw title="本地边界：数据留在本机，仅模型调用可选出网">
        <svg
          viewBox="0 0 720 300"
          width="100%"
          role="img"
          aria-label="本机数据与可选外部模型调用之间的边界示意"
        >
          {/* 参考线：顶部细线标注 */}
          <line x1="20" y1="24" x2="700" y2="24" stroke="var(--ra-color-border, currentColor)" strokeWidth="1" />
          <text x="20" y="18" fontSize="12" fill="var(--ra-color-muted, currentColor)" letterSpacing="0.12em">
            本机（默认）
          </text>
          <text x="700" y="18" textAnchor="end" fontSize="12" fill="var(--ra-color-muted, currentColor)" letterSpacing="0.12em">
            可选 · 仅模型调用出网
          </text>

          {/* 本地大框：data/ 目录五项 */}
          <rect x="20" y="40" width="440" height="220" fill="none" stroke="var(--ra-color-fg, currentColor)" strokeWidth="1.5" />
          <text x="40" y="72" fontSize="15" fill="var(--ra-color-fg, currentColor)">
            data/ —— 个人数据只在这里
          </text>
          <g fontSize="13" fill="var(--ra-color-muted, currentColor)">
            <text x="40" y="102">config.sqlite3 · 联系人、模型、自动回复设置</text>
            <text x="40" y="126">messages.jsonl / feedback.jsonl · 导入记录与草稿反馈</text>
            <text x="40" y="150">self-skill/ · 全局、关系、联系人级表达画像</text>
            <text x="40" y="174">automation-state.json / automation-events.jsonl · 自动化状态</text>
          </g>
          {/* 分隔细线 + 底线承诺 */}
          <line x1="40" y1="196" x2="440" y2="196" stroke="var(--ra-color-border, currentColor)" strokeWidth="1" strokeDasharray="2 4" />
          <text x="40" y="222" fontSize="13" fill="var(--ra-color-accent, currentColor)">
            微信读取 · 画像 · 设置 · 运行记录 —— 默认不出网
          </text>
          <text x="40" y="246" fontSize="13" fill="var(--ra-color-muted, currentColor)">
            公开仓库不应包含 data/ · private/ · .runtime/ · 日志 · 环境变量 · 私钥
          </text>

          {/* 虚线边界 */}
          <line x1="500" y1="40" x2="500" y2="260" stroke="var(--ra-color-border, currentColor)" strokeWidth="1" strokeDasharray="6 5" />
          <text x="500" y="284" textAnchor="middle" fontSize="12" fill="var(--ra-color-muted, currentColor)">
            边界
          </text>

          {/* 外部小框：模型接口 */}
          <rect x="520" y="40" width="180" height="220" fill="none" stroke="var(--ra-color-muted, currentColor)" strokeWidth="1" />
          <text x="540" y="72" fontSize="15" fill="var(--ra-color-fg, currentColor)">模型接口</text>
          <text x="540" y="102" fontSize="13" fill="var(--ra-color-muted, currentColor)">Ollama · 本地模型</text>
          <text x="540" y="126" fontSize="13" fill="var(--ra-color-muted, currentColor)">OpenAI 兼容接口</text>
          <text x="540" y="150" fontSize="13" fill="var(--ra-color-muted, currentColor)">失败时回退本地模板</text>
          {/* 演示模式 */}
          <line x1="540" y1="174" x2="680" y2="174" stroke="var(--ra-color-border, currentColor)" strokeWidth="1" strokeDasharray="2 4" />
          <text x="540" y="200" fontSize="13" fill="var(--ra-color-accent, currentColor)">演示模式 · 可离线体验</text>

          {/* 单向箭头：仅生成草稿时调用，不回流数据 */}
          <path
            d="M 464 150 H 516"
            stroke="var(--ra-color-muted, currentColor)"
            strokeWidth="1.5"
            markerEnd="url(#ra-open-arrow)"
          />
          <defs>
            <marker
              id="ra-open-arrow"
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="7"
              markerHeight="7"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--ra-color-muted, currentColor)" />
            </marker>
          </defs>
        </svg>
      </Raw>
    </Section>
  );
}
