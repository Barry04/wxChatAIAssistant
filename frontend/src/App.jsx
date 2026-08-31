import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity,
  Check,
  Clipboard,
  ChevronDown,
  Database,
  FileText,
  Heart,
  Home,
  LoaderCircle,
  MessageCircle,
  Paperclip,
  Pause,
  Pencil,
  Plus,
  Play,
  RefreshCw,
  RotateCcw,
  Send,
  Settings,
  ShieldCheck,
  Smile,
  Sparkles,
  Trash2,
  Upload,
  UserRound,
  Users,
  X,
} from 'lucide-react'
import OperationsPage from './OperationsPage.jsx'
import './App.css'
import './Modern.css'

const relationshipMeta = {
  partner: { label: '情侣', icon: Heart, color: '#d85b7d' },
  friend: { label: '朋友', icon: Users, color: '#23866f' },
  family: { label: '家人', icon: Home, color: '#b57617' },
}

const autoSendLevelOptions = [
  { level: 'L0', label: 'L0 日常聊天' },
]

const lengthLabels = {
  very_short: '很短',
  short: '简短',
  medium: '适中',
}

const emojiLabels = {
  none: '不用',
  low: '偶尔',
  medium: '适中',
  high: '经常',
}

const humorLabels = {
  low: '克制',
  medium: '自然',
  high: '活跃',
}

const BOOTSTRAP_CACHE_KEY = 'wx-chat-assistant:bootstrap:v1'
const BOOTSTRAP_CACHE_TTL_MS = 2 * 60 * 1000
const GLOBAL_PENDING_PATH = '/pending'
const OPERATIONS_PATH = '/operations'

function getAppPage() {
  if (window.location.pathname === GLOBAL_PENDING_PATH) return 'pending'
  if (window.location.pathname === OPERATIONS_PATH) return 'operations'
  return 'workspace'
}

function readBootstrapCache() {
  try {
    const stored = window.localStorage.getItem(BOOTSTRAP_CACHE_KEY)
    if (!stored) return null
    const record = JSON.parse(stored)
    if (
      !record?.data ||
      !Array.isArray(record.data.contacts) ||
      !Array.isArray(record.data.skills) ||
      typeof record.savedAt !== 'number'
    ) {
      window.localStorage.removeItem(BOOTSTRAP_CACHE_KEY)
      return null
    }
    return record
  } catch {
    return null
  }
}

function writeBootstrapCache(data) {
  try {
    window.localStorage.setItem(
      BOOTSTRAP_CACHE_KEY,
      JSON.stringify({ savedAt: Date.now(), data }),
    )
  } catch {
    // 缓存不可用时继续走本地 API，不影响工作台使用。
  }
}

function formatAutoSendMode(settings, wechatStatus) {
  if (!settings?.enabled || settings?.dry_run) return 'Dry-run'
  const levels = (settings.auto_send_levels || ['L0']).filter(
    (level) => level === 'L0',
  )
  const levelText = levels.length ? levels.join('、') : '无自动发送级别'
  if (!wechatStatus?.running || !wechatStatus?.logged_in) {
    return `微信未连接（${levelText}）`
  }
  return `允许发送 ${levelText}`
}

const sceneLabels = {
  daily: '日常聊天',
  comfort: '安慰陪伴',
  conflict: '敏感沟通',
  invitation: '邀约商量',
  joking: '玩笑互动',
  concern: '回应关心',
}

const roleLabels = {
  understand: '理解',
  style: '风格',
  writer: '写手',
  reviewer: '审核',
}

const reviewDecisionMeta = {
  accept: { label: '已通过', tone: 'accept' },
  revise: { label: '已重写', tone: 'revise' },
  block: { label: '已拦截', tone: 'block' },
}

