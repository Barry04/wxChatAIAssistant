import {
  Clipboard,
  Database,
  FileText,
  MessageCircle,
  Send,
  ShieldCheck,
  Sparkles,
} from 'lucide-react'

const draftAgentNodes = [
  { role: 'understand', label: '理解', caption: '识别场景与风险', icon: MessageCircle },
  { role: 'style', label: '风格', caption: '组合关系与表达', icon: Sparkles },
  { role: 'writer', label: '写手', caption: '生成候选草稿', icon: FileText },
  { role: 'reviewer', label: '审核', caption: '安全与质量复核', icon: ShieldCheck },
]

function AgentFlowGraph({ pipeline }) {
  const latestStepForRole = (role) =>
    [...pipeline.steps].reverse().find((step) => step.role === role)
  const stoppedEarly =
    pipeline.decision === 'block' && !latestStepForRole('reviewer')

  return (
    <div className="agent-flow-graph" aria-label="草稿生成 Agent 流转图">
      <div className="agent-flow-caption">
        <span>实时 Trace</span>
        <strong>{stoppedEarly ? '风险拦截，后续节点未运行' : '按顺序协作生成草稿'}</strong>
      </div>
      <div className="agent-flow-track">
        {draftAgentNodes.map((node, index) => {
          const step = latestStepForRole(node.role)
          const NodeIcon = node.icon
          const isSkipped = !step
          const status = step?.status || (isSkipped ? 'skipped' : 'ok')
          return (
            <div className="agent-flow-segment" key={node.role}>
              <article
                className={`agent-flow-node status-${status} ${
                  isSkipped ? 'is-skipped' : ''
                }`}
              >
                <span className="agent-flow-node-icon">
                  <NodeIcon size={16} aria-hidden="true" />
                </span>
                <span className="agent-flow-node-copy">
                  <strong>{node.label}</strong>
                  <small>{step?.summary || (isSkipped ? '未执行' : node.caption)}</small>
                </span>
                {typeof step?.duration_ms === 'number' && (
                  <span className="agent-flow-node-time">{step.duration_ms}ms</span>
                )}
              </article>
              {index < draftAgentNodes.length - 1 && (
                <span className="agent-flow-arrow" aria-hidden="true" />
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function AutomationFlowGraph({ events }) {
  const latest = events[events.length - 1]
  const latestAgent = latest?.agent || ''
  const latestAction = latest?.action || ''
  const policyRoute =
    latestAction === 'needs_confirmation'
      ? 'confirmation'
      : latestAgent === 'operator' || latestAction === 'sent'
        ? 'operator'
        : latestAction === 'blocked'
          ? 'blocked'
          : ''
  const nodes = [
    { id: 'watch', label: 'Watch', caption: '读取白名单新消息', icon: Database },
    { id: 'memory', label: 'Memory', caption: '同步已完成回合', icon: Clipboard },
    { id: 'draft', label: 'Draft', caption: '生成候选回复', icon: Sparkles },
    { id: 'policy', label: 'Policy', caption: '判定发送策略', icon: ShieldCheck },
  ]

  return (
    <section className="automation-flow" aria-label="自动化 Agent 流转图">
      <div className="automation-flow-header">
        <div>
          <span className="eyebrow">自动化流转</span>
          <strong>消息不会绕过策略门直接发送</strong>
        </div>
        {latest && (
          <span className="automation-flow-latest">
            最近：{latest.agent || '系统'} · {latestAction || '待运行'}
          </span>
        )}
      </div>
      <div className="automation-flow-track">
        {nodes.map((node, index) => {
          const NodeIcon = node.icon
          return (
            <div className="automation-flow-segment" key={node.id}>
              <article
                className={`automation-flow-node ${
                  latestAgent === node.id ? 'is-current' : ''
                }`}
              >
                <NodeIcon size={15} aria-hidden="true" />
                <span>
                  <strong>{node.label}</strong>
                  <small>{node.caption}</small>
                </span>
              </article>
              {index < nodes.length - 1 && (
                <span className="automation-flow-arrow" aria-hidden="true" />
              )}
            </div>
          )
        })}
        <div className="automation-flow-branches">
          <article
            className={`automation-flow-branch ${
              policyRoute === 'confirmation' ? 'is-current' : ''
            }`}
          >
            <ShieldCheck size={15} aria-hidden="true" />
            <span>
              <strong>待确认</strong>
              <small>L1 / L2 或 dry-run</small>
            </span>
          </article>
          <article
            className={`automation-flow-branch ${
              policyRoute === 'operator' ? 'is-current' : ''
            } ${policyRoute === 'blocked' ? 'is-blocked' : ''}`}
          >
            <Send size={15} aria-hidden="true" />
            <span>
              <strong>{policyRoute === 'blocked' ? '已拦截' : 'Operator'}</strong>
              <small>{policyRoute === 'blocked' ? '策略禁止发送' : '仅发送已批准原文'}</small>
            </span>
          </article>
        </div>
      </div>
    </section>
  )
}

export { AgentFlowGraph, AutomationFlowGraph }
