import { Section, Table, Quote, Raw } from "reacticle";

// 第七节：安全模型（核心）—— source.md「安全模型」整节。
// Table（L0/L1-L2/L3）+ 无发送能力声明 + Quote（合规提示）+ Raw SVG（风险分级条）。
// 这是全篇最关键的一节，正文把「分级 + 分工」讲透。
export function SectionSecurityModel() {
  return (
    <Section index="07" title="安全模型">
      <p>
        安全在这里不是「模型很听话」的自我标榜，而是<strong>分级 + 分工</strong>两套机制。
        分级决定一条草稿的风险待遇，分工决定谁能碰发送。先看风险分级：
      </p>

      <Table
        caption="风险分级：不同级别，不同放行路径"
        columns={[
          { key: "level", label: "风险级别", width: "18%" },
          { key: "behavior", label: "行为" },
        ]}
        rows={[
          {
            level: <strong>L0</strong>,
            behavior:
              "可生成普通草稿；只有白名单、明确开启、关闭 dry-run 且通过策略门时才可能自动发送。",
          },
          {
            level: <strong>L1 / L2</strong>,
            behavior: "进入待确认队列，必须由用户逐条确认或放弃。",
          },
          {
            level: <strong>L3</strong>,
            behavior: "拦截，不生成可直接发送的候选。",
          },
        ]}
      />

      <p>
        分级管「能不能发」，分工管「谁来发」。<strong>草稿 Agent 不具备微信发送能力</strong>；
        真实发送只由<strong>无模型的 Operator</strong> 执行，而且它必须<strong>已有批准的原文</strong>
        才动手。生成、审核、发送三件事由不同角色承担，任何一环越权都会在另一环被拦下。
      </p>

      <Quote who="README · 安全模型">
        请勿将本工具用于未经对方同意的自动化沟通。
      </Quote>

      <Raw title="风险分级条：L0 可发 · L1/L2 待确认 · L3 拦截">
        <svg viewBox="0 0 760 150" width="100%" role="img" aria-label="L0、L1/L2、L3 三级风险放行路径">
          <line x1="20" y1="20" x2="740" y2="20" stroke="var(--ra-color-border, currentColor)" strokeWidth="1" />
          {/* 三段条带：L0（可发）L1/L2（待确认）L3（拦截） */}
          <g>
            <rect x="20" y="48" width="180" height="52" fill="none" stroke="var(--ra-color-fg, currentColor)" strokeWidth="1.5" />
            <text x="110" y="72" textAnchor="middle" fontSize="15" fill="var(--ra-color-fg, currentColor)">L0</text>
            <text x="110" y="92" textAnchor="middle" fontSize="12" fill="var(--ra-color-muted, currentColor)">可生成普通草稿</text>

            <rect x="240" y="48" width="260" height="52" fill="none" stroke="var(--ra-color-accent, currentColor)" strokeWidth="1.5" />
            <text x="370" y="72" textAnchor="middle" fontSize="15" fill="var(--ra-color-accent, currentColor)">L1 / L2</text>
            <text x="370" y="92" textAnchor="middle" fontSize="12" fill="var(--ra-color-muted, currentColor)">待确认队列 · 逐条确认或放弃</text>

            <rect x="540" y="48" width="200" height="52" fill="none" stroke="var(--ra-color-muted, currentColor)" strokeWidth="1.5" />
            <text x="640" y="72" textAnchor="middle" fontSize="15" fill="var(--ra-color-muted, currentColor)">L3</text>
            <text x="640" y="92" textAnchor="middle" fontSize="12" fill="var(--ra-color-muted, currentColor)">拦截 · 不生成可直接发送候选</text>
          </g>
          {/* 放行路径标注 */}
          <g stroke="var(--ra-color-border, currentColor)" strokeWidth="1" fill="none">
            <path d="M 110 104 V 120 H 640 V 104" strokeDasharray="2 4" />
          </g>
          <text x="110" y="136" textAnchor="middle" fontSize="12" fill="var(--ra-color-muted, currentColor)">
            可自动发送（需白名单 + 开启 + 关 dry-run + 过策略门）
          </text>
          <text x="370" y="136" textAnchor="middle" fontSize="12" fill="var(--ra-color-muted, currentColor)">
            人工确认
          </text>
          <text x="640" y="136" textAnchor="middle" fontSize="12" fill="var(--ra-color-muted, currentColor)">
            直接拦截
          </text>
        </svg>
      </Raw>
    </Section>
  );
}