function summarizeAgentPipeline(result) {
  if (!result?.trace?.length) return null
  const roles = result.trace.map((item) => item.role)
  const writerPasses = roles.filter((role) => role === 'writer').length
  const decision = result.review?.decision || (result.risk?.level === 'L3' ? 'block' : 'accept')
  return {
    steps: result.trace,
    writerPasses,
    decision,
    decisionMeta: reviewDecisionMeta[decision] || reviewDecisionMeta.accept,
    issues: result.review?.issues || [],
  }
}

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
  const hubTrace = latest?.hub_trace || []
  const latestHub = [...hubTrace].reverse().find((step) => step.task === 'hub')
  const policyRoute =
    latestAction === 'needs_confirmation'
      ? 'confirmation'
      : latestAgent === 'operator' || latestAction === 'sent'
        ? 'operator'
        : latestAction === 'blocked'
          ? 'blocked'
          : ''
  const nodes = [
    { id: 'watch_read', label: 'Watch Task', caption: '读取并判定新消息', icon: Database },
    { id: 'memory_sync', label: 'Memory Task', caption: '同步已完成回合', icon: Clipboard },
    { id: 'draft', label: 'Draft Task', caption: '运行草稿子图', icon: Sparkles },
  ]
  const policyNode = { id: 'policy', label: 'Policy Gate', caption: '代码硬门禁', icon: ShieldCheck }
  const PolicyIcon = policyNode.icon

  return (
    <section className="automation-flow" aria-label="自动化 Agent 流转图">
      <div className="automation-flow-header">
        <div>
          <span className="eyebrow">Hub Orchestration</span>
          <strong>Task 完成后回到 Hub 决策，发送仍受代码门禁</strong>
        </div>
        {latest && (
          <span className="automation-flow-latest">
            {latest.orchestration_mode === 'langgraph-hub' ? 'HUB' : latest.agent || '系统'} ·{' '}
            {latestAction || '待运行'}
          </span>
        )}
      </div>
      <div className="automation-flow-hub-track">
        <div className="automation-flow-task-stack">
        {nodes.map((node, index) => {
          const NodeIcon = node.icon
          const steps = hubTrace.filter((step) => step.task === node.id)
          const step = steps[steps.length - 1]
          const isCurrent = latestHub?.next_task === node.id
          return (
            <div className="automation-flow-task-wrap" key={node.id}>
              <article
                className={`automation-flow-node ${
                  isCurrent || (latestAgent === node.id && !hubTrace.length) ? 'is-current' : ''
                } ${step?.status === 'fallback' ? 'is-fallback' : ''}`}
              >
                <NodeIcon size={15} aria-hidden="true" />
                <span>
                  <strong>{node.label}</strong>
                  <small>{step?.reason_code || node.caption}</small>
                </span>
                {typeof step?.duration_ms === 'number' && (
                  <em>{step.duration_ms}ms</em>
                )}
              </article>
              {index < nodes.length - 1 && <span className="automation-flow-task-arrow" aria-hidden="true" />}
            </div>
          )
        })}
        </div>
        <span className="automation-flow-hub-arrow" aria-hidden="true" />
        <article className={`automation-flow-hub-node ${latestHub ? 'is-current' : ''}`}>
          <div className="automation-flow-hub-icon">
            <Sparkles size={16} aria-hidden="true" />
          </div>
          <span>
            <strong>Hub 决策</strong>
            <small>HUB_REASON · {latestHub?.reason_code || '等待下一轮'}</small>
            <em>
              {latestHub?.decision_source === 'model'
                ? '真实模型路由'
                : latestHub?.decision_source === 'fallback'
                  ? '规则回退'
                  : '安全规则路由'}
            </em>
          </span>
        </article>
      </div>
      <div className="automation-flow-track automation-flow-policy-track">
        <div className="automation-flow-segment">
          <article
            className={`automation-flow-node ${
              latestAgent === policyNode.id ? 'is-current' : ''
            }`}
          >
            <PolicyIcon size={15} aria-hidden="true" />
            <span>
              <strong>{policyNode.label}</strong>
              <small>{policyNode.caption}</small>
            </span>
          </article>
        </div>
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

function summarizeContactCheck(contact, actions = []) {
  const action = actions[0]
  if (!action) return `已检查${contact.display_name}，没有发现未回复的历史消息`
  if (action.action === 'sent' && action.send_verified) {
    return `已向${contact.display_name}发送并验证回复`
  }
  if (action.action === 'needs_confirmation') {
    return `已为${contact.display_name}生成待确认草稿，尚未发送到微信`
  }
  if (action.action === 'waiting_for_user') {
    return `检测到${contact.display_name}未回复消息，仍在等待人工接管，尚未发送`
  }
  if (action.action === 'send_unverified') {
    return `向${contact.display_name}发送未获验证，系统不会标记为已回复`
  }
  if (action.action === 'read_error') {
    return `无法读取${contact.display_name}的微信消息：${action.error || '未知错误'}`
  }
  if (action.action === 'already_replied') {
    return `${contact.display_name}的最新消息已有你的回复，无需发送`
  }
  if (action.action === 'blocked') {
    return `已拦截${contact.display_name}的候选回复，未发送到微信`
  }
  return `已检查${contact.display_name}，本次状态：${action.action || '无可发送回复'}`
}

function AttachmentPicker({ files, onChange, inputId }) {
  return (
    <label className="pending-attachments" htmlFor={inputId}>
      <span>已批准附件</span>
      <div className="pending-attachment-row">
        <input
          id={inputId}
          type="file"
          multiple
          accept="image/*,.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.zip,.txt"
          onChange={(event) =>
            onChange(Array.from(event.target.files || []).slice(0, 5))
          }
        />
        <span className="pending-attachment-button">
          <Paperclip size={15} />
          {files.length ? `已选 ${files.length} 个文件` : '添加图片或文件'}
        </span>
      </div>
      {files.length > 0 && (
        <ul className="pending-attachment-list">
          {files.map((file) => (
            <li key={`${file.name}-${file.size}`}>{file.name}</li>
          ))}
        </ul>
      )}
    </label>
  )
}

function PendingConfirmationList({
  pending,
  pendingDrafts,
  setPendingDrafts,
  attachmentFiles = {},
  onAttachmentsChange,
  quoteEnabled = {},
  onQuoteChange,
  atEnabled = {},
  onAtChange,
  working,
  onConfirm,
  onDiscard,
  heading = '待确认队列',
  emptyText = '暂无待确认回复。确认后只会把已批准原文交给发送执行器。',
  listId,
}) {
  return (
    <div className="pending-confirmations" id={listId}>
      <div className="pending-heading">
        <strong>{heading}</strong>
        <span>{pending.length} 条</span>
      </div>
      {pending.length === 0 ? (
        <p className="form-hint">{emptyText}</p>
      ) : (
        pending.map((item) => (
          <article className="pending-item" key={item.id}>
            <div className="pending-item-header">
              <strong>{item.display_name}</strong>
              <span>{item.risk?.level || '未知风险'}</span>
            </div>
            {item.incoming?.length > 0 && (
              <p className="pending-incoming">
                {item.incoming.slice(-2).join(' / ')}
              </p>
            )}
            {item.quote_preview ? (
              <label className="pending-quote-toggle">
                <input
                  type="checkbox"
                  checked={quoteEnabled[item.id] ?? true}
                  onChange={(event) =>
                    onQuoteChange?.(item.id, event.target.checked)
                  }
                />
                将引用：{item.quote_preview}
              </label>
            ) : null}
            {(item.at_targets || []).length > 0 ? (
              <label className="pending-quote-toggle">
                <input
                  type="checkbox"
                  checked={atEnabled[item.id] ?? true}
                  onChange={(event) =>
                    onAtChange?.(item.id, event.target.checked)
                  }
                />
                将 @ {(item.at_targets || []).map((target) => target.name).join('、')}
              </label>
            ) : null}
            {(item.candidate_options?.length
              ? item.candidate_options
              : [item.candidate]
            )
              .filter(Boolean)
              .map((option, index) => (
                <button
                  type="button"
                  className={`l1-option ${
                    (pendingDrafts[item.id] ?? item.candidate) === option
                      ? 'selected'
                      : ''
                  }`}
                  key={`${item.id}-${option}-${index}`}
                  onClick={() =>
                    setPendingDrafts((drafts) => ({
                      ...drafts,
                      [item.id]: option,
                    }))
                  }
                >
                  <span>{option}</span>
                </button>
              ))}
            <textarea
              value={pendingDrafts[item.id] ?? item.candidate ?? ''}
              onChange={(event) =>
                setPendingDrafts((drafts) => ({
                  ...drafts,
                  [item.id]: event.target.value,
                }))
              }
              maxLength={200}
              aria-label={`编辑${item.display_name}的候选回复`}
            />
            <AttachmentPicker
              inputId={`pending-files-${item.id}`}
              files={attachmentFiles[item.id] || []}
              onChange={(files) => onAttachmentsChange?.(item.id, files)}
            />
            <div className="pending-actions">
              <button
                type="button"
                className="button primary"
                onClick={() => onConfirm(item)}
                disabled={
                  Boolean(working) ||
                  !(
                    (pendingDrafts[item.id] || item.candidate || '').trim() ||
                    (attachmentFiles[item.id] || []).length
                  )
                }
              >
                {working === `confirm:${item.id}` ? (
                  <LoaderCircle className="spin" size={16} />
                ) : (
                  <Send size={16} />
                )}
                确认并发送
              </button>
              <button
                type="button"
                className="button ghost"
                onClick={() => onDiscard(item)}
                disabled={Boolean(working)}
              >
                <Trash2 size={16} />
                放弃
              </button>
            </div>
          </article>
        ))
      )}
    </div>
  )
}

function PendingWorkbench({
  pending,
  selectedContact,
  view = 'current',
  pendingDrafts,
  setPendingDrafts,
  attachmentFiles = {},
  onAttachmentsChange,
  quoteEnabled = {},
  onQuoteChange,
  atEnabled = {},
  onAtChange,
  working,
  onConfirm,
  onDiscard,
  onOpenAll,
  onOpenContact,
  canOpenContact = () => true,
}) {
  const [activeId, setActiveId] = useState('')
  const showingCurrentContact = view === 'current'
  const visiblePending = useMemo(
    () =>
      showingCurrentContact && selectedContact
        ? pending.filter((item) => item.contact_id === selectedContact.contact_id)
        : showingCurrentContact
          ? []
          : pending,
    [pending, selectedContact, showingCurrentContact],
  )
  const pendingGroups = Array.from(
    visiblePending
      .reduce((groups, item) => {
        const key = item.contact_id || item.display_name || item.id
        if (!groups.has(key)) {
          groups.set(key, {
            contactId: item.contact_id,
            displayName: item.display_name || '未知联系人',
            items: [],
          })
        }
        groups.get(key).items.push(item)
        return groups
      }, new Map())
      .values(),
  )

  useEffect(() => {
    if (!visiblePending.some((item) => item.id === activeId)) {
      setActiveId(visiblePending[0]?.id || '')
    }
  }, [activeId, visiblePending])

  const activeItem =
    visiblePending.find((item) => item.id === activeId) || visiblePending[0] || null
  const riskCount = visiblePending.filter((item) => item.risk?.level !== 'L0').length

  return (
    <section className="pending-workspace">
      <header className="pending-workspace-header">
        <div>
          <span className="eyebrow">
            {showingCurrentContact ? '当前会话' : '全局收件箱'}
          </span>
          <h2>
            {showingCurrentContact ? '当前会话待确认' : '全部会话待确认'}
          </h2>
          <p>
            {showingCurrentContact
              ? selectedContact
                ? `仅显示“${selectedContact.display_name}”的待确认回复。`
                : '请先选择一个联系人。'
              : '按联系人分组查看全部待确认回复，可逐条确认、放弃或返回对应会话。'}
          </p>
        </div>
        <div className="pending-header-actions">
          {showingCurrentContact && pending.length > visiblePending.length && (
            <button
              type="button"
              className="button secondary pending-global-link"
              onClick={onOpenAll}
            >
              查看全部 {pending.length} 条
            </button>
          )}
          <div className="pending-workspace-stats">
            <span>
              <strong>{visiblePending.length}</strong> 待处理
            </span>
            <span className={riskCount ? 'has-risk' : ''}>
              <strong>{riskCount}</strong> 需谨慎
            </span>
          </div>
        </div>
      </header>

      {visiblePending.length === 0 ? (
        <div className="pending-empty">
          <ShieldCheck size={30} />
          <strong>
            {showingCurrentContact
              ? `${selectedContact?.display_name || '当前会话'} 暂无待确认回复`
              : '队列已经清空'}
          </strong>
          <p>
            {showingCurrentContact && pending.length > 0
              ? '其他联系人仍有待确认回复，可前往全局收件箱处理。'
              : '新的待确认回复会出现在这里，不会自动发送。'}
          </p>
          {showingCurrentContact && pending.length > 0 && (
            <button
              type="button"
              className="button secondary"
              onClick={onOpenAll}
            >
              打开全部待确认
            </button>
          )}
        </div>
      ) : (
        <div className="pending-workbench-grid">
          <nav
            className={`pending-inbox ${showingCurrentContact ? '' : 'is-grouped'}`}
            aria-label="待确认消息"
          >
            {(showingCurrentContact
              ? [{ contactId: selectedContact?.contact_id, items: visiblePending }]
              : pendingGroups
            ).map((group) => (
              <section className="pending-inbox-group" key={group.contactId || 'current'}>
                {!showingCurrentContact && (
                  <div className="pending-inbox-group-heading">
                    <span>{group.displayName}</span>
                    <strong>{group.items.length} 条</strong>
                  </div>
                )}
                {group.items.map((item) => {
              const incoming = item.incoming?.slice(-2).join(' / ') || '无可用上下文'
              const preview =
                pendingDrafts[item.id] || item.candidate || '等待填写回复'
              return (
                <button
                  type="button"
                  className={`pending-inbox-item ${
                    activeItem?.id === item.id ? 'active' : ''
                  }`}
                  key={item.id}
                  onClick={() => setActiveId(item.id)}
                >
                  <span className="pending-inbox-meta">
                    <strong>{item.display_name}</strong>
                    <span className={`risk-dot risk-${item.risk?.level || 'L0'}`}>
                      {item.risk?.level || 'L0'}
                    </span>
                  </span>
                  <span className="pending-inbox-context">{incoming}</span>
                  <span className="pending-inbox-preview">{preview}</span>
                </button>
              )
                })}
              </section>
            ))}
          </nav>

          {activeItem && (
            <article className="pending-review-card">
              <div className="pending-review-heading">
                <div>
                  <span className="eyebrow">发送给</span>
                  <h3>{activeItem.display_name}</h3>
                </div>
                <span className={`risk-badge risk-${activeItem.risk?.level || 'L0'}`}>
                  {activeItem.risk?.level || 'L0'} ·{' '}
                  {activeItem.risk?.label || '普通聊天'}
                </span>
              </div>

              {!showingCurrentContact && (
                <button
                  type="button"
                  className="button ghost pending-open-contact"
                  onClick={() => onOpenContact(activeItem.contact_id)}
                  disabled={!canOpenContact(activeItem.contact_id)}
                  title={
                    canOpenContact(activeItem.contact_id)
                      ? '返回这个联系人的当前会话'
                      : '该联系人已不在工作台中'
                  }
                >
                  <MessageCircle size={16} />
                  {canOpenContact(activeItem.contact_id)
                    ? '回到该会话'
                    : '联系人未在工作台'}
                </button>
              )}

              <div className="pending-context-card">
                <span>对方最新消息</span>
                <p>{activeItem.incoming?.slice(-2).join('\n') || '无可用上下文'}</p>
              </div>
              {activeItem.quote_preview ? (
                <label className="pending-quote-toggle">
                  <input
                    type="checkbox"
                    checked={quoteEnabled[activeItem.id] ?? true}
                    onChange={(event) =>
                      onQuoteChange?.(activeItem.id, event.target.checked)
                    }
                  />
                  将引用：{activeItem.quote_preview}
                </label>
              ) : null}
              {(activeItem.at_targets || []).length > 0 ? (
                <label className="pending-quote-toggle">
                  <input
                    type="checkbox"
                    checked={atEnabled[activeItem.id] ?? true}
                    onChange={(event) =>
                      onAtChange?.(activeItem.id, event.target.checked)
                    }
                  />
                  将 @ {(activeItem.at_targets || []).map((target) => target.name).join('、')}
                </label>
              ) : null}

              <div className="pending-option-group">
                <span>选择一个候选</span>
                <div>
                  {(activeItem.candidate_options?.length
                    ? activeItem.candidate_options
                    : [activeItem.candidate]
                  )
                    .filter(Boolean)
                    .map((option, index) => (
                      <button
                        type="button"
                        className={`pending-option ${
                          (pendingDrafts[activeItem.id] ?? activeItem.candidate) ===
                          option
                            ? 'selected'
                            : ''
                        }`}
                        key={`${activeItem.id}-${option}-${index}`}
                        onClick={() =>
                          setPendingDrafts((drafts) => ({
                            ...drafts,
                            [activeItem.id]: option,
                          }))
                        }
                      >
                        <span>{option}</span>
                        {(pendingDrafts[activeItem.id] ?? activeItem.candidate) ===
                          option && <Check size={16} />}
                      </button>
                    ))}
                </div>
              </div>

              <label className="pending-final-copy">
                <span>最终发送文本</span>
                <textarea
                  value={
                    pendingDrafts[activeItem.id] ?? activeItem.candidate ?? ''
                  }
                  onChange={(event) =>
                    setPendingDrafts((drafts) => ({
                      ...drafts,
                      [activeItem.id]: event.target.value,
                    }))
                  }
                  maxLength={200}
                />
              </label>
              <AttachmentPicker
                inputId={`workbench-files-${activeItem.id}`}
                files={attachmentFiles[activeItem.id] || []}
                onChange={(files) => onAttachmentsChange?.(activeItem.id, files)}
              />

              <div className="pending-review-actions">
                <button
                  type="button"
                  className="button ghost danger"
                  onClick={() => onDiscard(activeItem)}
                  disabled={Boolean(working)}
                >
                  <Trash2 size={17} />
                  放弃这条
                </button>
                <button
                  type="button"
                  className="button primary"
                  onClick={() => onConfirm(activeItem)}
                  disabled={
                    Boolean(working) ||
                    !(
                      (pendingDrafts[activeItem.id] || activeItem.candidate || '').trim() ||
                      (attachmentFiles[activeItem.id] || []).length
                    )
                  }
                >
                  {working === `confirm:${activeItem.id}` ? (
                    <LoaderCircle className="spin" size={17} />
                  ) : (
                    <Send size={17} />
                  )}
                  确认并发送
                </button>
              </div>
            </article>
          )}
        </div>
      )}
    </section>
  )
}

const emptyContact = {
  contact_id: '',
  display_name: '',
  relationship: 'friend',
  wechat_username: '',
  chat_type: 'private',
  participant_count: null,
  group_trigger_mode: 'mention_only',
  group_mention_keywords: [],
  preferred_address: '',
  message_length: 'short',
  emoji_level: 'low',
  humor_level: 'medium',
  boundaries: [],
  style_preset_id: '',
  is_demo: false,
}

async function api(path, options = {}) {
  const response = await fetch(path, options)
  if (!response.ok) {
    let message = `请求失败（${response.status}）`
    try {
      const payload = await response.json()
      message = payload.detail || message
    } catch {
      // Keep the HTTP fallback when a response is not JSON.
    }
    throw new Error(message)
  }
  return response.json()
}

async function confirmPendingSend(item, text, files = [], quote = false, at = false) {
  if (files.length) {
    const form = new FormData()
    files.forEach((file) => form.append('files', file))
    await api(
      `/api/automation/pending/${encodeURIComponent(item.id)}/attachments`,
      { method: 'POST', body: form },
    )
  }
  return api(`/api/automation/confirm/${encodeURIComponent(item.id)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, quote, at }),
  })
}

function IconButton({ label, children, className = '', ...props }) {
  return (
    <button
      type="button"
      className={`icon-button ${className}`}
      aria-label={label}
      title={label}
      {...props}
    >
      {children}
    </button>
  )
}

function Modal({ title, subtitle, onClose, children, wide = false }) {
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className={`modal ${wide ? 'modal-wide' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="modal-header">
          <div>
            <h2>{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          <IconButton label="关闭" onClick={onClose}>
            <X size={18} />
          </IconButton>
        </header>
        {children}
      </section>
    </div>
  )
}

function App() {
  const [contacts, setContacts] = useState([])
  const [skills, setSkills] = useState([])
  const [stats, setStats] = useState(null)
  const [settings, setSettings] = useState(null)
  const [contactAutomationSettings, setContactAutomationSettings] =
    useState(null)
  const [selfSkill, setSelfSkill] = useState(null)
  const [girlsChatStyle, setGirlsChatStyle] = useState(null)
  const [stylePresets, setStylePresets] = useState([])
  const [wechatStatus, setWechatStatus] = useState(null)
  const [selectedId, setSelectedId] = useState('')
  const [conversation, setConversation] = useState('')
  const [result, setResult] = useState(null)
  const [selectedCandidate, setSelectedCandidate] = useState(-1)
  const [finalText, setFinalText] = useState('')
  const [busy, setBusy] = useState('')
  const [styleSaving, setStyleSaving] = useState(false)
  const [notice, setNotice] = useState(null)
  const [l1Prompt, setL1Prompt] = useState(null)
  const [l1PromptText, setL1PromptText] = useState('')
  const [contactCheckActions, setContactCheckActions] = useState([])
  const [modal, setModal] = useState('')
  const [mobileSidebar, setMobileSidebar] = useState(false)
  const [activeStylePresetId, setActiveStylePresetId] = useState('style:balanced')
  const [appPage, setAppPage] = useState(getAppPage)
  const [workspaceMode, setWorkspaceMode] = useState('draft')
  const [pendingCount, setPendingCount] = useState(0)
  const [pendingItems, setPendingItems] = useState([])
  const [pendingDrafts, setPendingDrafts] = useState({})
  const [pendingAttachments, setPendingAttachments] = useState({})
  const [quoteEnabled, setQuoteEnabled] = useState({})
  const [atEnabled, setAtEnabled] = useState({})
  const lastPendingL1Ids = useRef(null)

  const selectedContact = useMemo(
    () => contacts.find((item) => item.contact_id === selectedId),
    [contacts, selectedId],
  )

  const selectedSkill = useMemo(
    () => skills.find((item) => item.id === selectedContact?.relationship),
    [skills, selectedContact],
  )

  const currentPendingCount = useMemo(
    () =>
      selectedContact
        ? pendingItems.filter(
            (item) => item.contact_id === selectedContact.contact_id,
          ).length
        : 0,
    [pendingItems, selectedContact],
  )

  const isGlobalPending = appPage === 'pending'
  const isOperations = appPage === 'operations'
  const isGlobalPage = isGlobalPending || isOperations

  const selectableStylePresets = useMemo(
    () => stylePresets.filter((preset) => preset.id !== 'style:balanced'),
    [stylePresets],
  )

  const showNotice = (message, type = 'success') => {
    setNotice({ message, type })
    window.setTimeout(() => setNotice(null), 3200)
  }

  const navigateTo = (path) => {
    if (window.location.pathname !== path) {
      window.history.pushState({}, '', path)
    }
    setAppPage(
      path === GLOBAL_PENDING_PATH
        ? 'pending'
        : path === OPERATIONS_PATH
          ? 'operations'
          : 'workspace',
    )
  }

  const openGlobalPending = () => {
    navigateTo(GLOBAL_PENDING_PATH)
    setMobileSidebar(false)
  }

  const openOperations = () => {
    navigateTo(OPERATIONS_PATH)
    setMobileSidebar(false)
  }

  const openContactWorkspace = (contactId, mode = 'draft') => {
    if (!contacts.some((contact) => contact.contact_id === contactId)) {
      showNotice('该待确认项对应的联系人已不在工作台中', 'error')
      return
    }
    setSelectedId(contactId)
    setWorkspaceMode(mode)
    navigateTo('/')
    setMobileSidebar(false)
  }

  const refreshStats = async () => {
    const nextStats = await api('/api/stats')
    setStats(nextStats)
  }

  useEffect(() => {
    const handlePopState = () => setAppPage(getAppPage())
    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  useEffect(() => {
    const cached = readBootstrapCache()
    const applyBootstrap = (data) => {
      setContacts(data.contacts)
      setSkills(data.skills)
      setStats(data.stats)
      setSettings(data.settings)
      setSelfSkill(data.selfSkill)
      setGirlsChatStyle(data.girlsChatStyle)
      setStylePresets(data.stylePresets)
      setWechatStatus(data.wechatStatus)
      setSelectedId((current) => {
        const preferred = current || data.selectedId
        return data.contacts.some((item) => item.contact_id === preferred)
          ? preferred
          : data.contacts[0]?.contact_id || ''
      })
    }

    async function bootstrap() {
      if (!cached) setBusy('bootstrap')
      try {
        const [
          nextContacts,
          nextSkills,
          nextStats,
          nextSettings,
          nextSelfSkill,
          nextStylePresets,
          nextGirlsChatStyle,
          nextWechatStatus,
        ] =
          await Promise.all([
            api('/api/contacts'),
            api('/api/skills'),
            api('/api/stats'),
            api('/api/settings'),
            api('/api/self-skill'),
            api('/api/style-presets'),
            api('/api/self-skill/girls-chat-style'),
            api('/api/wechat/status'),
          ])
        applyBootstrap({
          contacts: nextContacts,
          skills: nextSkills,
          stats: nextStats,
          settings: nextSettings,
          selfSkill: nextSelfSkill,
          girlsChatStyle: nextGirlsChatStyle,
          stylePresets: nextStylePresets,
          wechatStatus: nextWechatStatus,
          selectedId: cached?.data?.selectedId || '',
        })
      } catch (error) {
        showNotice(error.message, 'error')
      } finally {
        setBusy('')
      }
    }

    if (cached) {
      applyBootstrap(cached.data)
      if (Date.now() - cached.savedAt < BOOTSTRAP_CACHE_TTL_MS) return
    }
    bootstrap()
  }, [])

  useEffect(() => {
    if (
      !stats ||
      !settings ||
      !selfSkill ||
      !girlsChatStyle ||
      !wechatStatus
    ) {
      return
    }
    writeBootstrapCache({
      contacts,
      skills,
      stats,
      settings,
      selfSkill,
      girlsChatStyle,
      stylePresets,
      wechatStatus,
      selectedId,
    })
  }, [
    contacts,
    girlsChatStyle,
    selectedId,
    selfSkill,
    settings,
    skills,
    stats,
    stylePresets,
    wechatStatus,
  ])

  useEffect(() => {
    const checkPendingRisk = async () => {
      try {
        const pending = await api('/api/automation/pending')
        setPendingCount(pending.length)
        setPendingItems(pending)
        setPendingDrafts((drafts) => ({
          ...Object.fromEntries(
            pending.map((item) => [item.id, item.candidate || '']),
          ),
          ...drafts,
        }))
        const currentIds = new Set(
          pending
            .filter((item) => item.risk?.level === 'L1')
            .map((item) => item.id),
        )
        if (lastPendingL1Ids.current) {
          const newIds = [...currentIds].filter(
            (id) => !lastPendingL1Ids.current.has(id),
          )
          if (newIds.length > 0) {
            const latest = pending.find((item) => item.id === newIds[0])
            const options =
              latest?.candidate_options?.length > 0
                ? latest.candidate_options
                : [latest?.candidate].filter(Boolean)
            setL1Prompt(latest)
            setL1PromptText(options[0] || '')
            showNotice(
              `检测到 L1 风险消息：${latest?.display_name || '当前会话'}，候选回复已生成，请确认后发送。`,
              'error',
            )
          }
        }
        lastPendingL1Ids.current = currentIds
      } catch {
        // The automation window displays the detailed error when opened.
      }
    }

    checkPendingRisk()
    const timer = window.setInterval(checkPendingRisk, 5000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    setResult(null)
    setSelectedCandidate(-1)
    setFinalText('')
    const savedStyle = contacts.find(
      (item) => item.contact_id === selectedId,
    )?.style_preset_id
    setActiveStylePresetId(
      savedStyle?.startsWith('style:') ? savedStyle : 'style:balanced',
    )
  }, [selectedId, contacts])

  useEffect(() => {
    let active = true
    if (!selectedContact) {
      setContactAutomationSettings(null)
      return () => {
        active = false
      }
    }
    api(
      `/api/automation/contact-settings/${encodeURIComponent(
        selectedContact.contact_id,
      )}`,
    )
      .then((payload) => {
        if (active) setContactAutomationSettings(payload.settings)
      })
      .catch((error) => {
        if (active) showNotice(error.message, 'error')
      })
    return () => {
      active = false
    }
  }, [selectedContact])

  const generate = async () => {
    if (!selectedContact || !conversation.trim()) return
    setBusy('generate')
    try {
      const payload = await api('/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contact_id: selectedContact.contact_id,
          conversation: conversation.trim(),
          style_preset_id: activeStylePresetId,
        }),
      })
      setResult(payload)
      setSelectedCandidate(payload.candidates.length ? 0 : -1)
      setFinalText(payload.candidates[0]?.text || '')
    } catch (error) {
      showNotice(error.message, 'error')
    } finally {
      setBusy('')
    }
  }

  const saveContactStylePreset = async (stylePresetId) => {
    if (
      !selectedContact ||
      stylePresetId === activeStylePresetId ||
      styleSaving
    ) {
      return
    }
    setStyleSaving(true)
    try {
      const savedContact = await api(
        `/api/contacts/${encodeURIComponent(selectedContact.contact_id)}/style`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            style_preset_id: stylePresetId,
          }),
        },
      )
      setContacts((current) =>
        current.map((item) =>
          item.contact_id === savedContact.contact_id ? savedContact : item,
        ),
      )
      const presetName =
        stylePresets.find((preset) => preset.id === stylePresetId)?.name ||
        '自然均衡'
      showNotice(`已为“${savedContact.display_name}”保存${presetName}`)
    } catch (error) {
      showNotice(error.message, 'error')
    } finally {
      setStyleSaving(false)
    }
  }

  const chooseCandidate = (candidate, index) => {
    setSelectedCandidate(index)
    setFinalText(candidate.text)
  }

  const copyDraft = async () => {
    if (!finalText.trim()) return
    await navigator.clipboard.writeText(finalText)
    showNotice('草稿已复制，可回到微信自行发送')
  }

  const saveFeedback = async () => {
    if (!selectedContact || !finalText.trim()) return
    setBusy('feedback')
    try {
      await api('/api/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contact_id: selectedContact.contact_id,
          conversation,
          selected_text: result?.candidates[selectedCandidate]?.text || '',
          final_text: finalText.trim(),
          scene: result?.scene || 'daily',
        }),
      })
      await refreshStats()
      showNotice('已记住这次最终表达')
    } catch (error) {
      showNotice(error.message, 'error')
    } finally {
      setBusy('')
    }
  }

  const distill = async () => {
    setBusy('distill')
    try {
      const profile = await api('/api/self-skill/distill', { method: 'POST' })
      await refreshStats()
      setSelfSkill(await api('/api/self-skill'))
      showNotice(profile.summary)
    } catch (error) {
      showNotice(error.message, 'error')
    } finally {
      setBusy('')
    }
  }

  const distillGirlsChatStyle = async () => {
    setBusy('girls-style')
    try {
      const distilled = await api('/api/self-skill/girls-chat-style/distill', {
        method: 'POST',
      })
      setGirlsChatStyle(await api('/api/self-skill/girls-chat-style'))
      setStylePresets(await api('/api/style-presets'))
      showNotice(distilled.summary)
    } catch (error) {
      showNotice(error.message, 'error')
    } finally {
      setBusy('')
    }
  }

  const removeContact = async (contact = selectedContact) => {
    if (!contact || contact.is_demo) return
    if (!window.confirm(`确认删除联系人“${contact.display_name}”？`)) return
    try {
      await api(`/api/contacts/${encodeURIComponent(contact.contact_id)}`, {
        method: 'DELETE',
      })
      const remaining = contacts.filter(
        (item) => item.contact_id !== contact.contact_id,
      )
      setContacts(remaining)
      if (selectedId === contact.contact_id) {
        setSelectedId(remaining[0]?.contact_id || '')
      }
      showNotice('联系人已删除')
    } catch (error) {
      showNotice(error.message, 'error')
    }
  }

  const runAutomationOnce = async () => {
    if (!selectedContact) return
    setBusy('automation')
    try {
      const params = new URLSearchParams({ contact_id: selectedContact.contact_id })
      const result = await api(`/api/automation/run-once?${params}`, { method: 'POST' })
      if (result.skipped === 'cycle_already_running') {
        showNotice('后台检查仍在进行，请稍后再试', 'error')
        return
      }
      const actions = result.actions || []
      setContactCheckActions(actions)
      const pending = await api('/api/automation/pending')
      setPendingCount(pending.length)
      setPendingItems(pending)
      const action = actions[0]
      showNotice(
        summarizeContactCheck(selectedContact, actions),
        action?.action === 'read_error' || action?.action === 'send_unverified'
          ? 'error'
          : 'success',
      )
    } catch (error) {
      showNotice(error.message, 'error')
    } finally {
      setBusy('')
    }
  }

  const confirmL1Prompt = async () => {
    if (!l1Prompt || !l1PromptText.trim()) return
    setBusy('l1-confirm')
    try {
      await api(`/api/automation/confirm/${encodeURIComponent(l1Prompt.id)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: l1PromptText.trim() }),
      })
      setL1Prompt(null)
      setL1PromptText('')
      const pending = await api('/api/automation/pending')
      setPendingCount(pending.length)
      setPendingItems(pending)
      showNotice('L1 回复已确认并发送')
    } catch (error) {
      showNotice(error.message, 'error')
    } finally {
      setBusy('')
    }
  }

  const confirmWorkspacePending = async (item) => {
    const text = (pendingDrafts[item.id] || item.candidate || '').trim()
    const files = pendingAttachments[item.id] || []
    const quote = Boolean(item.quote_preview) && (quoteEnabled[item.id] ?? true)
    const at =
      (item.at_targets || []).length > 0 && (atEnabled[item.id] ?? true)
    if (!text && files.length === 0) return
    setBusy(`confirm:${item.id}`)
    try {
      await confirmPendingSend(item, text, files, quote, at)
      const pending = await api('/api/automation/pending')
      setPendingCount(pending.length)
      setPendingItems(pending)
      setPendingAttachments((current) => {
        const next = { ...current }
        delete next[item.id]
        return next
      })
      showNotice('已确认并交给发送执行器')
    } catch (error) {
      showNotice(error.message, 'error')
    } finally {
      setBusy('')
    }
  }

  const discardWorkspacePending = async (item) => {
    if (!window.confirm(`放弃发送给“${item.display_name}”的这条候选回复？`)) return
    setBusy(`discard:${item.id}`)
    try {
      await api(`/api/automation/pending/${encodeURIComponent(item.id)}`, {
        method: 'DELETE',
      })
      const pending = await api('/api/automation/pending')
      setPendingCount(pending.length)
      setPendingItems(pending)
      showNotice('已放弃该条待确认回复')
    } catch (error) {
      showNotice(error.message, 'error')
    } finally {
      setBusy('')
    }
  }

  const updateContactAutomationSetting = async (key, value) => {
    if (!selectedContact || !contactAutomationSettings) return
    const next = { ...contactAutomationSettings, [key]: value }
    if (key === 'dry_run' && value === false) {
      if (!next.real_send_acknowledged) {
        showNotice('请先勾选该联系人的真实发送确认', 'error')
        return
      }
      if (
        !window.confirm(
          `关闭“${selectedContact.display_name}”的 Dry-run 后，该联系人收到 L0 新消息时可能会自动发送。确认继续？`,
        )
      ) {
        return
      }
    }
    setBusy('contact-automation-settings')
    try {
      const payload = await api(
        `/api/automation/contact-settings/${encodeURIComponent(
          selectedContact.contact_id,
        )}`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(next),
        },
      )
      setContactAutomationSettings(payload.settings)
      showNotice(`已更新“${selectedContact.display_name}”的自动回复设置`)
    } catch (error) {
      showNotice(error.message, 'error')
    } finally {
      setBusy('')
    }
  }

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileSidebar ? 'sidebar-open' : ''}`}>
        <div className="brand">
          <div className="brand-mark">
            <MessageCircle size={21} />
          </div>
          <div>
            <strong>关系助手</strong>
            <span>本地草稿工作台</span>
          </div>
          <IconButton
            label="关闭联系人列表"
            className="sidebar-close"
            onClick={() => setMobileSidebar(false)}
          >
            <X size={18} />
          </IconButton>
        </div>

        <nav className="sidebar-nav" aria-label="主导航">
          <button
            type="button"
            className={!isGlobalPage ? 'active' : ''}
            onClick={() => navigateTo('/')}
          >
            <MessageCircle size={17} />
            会话工作台
          </button>
          <button
            type="button"
            className={isGlobalPending ? 'active' : ''}
            onClick={openGlobalPending}
          >
            <ShieldCheck size={17} />
            待确认
            {pendingCount > 0 && <span className="nav-badge">{pendingCount}</span>}
          </button>
          <button
            type="button"
            className={isOperations ? 'active' : ''}
            onClick={openOperations}
          >
            <Activity size={17} />
            运行记录
          </button>
        </nav>

        {!isGlobalPage && (
          <>
            <div className="sidebar-heading">
              <span>联系人</span>
              <IconButton label="添加联系人" onClick={() => setModal('contact')}>
                <Plus size={17} />
              </IconButton>
            </div>

            <nav className="contact-list" aria-label="联系人">
              {contacts.map((contact) => {
                const meta = relationshipMeta[contact.relationship]
                const RelationIcon = meta.icon
                return (
                  <div className="contact-row" key={contact.contact_id}>
                    <button
                      type="button"
                      className={`contact-item ${
                        selectedId === contact.contact_id ? 'active' : ''
                      }`}
                      onClick={() => {
                        openContactWorkspace(contact.contact_id, 'draft')
                      }}
                    >
                      <span
                        className="contact-avatar"
                        style={{ '--contact-color': meta.color }}
                      >
                        {contact.display_name.slice(0, 1)}
                      </span>
                      <span className="contact-copy">
                        <strong>{contact.display_name}</strong>
                        <small>
                          <RelationIcon size={13} />
                          {meta.label}
                        </small>
                      </span>
                      {contact.is_demo && <span className="demo-dot">示例</span>}
                    </button>
                    <div className="contact-actions">
                      <button
                        type="button"
                        className="contact-action contact-edit"
                        aria-label={`编辑关系 ${contact.display_name}`}
                        onClick={() => {
                          setSelectedId(contact.contact_id)
                          setModal('edit-contact')
                        }}
                      >
                        <Pencil size={13} />
                      </button>
                      {!contact.is_demo && (
                        <button
                          type="button"
                          className="contact-action contact-delete"
                          aria-label={`删除联系人 ${contact.display_name}`}
                          onClick={() => removeContact(contact)}
                        >
                          <Trash2 size={13} />
                        </button>
                      )}
                    </div>
                  </div>
                )
              })}
            </nav>
          </>
        )}

        <div className="sidebar-footer">
          <ShieldCheck size={17} />
          <span>高可靠 L0 回复可自动发送，其他回复进入人工确认队列</span>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="contact-title">
            <IconButton
              label="打开联系人列表"
              className="mobile-menu"
              onClick={() => setMobileSidebar(true)}
            >
              <Users size={19} />
            </IconButton>
            <div>
              <div className="title-line">
                <h1>
                  {isOperations
                    ? '运行记录中心'
                    : isGlobalPending
                      ? '全部待确认'
                    : selectedContact?.display_name || '选择联系人'}
                </h1>
                {!isGlobalPage && selectedContact && (
                  <span
                    className="relationship-tag"
                    style={{
                      '--tag-color':
                        relationshipMeta[selectedContact.relationship].color,
                    }}
                  >
                    {relationshipMeta[selectedContact.relationship].label}
                  </span>
                )}
              </div>
              <p>
                {isOperations
                  ? '查看 Agent 调用、发送验证、错误详情和模型运行状态'
                  : isGlobalPending
                    ? '跨会话统一处理需要人工确认的回复'
                  : selectedSkill?.description || '建立联系人后开始生成草稿'}
              </p>
            </div>
          </div>
          <div className="topbar-actions">
            <button
              type="button"
              className={`connection-button ${
                wechatStatus?.reader?.ready ? 'connected' : ''
              }`}
              onClick={() => setModal('wechat')}
            >
              <Database size={16} />
              {wechatStatus?.reader?.ready
                ? '微信数据与自动回复'
                : '微信数据未连接'}
            </button>
            {!isGlobalPage && selectedContact && (
              <IconButton
                label="编辑联系人"
                onClick={() => setModal('edit-contact')}
              >
                <Pencil size={18} />
              </IconButton>
            )}
            {!isGlobalPage && selectedContact && !selectedContact.is_demo && (
              <IconButton label="删除联系人" onClick={removeContact}>
                <Trash2 size={18} />
              </IconButton>
            )}
            <button
              type="button"
              className="button secondary"
              onClick={() => setModal('import')}
              disabled={!selectedContact || isGlobalPage}
            >
              <Upload size={17} />
              导入记录
            </button>
            <IconButton label="模型设置" onClick={() => setModal('settings')}>
              <Settings size={18} />
            </IconButton>
          </div>
        </header>

        {!isGlobalPage && <nav className="workspace-nav" aria-label="工作区" role="tablist">
          <button
            type="button"
            className={workspaceMode === 'draft' ? 'active' : ''}
            onClick={() => setWorkspaceMode('draft')}
          >
            <MessageCircle size={16} />
            手动生成
          </button>
          <button
            type="button"
            className={workspaceMode === 'pending' ? 'active' : ''}
            onClick={() => setWorkspaceMode('pending')}
          >
            <ShieldCheck size={16} />
            待确认
            {currentPendingCount > 0 && <span>{currentPendingCount}</span>}
          </button>
        </nav>}

        {isOperations ? (
          <OperationsPage
            api={api}
            contacts={contacts}
            onOpenContact={(contactId) => openContactWorkspace(contactId, 'draft')}
            onOpenPending={openGlobalPending}
            onOpenWechat={() => setModal('wechat')}
          />
        ) : isGlobalPending ? (
          <PendingWorkbench
            pending={pendingItems}
            view="all"
            pendingDrafts={pendingDrafts}
            setPendingDrafts={setPendingDrafts}
            attachmentFiles={pendingAttachments}
            onAttachmentsChange={(id, files) =>
              setPendingAttachments((current) => ({ ...current, [id]: files }))
            }
            quoteEnabled={quoteEnabled}
            onQuoteChange={(id, enabled) =>
              setQuoteEnabled((current) => ({ ...current, [id]: enabled }))
            }
            atEnabled={atEnabled}
            onAtChange={(id, enabled) =>
              setAtEnabled((current) => ({ ...current, [id]: enabled }))
            }
            working={busy}
            onConfirm={confirmWorkspacePending}
            onDiscard={discardWorkspacePending}
            onOpenContact={(contactId) => openContactWorkspace(contactId, 'pending')}
            canOpenContact={(contactId) =>
              contacts.some((contact) => contact.contact_id === contactId)
            }
          />
        ) : workspaceMode === 'pending' ? (
          <PendingWorkbench
            pending={pendingItems}
            selectedContact={selectedContact}
            view="current"
            pendingDrafts={pendingDrafts}
            setPendingDrafts={setPendingDrafts}
            attachmentFiles={pendingAttachments}
            onAttachmentsChange={(id, files) =>
              setPendingAttachments((current) => ({ ...current, [id]: files }))
            }
            quoteEnabled={quoteEnabled}
            onQuoteChange={(id, enabled) =>
              setQuoteEnabled((current) => ({ ...current, [id]: enabled }))
            }
            atEnabled={atEnabled}
            onAtChange={(id, enabled) =>
              setAtEnabled((current) => ({ ...current, [id]: enabled }))
            }
            working={busy}
            onConfirm={confirmWorkspacePending}
            onDiscard={discardWorkspacePending}
            onOpenAll={openGlobalPending}
          />
        ) : (
          <>
            <div className="workspace">
          <section className="conversation-panel">
            <div className="section-heading">
              <div>
                <span className="eyebrow">手动草稿</span>
                <h2>贴入对话，生成下一句</h2>
              </div>
              <span
                className={`automation-badge ${
                  contactAutomationSettings?.memory_sync_enabled
                    ? 'running'
                    : ''
                }`}
              >
                {selectedContact ? '基于当前联系人' : '先选择联系人'}
              </span>
            </div>

            <details className="automation-details">
              <summary>
                <span>
                  <span className="eyebrow">自动化与记忆设置</span>
                  <strong>
                    {contactAutomationSettings?.enabled
                      ? '已开启监听'
                      : '仅手动生成草稿'}
                  </strong>
                </span>
                <span className="automation-summary-meta">
                  {formatAutoSendMode(
                    contactAutomationSettings,
                    wechatStatus,
                  )}
                  <ChevronDown size={16} aria-hidden="true" />
                </span>
              </summary>

              <div className="automation-overview">
              <div>
                <span>数据库读取</span>
                <strong>
                  {wechatStatus?.reader?.ready ? '可用' : '等待连接'}
                </strong>
              </div>
              <div>
                <span>持续记忆</span>
                <strong>
                  {contactAutomationSettings?.memory_sync_enabled
                    ? '自动更新'
                    : '已关闭'}
                </strong>
              </div>
              <div>
                <span>发送模式</span>
                <strong>
                  {formatAutoSendMode(
                    contactAutomationSettings,
                    wechatStatus,
                  )}
                </strong>
              </div>
              <div>
                <span>白名单</span>
                <strong>
                  {selectedContact?.display_name || '未选择联系人'}
                </strong>
              </div>
            </div>

              {selectedContact && contactAutomationSettings && (
              <section className="automation-inline-settings">
                <div className="automation-inline-heading">
                  <div>
                    <strong>自动回复开关</strong>
                    <span>
                      当前联系人：{selectedContact.display_name}，设置只对该会话生效
                    </span>
                  </div>
                  <span
                    className={`automation-quick-state ${
                      contactAutomationSettings.enabled &&
                      !contactAutomationSettings.dry_run
                        ? 'active'
                        : ''
                    }`}
                  >
                    {contactAutomationSettings.enabled &&
                    !contactAutomationSettings.dry_run
                      ? '可发送'
                      : '仅生成候选'}
                  </span>
                </div>
                <div className="automation-inline-controls">
                  <label className="quick-toggle">
                    <span>
                      <strong>持续记忆</strong>
                      <small>读取该联系人的新记录并更新记忆</small>
                    </span>
                    <input
                      type="checkbox"
                      checked={contactAutomationSettings.memory_sync_enabled}
                      onChange={(event) =>
                        updateContactAutomationSetting(
                          'memory_sync_enabled',
                          event.target.checked,
                        )
                      }
                      aria-label="持续记忆"
                    />
                  </label>
                  <label className="quick-toggle">
                    <span>
                      <strong>自动监听</strong>
                      <small>发现白名单联系人的新消息</small>
                    </span>
                    <input
                      type="checkbox"
                      checked={contactAutomationSettings.enabled}
                      onChange={(event) =>
                        updateContactAutomationSetting(
                          'enabled',
                          event.target.checked,
                        )
                      }
                      aria-label="自动监听"
                    />
                  </label>
                  <label className="quick-toggle">
                    <span>
                      <strong>Dry-run</strong>
                      <small>开启时不会发送到微信</small>
                    </span>
                    <input
                      type="checkbox"
                      checked={contactAutomationSettings.dry_run}
                      onChange={(event) =>
                        updateContactAutomationSetting(
                          'dry_run',
                          event.target.checked,
                        )
                      }
                      aria-label="Dry-run"
                    />
                  </label>
                  <label className="quick-toggle">
                    <span>
                      <strong>真实发送确认</strong>
                      <small>关闭 Dry-run 前必须确认</small>
                    </span>
                    <input
                      type="checkbox"
                      checked={contactAutomationSettings.real_send_acknowledged}
                      onChange={(event) =>
                        updateContactAutomationSetting(
                          'real_send_acknowledged',
                          event.target.checked,
                        )
                      }
                      aria-label="真实发送确认"
                    />
                  </label>
                </div>
                <div className="automation-level-settings">
                  <div>
                    <strong>该联系人允许自动发送的风险级别</strong>
                    <span>
                      仅 L0 日常聊天可以自动发送；L1/L2 始终进入人工确认队列，L3 始终拦截。
                    </span>
                  </div>
                  <div className="automation-level-options">
                    {autoSendLevelOptions.map((option) => {
                      const levels =
                        contactAutomationSettings.auto_send_levels || ['L0']
                      return (
                        <label className="level-toggle" key={option.level}>
                          <span>{option.label}</span>
                          <input
                            type="checkbox"
                            checked={levels.includes(option.level)}
                            onChange={(event) => {
                              const next = event.target.checked
                                ? [...new Set([...levels, option.level])]
                                : levels.filter(
                                    (level) => level !== option.level,
                                  )
                              updateContactAutomationSetting(
                                'auto_send_levels',
                                next,
                              )
                            }}
                            aria-label={`${option.label}自动发送`}
                          />
                        </label>
                      )
                    })}
                  </div>
                </div>
                <div className="automation-inline-note">
                  {contactAutomationSettings.real_send_acknowledged
                    ? `该联系人已确认真实发送权限，当前自动发送级别：${(
                        contactAutomationSettings.auto_send_levels || ['L0']
                      ).join('、')}。L1/L2 始终需要人工确认，L3 始终禁止自动发送。`
                    : '该联系人当前为安全模式：只生成候选，不会自动发到微信。'}
                </div>
              </section>
              )}
            </details>

            <div className="automation-primary-actions">
              <button
                type="button"
                className="button secondary automation-check-button"
                onClick={runAutomationOnce}
                disabled={
                  busy === 'automation' || !wechatStatus?.reader?.ready
                }
              >
                {busy === 'automation' ? (
                  <LoaderCircle className="spin" size={18} />
                ) : (
                  <RefreshCw size={18} />
                )}
                立即检查未回复消息
              </button>
            </div>

            {contactCheckActions.length > 0 && (
              <div className="automation-inline-note" role="status">
                <strong>本次检查结果：</strong>{' '}
                {summarizeContactCheck(selectedContact, contactCheckActions)}
              </div>
            )}

            <textarea
              value={conversation}
              onChange={(event) => setConversation(event.target.value)}
              placeholder={'粘贴最近几轮对话，例如：\n对方：今天有点累\n我：怎么啦？'}
              aria-label="当前聊天内容"
              maxLength={12000}
            />

            <label className="style-preset-field">
              <div className="style-preset-heading">
                <div>
                  <strong>{'\u5f53\u524d\u8054\u7cfb\u4eba\u7684\u8868\u8fbe\u98ce\u683c'}</strong>
                  <small>{'\u4ece\u5168\u90e8\u5fae\u4fe1\u56de\u590d\u4e2d\u84b8\u998f\u51fa\u7684\u8868\u8fbe\u503e\u5411'}</small>
                </div>
                <span className="style-preset-count">{selectableStylePresets.length + 1} {'\u79cd'}</span>
              </div>
              <div className="style-preset-options">
                <button
                  type="button"
                  className={`style-preset-option ${activeStylePresetId === 'style:balanced' ? 'selected' : ''}`}
                  onClick={() => saveContactStylePreset('style:balanced')}
                  disabled={styleSaving}
                >
                  <span>自然均衡</span>
                  <small>从全量聊天记录提取的默认表达类型</small>
                </button>
                {selectableStylePresets.map((preset) => (
                  <button
                    type="button"
                    className={`style-preset-option ${activeStylePresetId === preset.id ? 'selected' : ''}`}
                    onClick={() => saveContactStylePreset(preset.id)}
                    disabled={styleSaving}
                    key={preset.id}
                  >
                    <span>{preset.name}</span>
                    <small>{preset.description || preset.style_rules?.[0]} · {preset.sample_count || 0} {'\u6761\u6837\u672c'}</small>
                  </button>
                ))}
              </div>
            </label>

            <div className="composer-footer">
              <span>{conversation.length.toLocaleString()} / 12,000</span>
              <button
                type="button"
                className="button primary"
                onClick={generate}
                disabled={
                  !selectedContact ||
                  !conversation.trim() ||
                  busy === 'generate'
                }
              >
                {busy === 'generate' ? (
                  <LoaderCircle className="spin" size={18} />
                ) : (
                  <Sparkles size={18} />
                )}
                生成三个草稿
              </button>
            </div>

            {selectedContact && (
              <button
                type="button"
                className="contact-context"
                onClick={() => setModal('edit-contact')}
              >
                <div>
                  <UserRound size={16} />
                  <span>称呼</span>
                  <strong>{selectedContact.preferred_address || '未设置'}</strong>
                </div>
                <div>
                  <MessageCircle size={16} />
                  <span>长度</span>
                  <strong>
                    {lengthLabels[selectedContact.message_length]}
                  </strong>
                </div>
                <div>
                  <Smile size={16} />
                  <span>表情</span>
                  <strong>{emojiLabels[selectedContact.emoji_level]}</strong>
                </div>
                <div>
                  <Sparkles size={16} />
                  <span>幽默</span>
                  <strong>{humorLabels[selectedContact.humor_level]}</strong>
                </div>
                <div>
                  <ShieldCheck size={16} />
                  <span>边界</span>
                  <strong>{selectedContact.boundaries.length} 条</strong>
                </div>
              </button>
            )}
          </section>

          <section className="draft-panel">
            <div className="section-heading">
              <div>
                <span className="eyebrow">候选回复</span>
                <h2>选一句，再改成你的话</h2>
              </div>
              {result && (
                <div className="result-tags">
                  <span className="scene-badge">
                    {sceneLabels[result.scene] || result.scene}
                  </span>
                  <span className={`risk-badge risk-${result.risk.level}`}>
                    {result.risk.level} · {result.risk.label}
                  </span>
                </div>
              )}
            </div>

            {!result && (
              <div className="empty-state">
                <div className="empty-icon">
                  <Sparkles size={24} />
                </div>
                <strong>等待一段对话</strong>
                <p>系统会结合关系、场景和历史表达给出三个不同语气的草稿。</p>
              </div>
            )}

            {result && (() => {
              const pipeline = summarizeAgentPipeline(result)
              if (!pipeline) return null
              return (
                <details className="agent-details">
                  <summary>
                    <span>
                      <span className="eyebrow">生成详情</span>
                      <strong>查看回复生成过程</strong>
                    </span>
                    <ChevronDown size={17} aria-hidden="true" />
                  </summary>
                  <div className="agent-pipeline" aria-label="多角色生成过程">
                  <div className="agent-pipeline-header">
                    <div>
                      <span className="eyebrow">Agent 过程</span>
                      <strong>
                        {pipeline.decisionMeta.label}
                        {pipeline.writerPasses > 1 ? ` · 写手重写 ${pipeline.writerPasses - 1} 次` : ''}
                      </strong>
                    </div>
                    <span className={`review-badge review-${pipeline.decisionMeta.tone}`}>
                      {pipeline.decisionMeta.label}
                    </span>
                  </div>
                  <AgentFlowGraph pipeline={pipeline} />
                  <ol className="agent-steps">
                    {pipeline.steps.map((step, index) => (
                      <li
                        key={`${step.role}-${index}-${step.status}`}
                        className={`agent-step status-${step.status || 'ok'}`}
                      >
                        <span className="agent-step-index">{index + 1}</span>
                        <div>
                          <strong>{roleLabels[step.role] || step.role}</strong>
                          <p>{step.summary || step.status}</p>
                        </div>
                        <span className="agent-step-meta">
                          {typeof step.duration_ms === 'number' ? `${step.duration_ms}ms` : ''}
                        </span>
                      </li>
                    ))}
                  </ol>
                  {pipeline.issues.length > 0 && (
                    <div className="review-issues">
                      <span>审核问题</span>
                      <ul>
                        {pipeline.issues.slice(0, 4).map((issue) => (
                          <li key={issue}>{issue}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  </div>
                </details>
              )
            })()}

            {result?.warning && (
              <div className={`warning risk-${result.risk.level}`}>
                <ShieldCheck size={18} />
                <span>{result.warning}</span>
              </div>
            )}

            {result?.candidates.length > 0 && (
              <>
                <div className="candidate-list">
                  {result.candidates.map((candidate, index) => (
                    <button
                      type="button"
                      className={`candidate ${
                        selectedCandidate === index ? 'selected' : ''
                      }`}
                      key={`${candidate.label}-${candidate.text}`}
                      onClick={() => chooseCandidate(candidate, index)}
                    >
                      <span className="candidate-label">{candidate.label}</span>
                      <span>{candidate.text}</span>
                      <span className="selection-mark">
                        {selectedCandidate === index && <Check size={15} />}
                      </span>
                    </button>
                  ))}
                </div>

                <div className="editor">
                  <label htmlFor="final-draft">最终草稿</label>
                  <textarea
                    id="final-draft"
                    value={finalText}
                    onChange={(event) => setFinalText(event.target.value)}
                  />
                  <div className="editor-actions">
                    <button
                      type="button"
                      className="button secondary"
                      onClick={saveFeedback}
                      disabled={!finalText.trim() || busy === 'feedback'}
                    >
                      {busy === 'feedback' ? (
                        <LoaderCircle className="spin" size={17} />
                      ) : (
                        <Database size={17} />
                      )}
                      记住这次表达
                    </button>
                    <button
                      type="button"
                      className="button primary"
                      onClick={copyDraft}
                      disabled={!finalText.trim()}
                    >
                      <Clipboard size={17} />
                      复制草稿
                    </button>
                  </div>
                </div>
              </>
            )}

            {result && result.candidates.length === 0 && (
              <div className="blocked-state">
                <ShieldCheck size={28} />
                <strong>这次需要你亲自判断</strong>
                <p>高风险内容不会生成可直接发送的回复。</p>
              </div>
            )}
          </section>
        </div>

        <section className="insight-bar" aria-label="本地表达库统计">
          <div className="insight-summary">
            <Database size={18} />
            <div>
              <span>本地表达库</span>
              <strong>
                {selfSkill?.ready
                  ? `个人 Skill · ${selfSkill.meta?.sample_count || 0} 条`
                  : `${stats?.records || 0} 条真实样本`}
              </strong>
            </div>
          </div>
          <div className="insight-metrics">
            <span>
              已反馈 <strong>{stats?.feedback || 0}</strong>
            </span>
            <span>
              画像样本 <strong>{stats?.profile?.sample_count || 0}</strong>
            </span>
          </div>
          <p>
            {selfSkill?.ready
              ? 'Self Memory 与 Persona 已生成，模型回复会自动加载。'
              : '导入真实聊天记录后，可以蒸馏成你的个人回复 Skill。'}
          </p>
          <button
            type="button"
            className="button secondary"
            onClick={distill}
            disabled={busy === 'distill'}
          >
            {busy === 'distill' ? (
              <LoaderCircle className="spin" size={17} />
            ) : (
              <RefreshCw size={17} />
            )}
            {selfSkill?.ready ? '重新蒸馏 Skill' : '蒸馏个人 Skill'}
          </button>
          <div className="insight-style-note">
            <span>
              {'\u5973\u751f\u804a\u5929\u98ce\u683c'}{' '}
              <strong>
                {girlsChatStyle?.meta?.sample_count || 0}{' '}
                {'\u6761\u6837\u672c'}
              </strong>
            </span>
            <small>
              {girlsChatStyle?.meta?.candidate_count || 0}{' '}
              {'\u4e2a\u665a\u5b89\u4e92\u9053\u79c1\u804a\u5019\u9009'}
            </small>
            <small>
              {girlsChatStyle?.meta?.coverage?.private_session_count || 0}{' '}
              {'\u4e2a\u53ef\u8bfb\u79c1\u804a\u4e2d\u7b5b\u51fa'}{' '}
              {girlsChatStyle?.meta?.coverage?.candidate_session_rate || 0}%
            </small>
          </div>
          <button
            type="button"
            className="button secondary"
            onClick={distillGirlsChatStyle}
            disabled={busy === 'girls-style'}
          >
            {busy === 'girls-style' ? (
              <LoaderCircle className="spin" size={17} />
            ) : (
              <Heart size={17} />
            )}
            {'\u84b8\u998f\u5973\u751f\u804a\u5929\u98ce\u683c'}
          </button>
            </section>
          </>
        )}
      </main>

      {l1Prompt && (
        <Modal
          title={`L1 消息需要确认 · ${l1Prompt.display_name || '当前会话'}`}
          subtitle="系统已生成多个候选回复，请选择、修改或自行输入后发送"
          onClose={() => setL1Prompt(null)}
        >
          <div className="modal-body l1-prompt-body">
            <div className="l1-prompt-warning">
              <ShieldCheck size={18} />
              <span>
                这条消息涉及待核实事实或计划，系统不会直接代替你发送。确认发送后，下一条新消息会重新进行风险判定。
              </span>
            </div>

            {l1Prompt.incoming?.length > 0 && (
              <div className="l1-prompt-incoming">
                <span>对方最新消息</span>
                <strong>{l1Prompt.incoming.slice(-1)[0]}</strong>
              </div>
            )}

            <div className="l1-prompt-options">
              <span>选择候选回复</span>
              {(l1Prompt.candidate_options?.length
                ? l1Prompt.candidate_options
                : [l1Prompt.candidate]
              )
                .filter(Boolean)
                .map((option, index) => (
                  <button
                    type="button"
                    className={`l1-option ${
                      l1PromptText === option ? 'selected' : ''
                    }`}
                    key={`${option}-${index}`}
                    onClick={() => setL1PromptText(option)}
                  >
                    <span>{option}</span>
                    {l1PromptText === option && <Check size={16} />}
                  </button>
                ))}
            </div>

            <label className="field l1-custom-reply">
              <span>回复内容（可修改或自行输入）</span>
              <textarea
                value={l1PromptText}
                maxLength={200}
                onChange={(event) => setL1PromptText(event.target.value)}
                placeholder="请输入要发送的回复"
              />
            </label>

            <div className="modal-actions">
              <button
                type="button"
                className="button ghost"
                onClick={() => setL1Prompt(null)}
                disabled={busy === 'l1-confirm'}
              >
                稍后处理
              </button>
              <button
                type="button"
                className="button primary"
                onClick={confirmL1Prompt}
                disabled={busy === 'l1-confirm' || !l1PromptText.trim()}
              >
                {busy === 'l1-confirm' ? (
                  <LoaderCircle className="spin" size={17} />
                ) : (
                  <Send size={17} />
                )}
                确认并发送
              </button>
            </div>
          </div>
        </Modal>
      )}

      {modal === 'import' && selectedContact && (
        <ImportModal
          contact={selectedContact}
          onClose={() => setModal('')}
          onImported={async (count) => {
            await refreshStats()
            setModal('')
            showNotice(`已导入 ${count} 组对话`)
          }}
        />
      )}

      {(modal === 'contact' || modal === 'edit-contact') && (
        <ContactModal
          contact={modal === 'edit-contact' ? selectedContact : null}
          stylePresets={stylePresets}
          onClose={() => setModal('')}
          onSaved={(saved) => {
            setContacts((current) => {
              const exists = current.some(
                (item) => item.contact_id === saved.contact_id,
              )
              if (!exists) return [...current, saved]
              return current.map((item) =>
                item.contact_id === saved.contact_id ? saved : item,
              )
            })
            setSelectedId(saved.contact_id)
            setModal('')
            showNotice(
              modal === 'edit-contact' ? '联系人偏好已更新' : '已添加联系人',
            )
          }}
        />
      )}

      {modal === 'settings' && settings && (
        <SettingsModal
          initial={settings}
          onClose={() => setModal('')}
          onSaved={(nextSettings) => {
            setSettings(nextSettings)
            setModal('')
            showNotice('模型设置已更新')
          }}
        />
      )}

      {modal === 'wechat' && (
        <WeChatModal
          status={wechatStatus}
          contacts={contacts}
          girlsChatStyle={girlsChatStyle}
          onClose={() => setModal('')}
          onRefresh={async () => {
            const nextStatus = await api('/api/wechat/status')
            setWechatStatus(nextStatus)
            return nextStatus
          }}
          onChanged={async () => {
            await refreshStats()
            setSelfSkill(await api('/api/self-skill'))
          }}
          onAddContact={() => setModal('contact')}
          onOpenOperations={() => {
            setModal('')
            openOperations()
          }}
        />
      )}

      {notice && (
        <div className={`toast ${notice.type}`}>
          {notice.type === 'error' ? (
            <X size={17} />
          ) : (
            <Check size={17} />
          )}
          {notice.message}
        </div>
      )}

      {busy === 'bootstrap' && (
        <div className="boot-screen">
          <LoaderCircle className="spin" size={28} />
          <span>正在读取本地关系库…</span>
        </div>
      )}
    </div>
  )
}

function WeChatModal({
  status,
  contacts,
  girlsChatStyle,
  onClose,
  onRefresh,
  onChanged,
  onAddContact,
  onOpenOperations,
}) {
  const [current, setCurrent] = useState(status)
  const [localContacts, setLocalContacts] = useState(contacts)
  const [sessions, setSessions] = useState([])
  const [settings, setSettings] = useState(null)
  const [worker, setWorker] = useState(null)
  const [analysis, setAnalysis] = useState(null)
  const [coverage, setCoverage] = useState(null)
  const [events, setEvents] = useState([])
  const [pending, setPending] = useState([])
  const [pendingDrafts, setPendingDrafts] = useState({})
  const [pendingAttachments, setPendingAttachments] = useState({})
  const [quoteEnabled, setQuoteEnabled] = useState({})
  const [atEnabled, setAtEnabled] = useState({})
  const [refreshing, setRefreshing] = useState(false)
  const [working, setWorking] = useState('')
  const [error, setError] = useState('')
  const [sessionOffset, setSessionOffset] = useState(0)
  const [batchSize, setBatchSize] = useState(20)
  const [messagesPerSession, setMessagesPerSession] = useState(50000)
  const [batchInfo, setBatchInfo] = useState(null)
  const l1Pending = useMemo(
    () => pending.filter((item) => item.risk?.level === 'L1'),
    [pending],
  )

  useEffect(() => {
    setLocalContacts(contacts)
  }, [contacts])

  const loadAutomation = async () => {
    const [
      nextSettings,
      nextWorker,
      nextAnalysis,
      nextCoverage,
      nextEvents,
      nextPending,
    ] =
      await Promise.all([
        api('/api/automation/settings'),
        api('/api/automation/status'),
        api('/api/wechat/analysis'),
        api('/api/wechat/coverage'),
        api('/api/automation/events?limit=8'),
        api('/api/automation/pending'),
      ])
    setSettings(nextSettings)
    setWorker(nextWorker)
    setAnalysis(nextAnalysis)
    setCoverage(nextCoverage)
    setEvents(nextEvents.reverse())
    setPending(nextPending)
    setPendingDrafts((drafts) => ({
      ...Object.fromEntries(
        nextPending.map((item) => [item.id, item.candidate || '']),
      ),
      ...drafts,
    }))
  }

  useEffect(() => {
    loadAutomation().catch((loadError) => setError(loadError.message))
    api('/api/wechat/sessions?limit=500')
      .then((result) =>
        setSessions(
          result.sessions.filter(
            (session) =>
              session.chat_type === 'private' || session.chat_type === 'group',
          ),
        ),
      )
      .catch(() => setSessions([]))
  }, [])

  useEffect(() => {
    const timer = window.setInterval(() => {
      loadAutomation().catch((loadError) => setError(loadError.message))
    }, 5000)
    return () => window.clearInterval(timer)
  }, [])


  const refresh = async () => {
    setRefreshing(true)
    try {
      setCurrent(await onRefresh())
    } finally {
      setRefreshing(false)
    }
  }

  const importAndDistill = async () => {
    setWorking('import')
    setError('')
    try {
      const imported = await api('/api/wechat/import-recent', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_limit: batchSize,
          session_offset: sessionOffset,
          messages_per_session: messagesPerSession,
          include_groups: true,
        }),
      })
      const distilled = await api('/api/self-skill/distill', {
        method: 'POST',
      })
      await loadAutomation()
      await onChanged()
      setBatchInfo(imported.batch)
      setSessionOffset(imported.next_session_offset ?? 0)
      window.alert(
        `本批读取完成：识别 ${imported.recognized_records} 组对话，新增 ${imported.imported} 组；` +
          `当前可读会话 ${imported.coverage.readable_sessions}/${imported.coverage.total_sessions}` +
          `${imported.coverage.failed_count ? `，缺失 ${imported.coverage.failed_count} 个会话` : ''}；` +
          distilled.summary,
      )
    } catch (workError) {
      setError(workError.message)
    } finally {
      setWorking('')
    }
  }

  const saveSettings = async (next) => {
    setWorking('settings')
    setError('')
    try {
      const saved = await api('/api/automation/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(next),
      })
      setSettings(saved)
      await loadAutomation()
      await onChanged()
    } catch (workError) {
      setError(workError.message)
    } finally {
      setWorking('')
    }
  }

  const updateSetting = (key, value) => {
    const next = { ...settings, [key]: value }
    if (key === 'dry_run' && value === false) {
      if (!settings.real_send_acknowledged) {
        setError('请先勾选真实发送确认，再关闭 Dry-run')
        return
      }
      const confirmed = window.confirm(
        '关闭 Dry-run 后，白名单联系人收到 L0 新消息时可能会自动发送。确认继续？',
      )
      if (!confirmed) return
    }
    saveSettings(next)
  }

  const setPaused = async (paused) => {
    setWorking(paused ? 'pause' : 'resume')
    setError('')
    try {
      await api(`/api/automation/${paused ? 'pause' : 'resume'}`, {
        method: 'POST',
      })
      await loadAutomation()
      await onChanged()
    } catch (workError) {
      setError(workError.message)
    } finally {
      setWorking('')
    }
  }

  const resetCursors = async () => {
    if (!window.confirm('确认重置全部联系人游标？下一次检查将重新建立基线。')) return
    setWorking('reset')
    setError('')
    try {
      await api('/api/automation/reset-cursors', { method: 'POST' })
      await loadAutomation()
      await onChanged()
    } catch (workError) {
      setError(workError.message)
    } finally {
      setWorking('')
    }
  }

  const confirmPending = async (item) => {
    const text = (pendingDrafts[item.id] || item.candidate || '').trim()
    const files = pendingAttachments[item.id] || []
    const quote = Boolean(item.quote_preview) && (quoteEnabled[item.id] ?? true)
    const at =
      (item.at_targets || []).length > 0 && (atEnabled[item.id] ?? true)
    if (!text && files.length === 0) return
    setWorking(`confirm:${item.id}`)
    setError('')
    try {
      await confirmPendingSend(item, text, files, quote, at)
      setPendingAttachments((current) => {
        const next = { ...current }
        delete next[item.id]
        return next
      })
      await loadAutomation()
      await onChanged()
    } catch (workError) {
      setError(workError.message)
    } finally {
      setWorking('')
    }
  }

  const discardPending = async (item) => {
    if (!window.confirm(`放弃发送给“${item.display_name}”的这条候选回复？`)) return
    setWorking(`discard:${item.id}`)
    setError('')
    try {
      await api(`/api/automation/pending/${encodeURIComponent(item.id)}`, {
        method: 'DELETE',
      })
      await loadAutomation()
      await onChanged()
    } catch (workError) {
      setError(workError.message)
    } finally {
      setWorking('')
    }
  }

  const toggleContact = (contactId) => {
    const allowed = new Set(settings.allowed_contact_ids)
    if (allowed.has(contactId)) allowed.delete(contactId)
    else allowed.add(contactId)
    saveSettings({
      ...settings,
      allowed_contact_ids: [...allowed],
    })
  }

  const bindSession = async (contact, username) => {
    if (!username) return
    const session = sessions.find((item) => item.username === username)
    setWorking(`bind:${contact.contact_id}`)
    setError('')
    try {
      const saved = await api('/api/contacts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...contact,
          wechat_username: username,
          chat_type: session?.chat_type === 'group' ? 'group' : 'private',
          participant_count: session?.participant_count || null,
        }),
      })
      setLocalContacts((items) =>
        items.map((item) =>
          item.contact_id === saved.contact_id ? saved : item,
        ),
      )
      await onChanged()
    } catch (workError) {
      setError(workError.message)
    } finally {
      setWorking('')
    }
  }

  const runOnce = async () => {
    setWorking('run')
    setError('')
    try {
      await api('/api/automation/run-once', { method: 'POST' })
      await loadAutomation()
      await onChanged()
    } catch (workError) {
      setError(workError.message)
    } finally {
      setWorking('')
    }
  }

  return (
    <Modal
      title="微信自动回复"
      subtitle="直接读取本机微信数据库，生成回复后按风险等级处理"
      onClose={onClose}
      wide
    >
      <div className="modal-body">
        <div className={`wechat-status ${current?.reader?.ready ? 'ready' : ''}`}>
          <div className="wechat-status-icon">
            {current?.reader?.ready ? (
              <Check size={22} />
            ) : (
              <Database size={22} />
            )}
          </div>
          <div>
            <strong>
              {current?.reader?.ready ? '微信聊天数据库可读' : '等待数据库连接'}
            </strong>
            <p>
              {current?.reader?.ready
                ? `已连接 ${current.reader.metadata_cache?.source_db_count || 0} 个数据库文件，读取过程不使用 OCR`
                : current?.reader?.message || current?.message || '未检测到微信。'}
            </p>
          </div>
        </div>

        {l1Pending.length > 0 && (
          <div className="automation-risk-alert" role="status">
            <ShieldCheck size={18} />
            <div>
              <strong>检测到 {l1Pending.length} 条 L1 风险消息</strong>
              <span>
                已生成候选回复，但涉及待核实事实或计划，系统不会自动发送。请到下方“待人工确认”中检查后确认发送。
              </span>
            </div>
          </div>
        )}

        {settings && (
          <section className="automation-quick-settings">
            <div className="automation-quick-heading">
              <div>
                <strong>自动回复开关</strong>
                <span>
                  自动监听负责发现新消息；关闭 Dry-run 后才允许真实发送
                </span>
              </div>
              <span
                className={`automation-quick-state ${
                  settings.enabled && !settings.dry_run ? 'active' : ''
                }`}
              >
                {settings.enabled && !settings.dry_run ? '可发送' : '仅生成候选'}
              </span>
            </div>
            <div className="automation-quick-controls">
              <label className="quick-toggle">
                <span>
                  <strong>自动监听</strong>
                  <small>发现白名单联系人的新消息</small>
                </span>
                <input
                  type="checkbox"
                  checked={settings.enabled}
                  onChange={(event) =>
                    updateSetting('enabled', event.target.checked)
                  }
                  aria-label="自动监听"
                />
              </label>
              <label className="quick-toggle">
                <span>
                  <strong>Dry-run</strong>
                  <small>开启时不会发送到微信</small>
                </span>
                <input
                  type="checkbox"
                  checked={settings.dry_run}
                  onChange={(event) =>
                    updateSetting('dry_run', event.target.checked)
                  }
                  aria-label="Dry-run"
                />
              </label>
            </div>
            <div className="automation-quick-note">
              <ShieldCheck size={16} />
              <span>
                {settings.real_send_acknowledged
                  ? '已确认真实发送权限；仍只对白名单中的 L0 普通聊天自动发送。'
                  : '当前未确认真实发送权限；如需真实发送，请先在下方勾选“真实发送确认”。'}
              </span>
            </div>
          </section>
        )}

        {coverage && (
          <section className="wechat-coverage">
            <div className="coverage-heading">
              <div>
                <strong>读取覆盖情况</strong>
                <span>
                  会话目录总量与数据库可读范围分开统计；失败会话不会计入蒸馏
                </span>
              </div>
              <span className="coverage-rate">
                {coverage.session_coverage_percent}% 会话已读取
              </span>
            </div>
            <div className="coverage-metrics">
              <div>
                <span>全部会话</span>
                <strong>{coverage.total_sessions}</strong>
              </div>
              <div>
                <span>数据库可读</span>
                <strong>{coverage.readable_sessions}</strong>
              </div>
              <div>
                <span>缺失会话</span>
                <strong className={coverage.failed_count ? 'has-warning' : ''}>
                  {coverage.failed_count}
                </strong>
              </div>
              <div>
                <span>已蒸馏回复</span>
                <strong>{coverage.distilled_reply_count}</strong>
              </div>
            </div>
            {girlsChatStyle?.meta?.coverage && (
              <div className="coverage-note">
                <strong>女生风格候选口径</strong>
                <span>
                  已读取的私聊 {girlsChatStyle.meta.coverage.private_session_count} 个，
                  符合“双方 12 小时内互道晚安” {girlsChatStyle.meta.coverage.candidate_session_count} 个，
                  排除 {girlsChatStyle.meta.coverage.excluded_session_count} 个。
                </span>
              </div>
            )}
            {coverage.failed_count > 0 && (
              <details className="coverage-failures">
                <summary>查看 {coverage.failed_count} 个未读取会话</summary>
                <div>
                  {coverage.failed_sessions.map((item) => (
                    <p key={item.username}>
                      <strong>{item.display_name || item.username}</strong>
                      <span>
                        {item.reason && item.reason.includes('Msg_')
                          ? '消息分片中未找到对应 Msg_* 表'
                          : item.reason || '读取失败'}
                      </span>
                    </p>
                  ))}
                </div>
              </details>
            )}
          </section>
        )}

        <div className="wechat-actions">
          <div className="wechat-batch-controls">
            <label>
              <span>每批会话</span>
              <input
                type="number"
                min="1"
                max="50"
                value={batchSize}
                onChange={(event) =>
                  setBatchSize(Number(event.target.value) || 1)
                }
              />
            </label>
            <label>
              <span>每个会话最多消息</span>
              <input
                type="number"
                min="20"
                max="50000"
                step="100"
                value={messagesPerSession}
                onChange={(event) =>
                  setMessagesPerSession(Number(event.target.value) || 20)
                }
              />
            </label>
            <span className="wechat-batch-status">
              {batchInfo
                ? `当前批次 ${batchInfo.session_offset + 1}-${batchInfo.session_end}/${batchInfo.total_sessions}`
                : '尚未开始分批读取'}
            </span>
          </div>
          <button
            type="button"
            className="button primary"
            onClick={importAndDistill}
            disabled={working || !current?.reader?.ready}
          >
            {working === 'import' ? (
              <LoaderCircle className="spin" size={17} />
            ) : (
              <Sparkles size={17} />
            )}
            读取最近聊天并蒸馏
          </button>
          <button
            type="button"
            className="button secondary"
            onClick={runOnce}
            disabled={working || !current?.reader?.ready}
          >
            <RefreshCw size={17} />
            运行一次监听
          </button>
        </div>

        {settings && (
          <section className="automation-settings">
            <div className="setting-row">
              <div>
                <strong>持续更新记忆</strong>
                <span>
                  持续读取白名单联系人的真实微信历史，发现新的完整对话后自动更新个人表达画像；不会发送消息
                </span>
              </div>
              <input
                type="checkbox"
                checked={settings.memory_sync_enabled}
                onChange={(event) =>
                  updateSetting('memory_sync_enabled', event.target.checked)
                }
                aria-label="持续更新记忆"
              />
            </div>
            <div className="setting-row">
              <div>
                <strong>自动监听</strong>
                <span>发现白名单联系人新消息后生成回复；首次运行只记录基线</span>
              </div>
              <input
                type="checkbox"
                checked={settings.enabled}
                onChange={(event) =>
                  updateSetting('enabled', event.target.checked)
                }
                aria-label="自动监听"
              />
            </div>
            <div className="setting-row">
              <div>
                <strong>Dry-run</strong>
                <span>开启时只生成候选并记录事件，不操作微信发送</span>
              </div>
              <input
                type="checkbox"
                checked={settings.dry_run}
                onChange={(event) =>
                  updateSetting('dry_run', event.target.checked)
                }
                aria-label="Dry-run"
              />
            </div>
            <div className="setting-row setting-warning">
              <div>
                <strong>真实发送确认</strong>
                <span>明确确认后，关闭 Dry-run 才能发送；L0 可自动发送，其他等级进入队列。</span>
              </div>
              <input
                type="checkbox"
                checked={settings.real_send_acknowledged}
                onChange={(event) =>
                  updateSetting('real_send_acknowledged', event.target.checked)
                }
                aria-label="真实发送确认"
              />
            </div>

            <div className="automation-controls">
              <button
                type="button"
                className="button secondary"
                onClick={() => setPaused(!worker?.paused)}
                disabled={Boolean(working)}
              >
                {worker?.paused ? <Play size={17} /> : <Pause size={17} />}
                {worker?.paused ? '恢复自动化' : '暂停自动化'}
              </button>
              <button
                type="button"
                className="button ghost"
                onClick={resetCursors}
                disabled={Boolean(working)}
              >
                <RotateCcw size={17} />
                重置全部游标
              </button>
            </div>

            <div className="send-guard">
              <ShieldCheck size={17} />
              <span>
                {worker?.send_guard_ready
                  ? '真实发送保护已满足：L0 高可靠回复可自动发送，其他风险等级仍需人工确认。'
                  : '当前不会直接真实发送：请保持 Dry-run 或完成真实发送确认。'}
              </span>
            </div>

            <PendingConfirmationList
              pending={pending}
              pendingDrafts={pendingDrafts}
              setPendingDrafts={setPendingDrafts}
              attachmentFiles={pendingAttachments}
              onAttachmentsChange={(id, files) =>
                setPendingAttachments((current) => ({ ...current, [id]: files }))
              }
              quoteEnabled={quoteEnabled}
              onQuoteChange={(id, enabled) =>
                setQuoteEnabled((current) => ({ ...current, [id]: enabled }))
              }
              atEnabled={atEnabled}
              onAtChange={(id, enabled) =>
                setAtEnabled((current) => ({ ...current, [id]: enabled }))
              }
              working={working}
              onConfirm={confirmPending}
              onDiscard={discardPending}
              heading="待人工确认"
              emptyText="暂无待确认回复。"
            />

            <div className="whitelist">
              <span>允许自动处理的联系人</span>
              {localContacts.filter((contact) => contact.wechat_username).length ? (
                localContacts
                  .filter((contact) => contact.wechat_username)
                  .map((contact) => (
                    <label key={contact.contact_id}>
                      <input
                        type="checkbox"
                        checked={settings.allowed_contact_ids.includes(
                          contact.contact_id,
                        )}
                        onChange={() => toggleContact(contact.contact_id)}
                      />
                      <span>{contact.display_name}</span>
                      <small>
                        {contact.chat_type === 'group' ? '群聊' : '私聊'}
                        {contact.participant_count
                          ? ` · ${contact.participant_count} 人`
                          : ''}
                        {' · '}
                        {contact.wechat_username}
                      </small>
                    </label>
                  ))
              ) : (
                <p>还没有绑定微信会话，请在下面选择联系人并绑定。</p>
              )}
            </div>

            <div className="session-bindings">
              {localContacts
                .filter((contact) => !contact.wechat_username && !contact.is_demo)
                .map((contact) => (
                  <div className="session-binding" key={contact.contact_id}>
                    <div>
                      <strong>{contact.display_name}</strong>
                      <span>选择对应的微信会话后加入白名单</span>
                    </div>
                    <select
                      defaultValue=""
                      aria-label={`绑定${contact.display_name}的微信会话`}
                      onChange={(event) =>
                        bindSession(contact, event.target.value)
                      }
                      disabled={working === `bind:${contact.contact_id}`}
                    >
                      <option value="">选择微信会话</option>
                      {sessions.map((session) => (
                        <option key={session.username} value={session.username}>
                          {session.display_name}
                          {session.chat_type === 'group'
                            ? ` · 群聊${
                                session.participant_count
                                  ? ` · ${session.participant_count} 人`
                                  : ''
                              }`
                            : ' · 私聊'}
                        </option>
                      ))}
                    </select>
                  </div>
                ))}
              {!localContacts.some(
                (contact) => !contact.wechat_username && !contact.is_demo,
              ) && (
                <div className="session-binding-empty">
                  <p className="form-hint">
                    请先添加一个真实联系人，再绑定对应的微信会话。
                  </p>
                  <button
                    type="button"
                    className="button secondary"
                    onClick={onAddContact}
                  >
                    <Plus size={16} />
                    添加联系人并绑定
                  </button>
                </div>
              )}
              {!sessions.length && (
                <p className="form-hint">
                  当前没有可用的私聊会话，请确认微信已登录并点击“重新检测”。
                </p>
              )}
            </div>
          </section>
        )}

        <div className="automation-metrics">
          <div>
            <span>蒸馏回复</span>
            <strong>{analysis?.reply_count || 0}</strong>
          </div>
          <div>
            <span>中位响应</span>
            <strong>
              {analysis?.median_response_seconds == null
                ? '暂无'
                : `${analysis.median_response_seconds} 秒`}
            </strong>
          </div>
          <div>
            <span>5 分钟内</span>
            <strong>{analysis?.under_5min_rate || 0}%</strong>
          </div>
          <div>
            <span>最近运行</span>
            <strong>{worker?.last_run_at ? '已运行' : '未运行'}</strong>
          </div>
        </div>

        <AutomationFlowGraph events={events} />

        <section className="automation-records-entry">
          <div>
            <span className="eyebrow">运行记录中心</span>
            <strong>查看完整 Agent 调用、失败原因和模型日志</strong>
            <p>当前弹窗保留连接、导入和自动化设置；详细记录统一迁移到独立页面。</p>
          </div>
          <button type="button" className="button secondary" onClick={onOpenOperations}>
            <Activity size={16} />
            打开运行记录中心
          </button>
        </section>

        {events.length > 0 && (
          <div className="automation-events">
            <span>最近事件</span>
            {events.map((event, index) => (
              <div key={`${event.created_at || 'event'}-${index}`}>
                <strong>{event.display_name || '自动监听'}</strong>
                <small>
                  {{
                    baseline: '已建立基线',
                    drafted: '已生成草稿',
                    needs_confirmation: '等待确认',
                    blocked: '已阻止',
                    sent: '已发送',
                    error: '运行错误',
                  }[event.action] || event.action}
                </small>
              </div>
            ))}
          </div>
        )}

        <div className="privacy-note">
          <ShieldCheck size={18} />
          <span>
            聊天内容只在本机用于生成个人 Skill 和回复。自动发送默认关闭，且仅允许对白名单联系人和 L0 普通聊天生效。
          </span>
        </div>

        {error && <p className="form-error">{error}</p>}

        <div className="modal-actions">
          <button type="button" className="button ghost" onClick={onClose}>
            关闭
          </button>
          <button
            type="button"
            className="button primary"
            onClick={refresh}
            disabled={refreshing}
          >
            {refreshing ? (
              <LoaderCircle className="spin" size={17} />
            ) : (
              <RefreshCw size={17} />
            )}
            重新检测
          </button>
        </div>
      </div>
    </Modal>
  )
}

