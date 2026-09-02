import { Section, CodeBlock, Raw } from "reacticle";

// 第三节：多角色草稿生成 —— source.md「新版能力」第 2 条。
// 正文 + CodeBlock（角色链）+ Raw SVG（四角色审查顺序），服务「多角色审核」论点。
// tufte 气质：细线流程、低装饰、只用 --ra-* token。
export function SectionDraftPipeline() {
  return (
    <Section index="03" title="多角色草稿生成">
      <p>
        一条回复草稿不是「点一下按钮让模型写一段」那么简单，而是由四个角色<strong>依次接力</strong>
        完成：
      </p>

      <CodeBlock
        language="text"
        title="角色链"
        code={`understand → style → writer → reviewer`}
      />

      <p>
        <strong>understand</strong> 先识别场景与风险——这条消息在什么语境里、有没有越界的可能；
        <strong>style</strong> 再组合关系和个人风格——调用工作台里维护的称呼、边界与幽默偏好；
        <strong>writer</strong> 生成候选文本；最后由 <strong>reviewer</strong> 做安全与质量审核，
        把不合适的候选拦在发送之前。
      </p>
      <p>
        把「识别、组合、生成、审核」拆成四个角色，而不是让一个模型一步到位，目的很直接：
        <strong>安全与质量在生成之后还有一道独立关口</strong>。生成者与审核者分离，审核才不是
        自说自话——这也是后面安全模型里「草稿 Agent 不具备发送能力」的设计前提。
      </p>

      <Raw title="四角色审查顺序：每个候选都过一遍流水线">
        <svg viewBox="0 0 760 160" width="100%" role="img" aria-label="understand 到 reviewer 的四角色流水线">
          <line x1="20" y1="20" x2="740" y2="20" stroke="var(--ra-color-border, currentColor)" strokeWidth="1" />
          {/* 四个角色框：细线、等宽、间距留白 */}
          <g>
            <rect x="40" y="48" width="150" height="64" fill="none" stroke="var(--ra-color-fg, currentColor)" strokeWidth="1.5" />
            <text x="115" y="76" textAnchor="middle" fontSize="16" fill="var(--ra-color-fg, currentColor)">understand</text>
            <text x="115" y="98" textAnchor="middle" fontSize="12" fill="var(--ra-color-muted, currentColor)">识别场景与风险</text>
          </g>
          <g>
            <rect x="220" y="48" width="150" height="64" fill="none" stroke="var(--ra-color-fg, currentColor)" strokeWidth="1.5" />
            <text x="295" y="76" textAnchor="middle" fontSize="16" fill="var(--ra-color-fg, currentColor)">style</text>
            <text x="295" y="98" textAnchor="middle" fontSize="12" fill="var(--ra-color-muted, currentColor)">组合关系与风格</text>
          </g>
          <g>
            <rect x="400" y="48" width="150" height="64" fill="none" stroke="var(--ra-color-fg, currentColor)" strokeWidth="1.5" />
            <text x="475" y="76" textAnchor="middle" fontSize="16" fill="var(--ra-color-fg, currentColor)">writer</text>
            <text x="475" y="98" textAnchor="middle" fontSize="12" fill="var(--ra-color-muted, currentColor)">生成候选</text>
          </g>
          {/* reviewer：accent 强调（审核关口） */}
          <g>
            <rect x="580" y="48" width="150" height="64" fill="none" stroke="var(--ra-color-accent, currentColor)" strokeWidth="1.5" />
            <text x="655" y="76" textAnchor="middle" fontSize="16" fill="var(--ra-color-accent, currentColor)">reviewer</text>
            <text x="655" y="98" textAnchor="middle" fontSize="12" fill="var(--ra-color-muted, currentColor)">安全与质量审核</text>
          </g>
          {/* 箭头 */}
          <g stroke="var(--ra-color-fg, currentColor)" strokeWidth="1.5" fill="none">
            <path d="M 192 80 H 216" markerEnd="url(#ra-pipe-arrow)" />
            <path d="M 372 80 H 396" markerEnd="url(#ra-pipe-arrow)" />
            <path d="M 552 80 H 576" markerEnd="url(#ra-pipe-arrow)" />
          </g>
          <defs>
            <marker id="ra-pipe-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--ra-color-fg, currentColor)" />
            </marker>
          </defs>
          {/* 底部标注 */}
          <line x1="20" y1="140" x2="740" y2="140" stroke="var(--ra-color-border, currentColor)" strokeWidth="1" strokeDasharray="2 4" />
          <text x="20" y="132" fontSize="12" fill="var(--ra-color-muted, currentColor)">每个候选都完整经过四步</text>
          <text x="740" y="132" textAnchor="end" fontSize="12" fill="var(--ra-color-muted, currentColor)">审核在生成之后独立把关</text>
        </svg>
      </Raw>
    </Section>
  );
}
