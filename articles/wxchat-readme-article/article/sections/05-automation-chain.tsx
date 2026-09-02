import { Section, CodeBlock, Raw } from "reacticle";

// 第五节：受控自动化链路 —— source.md「新版能力」第 4 条。
// 正文 + CodeBlock（编排链）+ Raw SVG（watch→memory→draft→policy→operator/queue），
// 服务「受控」论点：自动化每一环都可审计，发送前有策略闸门。
export function SectionAutomationChain() {
  return (
    <Section index="05" title="受控自动化链路">
      <p>
        真正的自动化——让系统在无人值守时处理消息——是<strong>受控</strong>的，而不是「放开
        让它自己发」。链路从一个保守的前提开始：<strong>Watcher 只读取白名单消息</strong>，
        不在白名单内的对话，自动化连看都不看。
      </p>

      <CodeBlock
        language="text"
        title="编排链"
        code={`watch → memory → draft → policy → operator/queue`}
      />

      <p>
        <strong>Orchestrator</strong> 按上面的顺序编排整条链路：watch 监听白名单消息，memory
        读取会话与画像上下文，draft 生成草稿，policy 过策略闸门，最后进入 operator 或队列。
        每一步都是明确的阶段，没有「黑盒自动发送」的暗箱。
      </p>
      <p>
        链路的终点是<strong>Operator</strong>——它<strong>只接收已批准的原文</strong>，负责
        会话校验、发送与结果验证。注意这里的分工：生成、审批、执行由不同角色承担，任何一环
        都没有「既当运动员又当裁判」的能力。
      </p>

      <Raw title="受控链路：从监听白名单到发送执行">
        <svg viewBox="0 0 760 150" width="100%" role="img" aria-label="watch 到 operator 的受控自动化链路">
          <line x1="20" y1="20" x2="740" y2="20" stroke="var(--ra-color-border, currentColor)" strokeWidth="1" />
          {/* 五个阶段框 */}
          <g fontFamily="var(--ra-font-body, inherit)">
            <rect x="24" y="46" width="120" height="56" fill="none" stroke="var(--ra-color-fg, currentColor)" strokeWidth="1.5" />
            <text x="84" y="70" textAnchor="middle" fontSize="14" fill="var(--ra-color-fg, currentColor)">watch</text>
            <text x="84" y="90" textAnchor="middle" fontSize="11" fill="var(--ra-color-muted, currentColor)">白名单消息</text>

            <rect x="168" y="46" width="120" height="56" fill="none" stroke="var(--ra-color-fg, currentColor)" strokeWidth="1.5" />
            <text x="228" y="70" textAnchor="middle" fontSize="14" fill="var(--ra-color-fg, currentColor)">memory</text>
            <text x="228" y="90" textAnchor="middle" fontSize="11" fill="var(--ra-color-muted, currentColor)">会话与画像</text>

            <rect x="312" y="46" width="120" height="56" fill="none" stroke="var(--ra-color-fg, currentColor)" strokeWidth="1.5" />
            <text x="372" y="70" textAnchor="middle" fontSize="14" fill="var(--ra-color-fg, currentColor)">draft</text>
            <text x="372" y="90" textAnchor="middle" fontSize="11" fill="var(--ra-color-muted, currentColor)">生成草稿</text>

            {/* policy：accent 强调的策略闸门 */}
            <rect x="456" y="46" width="120" height="56" fill="none" stroke="var(--ra-color-accent, currentColor)" strokeWidth="1.5" />
            <text x="516" y="70" textAnchor="middle" fontSize="14" fill="var(--ra-color-accent, currentColor)">policy</text>
            <text x="516" y="90" textAnchor="middle" fontSize="11" fill="var(--ra-color-muted, currentColor)">策略闸门</text>

            <rect x="600" y="46" width="136" height="56" fill="none" stroke="var(--ra-color-fg, currentColor)" strokeWidth="1.5" />
            <text x="668" y="70" textAnchor="middle" fontSize="14" fill="var(--ra-color-fg, currentColor)">operator/queue</text>
            <text x="668" y="90" textAnchor="middle" fontSize="11" fill="var(--ra-color-muted, currentColor)">批准原文 · 发送验证</text>
          </g>
          {/* 箭头 */}
          <g stroke="var(--ra-color-fg, currentColor)" strokeWidth="1.5" fill="none">
            <path d="M 146 74 H 164" markerEnd="url(#ra-auto-arrow)" />
            <path d="M 290 74 H 308" markerEnd="url(#ra-auto-arrow)" />
            <path d="M 434 74 H 452" markerEnd="url(#ra-auto-arrow)" />
            <path d="M 578 74 H 596" markerEnd="url(#ra-auto-arrow)" />
          </g>
          <defs>
            <marker id="ra-auto-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--ra-color-fg, currentColor)" />
            </marker>
          </defs>
          <line x1="20" y1="132" x2="740" y2="132" stroke="var(--ra-color-border, currentColor)" strokeWidth="1" strokeDasharray="2 4" />
          <text x="20" y="124" fontSize="12" fill="var(--ra-color-muted, currentColor)">每一环都可审计</text>
          <text x="740" y="124" textAnchor="end" fontSize="12" fill="var(--ra-color-muted, currentColor)">发送只发生在策略通过之后</text>
        </svg>
      </Raw>
    </Section>
  );
}