function ContactModal({
  onClose,
  onSaved,
  stylePresets = [],
  contact = null,
}) {
  const isEditing = Boolean(contact?.contact_id)
  const [form, setForm] = useState(() =>
    contact ? { ...emptyContact, ...contact } : emptyContact,
  )
  const [sessions, setSessions] = useState([])
  const [boundaryText, setBoundaryText] = useState(() =>
    (contact?.boundaries || []).join('\n'),
  )
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api('/api/wechat/sessions?limit=100')
      .then((result) =>
        setSessions(
          result.sessions.filter(
            (session) =>
              session.chat_type === 'private' || session.chat_type === 'group',
          ),
        ),
      )
      .catch(() => setSessions([]))
  }, [])

  const submit = async (event) => {
    event.preventDefault()
    setSaving(true)
    setError('')
    try {
      const savedContact = await api('/api/contacts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...form,
          contact_id: isEditing
            ? form.contact_id
            : form.contact_id.trim() ||
              (form.wechat_username
                ? `wechat:${form.wechat_username}`
                : `contact-${Date.now().toString(36)}`),
          display_name: form.display_name.trim(),
          wechat_username: form.wechat_username.trim(),
          preferred_address: form.preferred_address.trim(),
          is_demo: Boolean(form.is_demo),
          boundaries: boundaryText
            .split('\n')
            .map((item) => item.trim())
            .filter(Boolean),
        }),
      })
      onSaved(savedContact)
    } catch (submitError) {
      setError(submitError.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      title={isEditing ? '编辑联系人' : '添加联系人'}
      subtitle={
        isEditing
          ? '称呼、长度和语气会立刻影响下一轮草稿'
          : '关系和称呼会影响草稿的语气'
      }
      onClose={onClose}
    >
      <form className="modal-body form-grid" onSubmit={submit}>
        <label className="field full">
          <span>从微信会话选择</span>
          <select
            value={form.wechat_username}
            onChange={(event) => {
              const username = event.target.value
              const session = sessions.find(
                (item) => item.username === username,
              )
              setForm({
                ...form,
                wechat_username: username,
                chat_type:
                  session?.chat_type === 'group' ? 'group' : 'private',
                participant_count: session?.participant_count || null,
                display_name:
                  form.display_name || session?.display_name || '',
              })
            }}
          >
            <option value="">暂不绑定微信会话</option>
            {sessions.map((session) => (
              <option key={session.username} value={session.username}>
                {session.display_name}
                {session.chat_type === 'group'
                  ? ` · 群聊${
                      session.participant_count
                        ? ` · ${session.participant_count} 人`
                        : ''
                    }`
                  : ' · 私聊'}
              </option>
            ))}
          </select>
        </label>

        <label className="field full">
          <span>显示名称</span>
          <input
            required
            maxLength={80}
            value={form.display_name}
            onChange={(event) =>
              setForm({ ...form, display_name: event.target.value })
            }
            placeholder="例如：小林"
          />
        </label>

        <fieldset className="field full">
          <legend>关系类型</legend>
          <div className="segmented relationship-options">
            {Object.entries(relationshipMeta).map(([value, meta]) => {
              const RelationIcon = meta.icon
              return (
                <button
                  type="button"
                  className={form.relationship === value ? 'active' : ''}
                  key={value}
                  onClick={() => setForm({ ...form, relationship: value })}
                >
                  <RelationIcon size={16} />
                  {meta.label}
                </button>
              )
            })}
          </div>
        </fieldset>

        {form.chat_type === 'group' && (
          <>
            <fieldset className="field full">
              <legend>群聊触发方式</legend>
              <div className="segmented relationship-options">
                <button
                  type="button"
                  className={
                    form.group_trigger_mode === 'mention_only' ? 'active' : ''
                  }
                  onClick={() =>
                    setForm({ ...form, group_trigger_mode: 'mention_only' })
                  }
                >
                  仅 @我或关键词
                </button>
                <button
                  type="button"
                  className={
                    form.group_trigger_mode === 'all_messages' ? 'active' : ''
                  }
                  onClick={() =>
                    setForm({ ...form, group_trigger_mode: 'all_messages' })
                  }
                >
                  所有新消息
                </button>
              </div>
            </fieldset>
            <label className="field full">
              <span>群聊触发关键词</span>
              <input
                value={(form.group_mention_keywords || []).join(', ')}
                onChange={(event) =>
                  setForm({
                    ...form,
                    group_mention_keywords: event.target.value
                      .split(',')
                      .map((item) => item.trim())
                      .filter(Boolean),
                  })
                }
                placeholder="多个关键词用逗号分隔，可留空"
              />
            </label>
          </>
        )}

        <label className="field">
          <span>微信会话 ID</span>
          <input
            maxLength={160}
            value={form.wechat_username}
            onChange={(event) =>
              setForm({ ...form, wechat_username: event.target.value })
            }
            placeholder="例如：wxid_xxx 或群聊 @chatroom"
          />
        </label>

        <label className="field">
          <span>常用称呼</span>
          <input
            maxLength={40}
            value={form.preferred_address}
            onChange={(event) =>
              setForm({ ...form, preferred_address: event.target.value })
            }
            placeholder="例如：宝、老张"
          />
        </label>

        <label className="field">
          <span>回复长度</span>
          <select
            value={form.message_length}
            onChange={(event) =>
              setForm({ ...form, message_length: event.target.value })
            }
          >
            <option value="very_short">很短</option>
            <option value="short">简短</option>
            <option value="medium">适中</option>
          </select>
        </label>

        <label className="field">
          <span>表情使用</span>
          <select
            value={form.emoji_level}
            onChange={(event) =>
              setForm({ ...form, emoji_level: event.target.value })
            }
          >
            <option value="none">不用</option>
            <option value="low">偶尔</option>
            <option value="medium">适中</option>
            <option value="high">经常</option>
          </select>
        </label>

        <label className="field">
          <span>幽默程度</span>
          <select
            value={form.humor_level}
            onChange={(event) =>
              setForm({ ...form, humor_level: event.target.value })
            }
          >
            <option value="low">克制</option>
            <option value="medium">自然</option>
            <option value="high">活跃</option>
          </select>
        </label>

        <label className="field full">
          <span>表达边界（每行一条）</span>
          <textarea
            value={boundaryText}
            onChange={(event) => setBoundaryText(event.target.value)}
            placeholder={'不替我承诺见面\n不讨论借款'}
          />
        </label>

        <label className="field full">
          <span>复用已提取的表达风格</span>
          <select
            value={form.style_preset_id}
            onChange={(event) =>
              setForm({ ...form, style_preset_id: event.target.value })
            }
          >
            <option value="">不使用外部风格</option>
            {stylePresets.map((preset) => (
              <option value={preset.id} key={preset.id}>
                {preset.name} · {preset.sample_count || 0} 条样本
              </option>
            ))}
          </select>
        </label>

        {error && <p className="form-error full">{error}</p>}

        <div className="modal-actions full">
          <button type="button" className="button ghost" onClick={onClose}>
            取消
          </button>
          <button
            type="submit"
            className="button primary"
            disabled={saving || !form.display_name.trim()}
          >
            {saving ? (
              <LoaderCircle className="spin" size={17} />
            ) : isEditing ? (
              <Check size={17} />
            ) : (
              <Plus size={17} />
            )}
            {isEditing ? '保存偏好' : '保存联系人'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

function ImportModal({ contact, onClose, onImported }) {
  const [mode, setMode] = useState('text')
  const [content, setContent] = useState('')
  const [file, setFile] = useState(null)
  const [selfLabel, setSelfLabel] = useState('我')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const submit = async (event) => {
    event.preventDefault()
    setSaving(true)
    setError('')
    try {
      let result
      if (mode === 'text') {
        result = await api('/api/import/text', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            contact_id: contact.contact_id,
            relationship: contact.relationship,
            content,
            self_label: selfLabel,
          }),
        })
      } else {
        const formData = new FormData()
        formData.append('file', file)
        formData.append('contact_id', contact.contact_id)
        formData.append('relationship', contact.relationship)
        formData.append('self_label', selfLabel)
        result = await api('/api/import/file', {
          method: 'POST',
          body: formData,
        })
      }
      onImported(result.imported)
    } catch (submitError) {
      setError(submitError.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      title={`导入 ${contact.display_name} 的聊天记录`}
      subtitle="原始内容只写入本机 data/messages.jsonl"
      onClose={onClose}
      wide
    >
      <form className="modal-body" onSubmit={submit}>
        <div className="segmented import-tabs">
          <button
            type="button"
            className={mode === 'text' ? 'active' : ''}
            onClick={() => setMode('text')}
          >
            <Clipboard size={16} />
            粘贴文本
          </button>
          <button
            type="button"
            className={mode === 'file' ? 'active' : ''}
            onClick={() => setMode('file')}
          >
            <FileText size={16} />
            上传文件
          </button>
        </div>

        <label className="field">
          <span>你在记录中的名字</span>
          <input
            value={selfLabel}
            onChange={(event) => setSelfLabel(event.target.value)}
            placeholder="我"
          />
        </label>

        {mode === 'text' ? (
          <label className="field">
            <span>聊天内容</span>
            <textarea
              className="import-textarea"
              value={content}
              onChange={(event) => setContent(event.target.value)}
              placeholder={'对方: 今天有点累\n我: 怎么啦\n我: 跟我说说'}
            />
          </label>
        ) : (
          <label className="file-drop">
            <Upload size={24} />
            <strong>{file?.name || '选择 TXT、MD 或 CSV 文件'}</strong>
            <span>点击浏览本地文件</span>
            <input
              type="file"
              accept=".txt,.md,.csv"
              onChange={(event) => setFile(event.target.files?.[0] || null)}
            />
          </label>
        )}

        {error && <p className="form-error">{error}</p>}

        <div className="modal-actions">
          <button type="button" className="button ghost" onClick={onClose}>
            取消
          </button>
          <button
            type="submit"
            className="button primary"
            disabled={
              saving || (mode === 'text' ? !content.trim() : !file)
            }
          >
            {saving ? (
              <LoaderCircle className="spin" size={17} />
            ) : (
              <Upload size={17} />
            )}
            开始导入
          </button>
        </div>
      </form>
    </Modal>
  )
}

function SettingsModal({ initial, onClose, onSaved }) {
  const [form, setForm] = useState({ ...initial, api_key: '' })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const submit = async (event) => {
    event.preventDefault()
    setSaving(true)
    setError('')
    try {
      const result = await api('/api/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      onSaved(result)
    } catch (submitError) {
      setError(submitError.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      title="模型设置"
      subtitle="API Key 只保存在当前服务进程"
      onClose={onClose}
    >
      <form className="modal-body" onSubmit={submit}>
        <fieldset className="field">
          <legend>提供方</legend>
          <div className="segmented provider-options">
            {[
              ['demo', '离线演示'],
              ['ollama', 'Ollama'],
              ['openai-compatible', 'OpenAI 兼容'],
            ].map(([value, label]) => (
              <button
                type="button"
                className={form.provider === value ? 'active' : ''}
                key={value}
                onClick={() => setForm({ ...form, provider: value })}
              >
                {label}
              </button>
            ))}
          </div>
        </fieldset>

        {form.provider !== 'demo' && (
          <>
            <label className="field">
              <span>服务地址</span>
              <input
                required
                value={form.base_url}
                onChange={(event) =>
                  setForm({ ...form, base_url: event.target.value })
                }
                placeholder="http://127.0.0.1:11434"
              />
            </label>
            <label className="field">
              <span>模型名称</span>
              <input
                required
                value={form.model}
                onChange={(event) =>
                  setForm({ ...form, model: event.target.value })
                }
                placeholder="qwen3:8b"
              />
            </label>
          </>
        )}

        {form.provider === 'openai-compatible' && (
          <label className="field">
            <span>API Key</span>
            {initial.api_key_configured && (
              <small>已保存 API Key，留空会继续使用已保存的 Key。</small>
            )}
            <input
              type="password"
              value={form.api_key}
              onChange={(event) =>
                setForm({ ...form, api_key: event.target.value })
              }
              placeholder="仅本次运行有效"
            />
          </label>
        )}

        {error && <p className="form-error">{error}</p>}

        <div className="privacy-note">
          <ShieldCheck size={18} />
          <span>
            离线演示不发送外部请求；其他模式会将当前对话和必要上下文发送到你配置的模型服务。
          </span>
        </div>

        <div className="modal-actions">
          <button type="button" className="button ghost" onClick={onClose}>
            取消
          </button>
          <button
            type="submit"
            className="button primary"
            disabled={saving}
          >
            {saving ? (
              <LoaderCircle className="spin" size={17} />
            ) : (
              <Send size={17} />
            )}
            应用设置
          </button>
        </div>
      </form>
    </Modal>
  )
}

export default App
