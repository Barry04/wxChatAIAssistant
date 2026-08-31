import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Activity,
  AlertTriangle,
  Bot,
  CheckCircle2,
  ChevronRight,
  Clock3,
  Database,
  Filter,
  LoaderCircle,
  MessageCircle,
  Pause,
  Play,
  RefreshCw,
  RotateCcw,
  Search,
  Send,
  ShieldCheck,
  TerminalSquare,
  XCircle,
} from 'lucide-react'

const failureActions = new Set(['error', 'read_error', 'send_unverified'])

const actionMeta = {
  baseline: { label: '已建立基线', tone: 'neutral', icon: Database },
  drafted: { label: '已生成草稿', tone: 'info', icon: Bot },
  needs_confirmation: { label: '等待确认', tone: 'warning', icon: ShieldCheck },
  blocked: { label: '已阻止', tone: 'warning', icon: ShieldCheck },
  sent: { label: '已发送', tone: 'success', icon: Send },
  send_unverified: { label: '发送未验证', tone: 'danger', icon: AlertTriangle },
  read_error: { label: '读取失败', tone: 'danger', icon: XCircle },
  error: { label: '运行错误', tone: 'danger', icon: XCircle },
  waiting_for_user: { label: '等待人工接管', tone: 'warning', icon: Pause },
  already_replied: { label: '无需回复', tone: 'neutral', icon: CheckCircle2 },
}

function eventMeta(event) {
  return (
    actionMeta[event?.action] || {
      label: event?.action || '未知事件',
      tone: 'neutral',
      icon: Activity,
    }
  )
}

function formatDateTime(value) {
  if (!value) return '时间未知'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date)
}

function eventError(event) {
  return (
    event?.send_error ||
    event?.last_error ||
    event?.error ||
    event?.generation?.warning ||
    ''
  )
}

function isFailure(event) {
  return Boolean(
    failureActions.has(event?.action) ||
      eventError(event) ||
      event?.sent === false ||
      event?.send_verified === false,
  )
}

function eventSearchText(event) {
  return [
    event.display_name,
    event.contact_id,
    event.talker,
    event.action,
    event.candidate,
    ...(event.incoming || []),
    eventError(event),
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
}

function modelSearchText(record) {
  return [record.provider, record.model, record.endpoint, record.status, record.error]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
}

function RecordEmpty({ title, description }) {
  return (
    <div className="operations-empty">
      <ShieldCheck size={30} />
      <strong>{title}</strong>
      <p>{description}</p>
    </div>
  )
}

function TraceList({ title, items = [], type = 'agent' }) {
  if (!items.length) return null
  return (
    <section className="operations-detail-section">
      <div className="operations-detail-section-title">
        <span>{title}</span>
        <strong>{items.length} 步</strong>
      </div>
      <div className="operations-trace-list">
        {items.map((item, index) => (
          <div className="operations-trace-item" key={`${type}-${index}-${item.role || item.task}`}>
            <span className={`operations-trace-dot status-${item.status || 'ok'}`} />
            <div>
              <strong>{item.role || item.task || `步骤 ${index + 1}`}</strong>
              <p>{item.summary || item.reason_code || item.next_task || '已完成'}</p>
            </div>
            {typeof item.duration_ms === 'number' && <small>{item.duration_ms}ms</small>}
          </div>
        ))}
      </div>
    </section>
  )
}

function AgentInvocationGraph({ event }) {
  const agentTrace = event?.generation?.trace || event?.trace || []
  const hubTrace = event?.hub_trace || []
  const roleLabels = {
    understand: 'Understand',
    style: 'Style',
    writer: 'Writer',
    reviewer: 'Reviewer',
    rewrite: 'Rewrite',
  }
  const taskLabels = {
    hub: 'Hub',
    watch_read: 'Watch Read',
    memory_sync: 'Memory Sync',
    watch_evaluate: 'Watch Evaluate',
    draft: 'Draft Agent',
    policy: 'Policy Gate',
    queue: 'Confirmation Queue',
    operator: 'Operator',
    finish: 'Finish',
  }
  const defaultHubSteps = [
    { task: 'watch_read', status: 'idle', next_task: 'hub' },
    { task: 'hub', status: 'idle', next_task: 'memory_sync' },
    { task: 'memory_sync', status: 'idle', next_task: 'hub' },
    { task: 'hub', status: 'idle', next_task: 'watch_evaluate' },
    { task: 'watch_evaluate', status: 'idle', next_task: 'hub' },
    { task: 'hub', status: 'idle', next_task: 'draft' },
    { task: 'draft', status: 'idle', next_task: 'hub' },
    { task: 'hub', status: 'idle', next_task: 'policy' },
    { task: 'policy', status: 'idle', next_task: 'finish' },
  ]
  const hubSteps = hubTrace.length ? hubTrace : defaultHubSteps
  const roles = ['understand', 'style', 'writer', 'reviewer']
  const reviewerStep = [...agentTrace].reverse().find((step) => step.role === 'reviewer')
  const revised = reviewerStep?.status === 'revise' || agentTrace.some((step) => step.role === 'rewrite')

  return (
    <section className="operations-agent-graph">
      <div className="operations-agent-graph-heading">
        <div>
          <span className="eyebrow">Agent Invocation Graph</span>
          <strong>实际调用链与安全门禁</strong>
        </div>
        <span>{hubTrace.length ? `${hubTrace.length} 个运行节点` : '旧记录 · 推断拓扑'}</span>
      </div>

      <div className="operations-graph-lane">
        <div className="operations-graph-lane-label">
          <Activity size={15} />
          Hub 主链
        </div>
        <div className="operations-hub-flow">
          {hubSteps.map((step, index) => (
            <div className="operations-hub-step" key={`${step.task}-${index}-${step.next_task}`}>
              <article
                className={`operations-graph-node node-${step.task} status-${step.status || 'ok'}`}
              >
                <span>{taskLabels[step.task] || step.task}</span>
                <strong>{step.reason_code || step.status || '等待运行'}</strong>
                <small>
                  {step.decision_source || 'rule'}
                  {typeof step.duration_ms === 'number' ? ` · ${step.duration_ms}ms` : ''}
                </small>
              </article>
              {index < hubSteps.length - 1 && (
                <div className="operations-graph-edge">
                  <span>{step.next_task || hubSteps[index + 1]?.task}</span>
                  <ChevronRight size={15} />
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="operations-graph-lane">
        <div className="operations-graph-lane-label">
          <Bot size={15} />
          Draft 子图
        </div>
        <div className="operations-agent-flow">
          {roles.map((role, index) => {
            const step = [...agentTrace].reverse().find((item) => item.role === role)
            return (
              <div className="operations-agent-step" key={role}>
                <article
                  className={`operations-graph-node node-agent status-${step?.status || 'idle'}`}
                >
                  <span>{roleLabels[role]}</span>
                  <strong>{step?.summary || '等待调用'}</strong>
                  <small>
                    {typeof step?.duration_ms === 'number' ? `${step.duration_ms}ms` : '未执行'}
                  </small>
                </article>
                {index < roles.length - 1 && (
                  <div className="operations-graph-edge agent-edge">
                    <span>direct call</span>
                    <ChevronRight size={15} />
                  </div>
                )}
              </div>
            )
          })}
          {revised && (
            <div className="operations-rewrite-loop">
              <RotateCcw size={14} />
              Reviewer 要求重写，调用返回 Writer
            </div>
          )}
        </div>
      </div>

      <div className="operations-policy-flow">
        <span className="operations-policy-label">确定性边界</span>
        <div>
          <article className="operations-policy-node">
            <ShieldCheck size={16} />
            <span>
              <strong>PolicyGate</strong>
              <small>LLM 无权绕过</small>
            </span>
          </article>
          <ChevronRight size={16} />
          <article className={`operations-policy-node result-${event?.action || 'unknown'}`}>
            {event?.action === 'sent' ? <Send size={16} /> : <ShieldCheck size={16} />}
            <span>
              <strong>{eventMeta(event).label}</strong>
              <small>{event?.action === 'sent' ? 'Operator 校验后发送' : '未进入直接发送'}</small>
            </span>
          </article>
        </div>
      </div>
    </section>
  )
}

function AutomationDetail({
  event,
  contacts,
  worker,
  retrying,
  onRetry,
  onOpenContact,
  onOpenPending,
  onOpenWechat,
}) {
  if (!event) {
    return (
      <RecordEmpty
        title="选择一条运行记录"
        description="左侧记录会按时间倒序排列，失败项会优先显示错误原因。"
      />
    )
  }

  const meta = eventMeta(event)
  const StatusIcon = meta.icon
  const error = eventError(event)
  const contactExists = contacts.some((contact) => contact.contact_id === event.contact_id)
  const agentTrace = event.generation?.trace || event.trace || []
  const hubTrace = event.hub_trace || []
  const canRetry = isFailure(event) && Boolean(event.contact_id) && contactExists

  return (
    <article className="operations-detail-card">
      <header className="operations-detail-header">
        <div>
          <span className="eyebrow">运行详情</span>
          <h2>{event.display_name || '自动化任务'}</h2>
          <p>{formatDateTime(event.created_at)}</p>
        </div>
        <span className={`operations-status status-${meta.tone}`}>
          <StatusIcon size={15} />
          {meta.label}
        </span>
      </header>

      {error && (
        <section className="operations-error-panel">
          <AlertTriangle size={19} />
          <div>
            <strong>失败原因</strong>
            <p>{error}</p>
          </div>
        </section>
      )}

      <div className="operations-detail-actions">
        {canRetry && (
          <button
            type="button"
            className="button primary"
            onClick={() => onRetry(event)}
            disabled={retrying}
          >
            {retrying ? <LoaderCircle className="spin" size={16} /> : <RotateCcw size={16} />}
            重新检查该会话
          </button>
        )}
        {event.action === 'needs_confirmation' && (
          <button type="button" className="button secondary" onClick={onOpenPending}>
            <ShieldCheck size={16} />
            打开待确认
          </button>
        )}
        {contactExists && (
          <button
            type="button"
            className="button ghost"
            onClick={() => onOpenContact(event.contact_id)}
          >
            <MessageCircle size={16} />
            返回联系人
          </button>
        )}
        {!contactExists && event.contact_id && (
          <span className="operations-orphan-note">联系人已不在工作台中</span>
        )}
        {isFailure(event) && (
          <button type="button" className="button ghost" onClick={onOpenWechat}>
            <Database size={16} />
            检查微信连接
          </button>
        )}
      </div>

      <AgentInvocationGraph event={event} />

      <section className="operations-facts-grid">
        <div>
          <span>风险级别</span>
          <strong>{event.risk?.level || '未识别'}</strong>
        </div>
        <div>
          <span>发送状态</span>
          <strong>{event.send_verified ? '已验证' : event.sent ? '已提交' : '未发送'}</strong>
        </div>
        <div>
          <span>配置范围</span>
          <strong>{event.settings_scope === 'contact' ? '联系人级' : '全局'}</strong>
        </div>
        <div>
          <span>编排模式</span>
          <strong>{event.orchestration_mode || worker?.orchestration_mode || '规则流程'}</strong>
        </div>
      </section>

      {event.incoming?.length > 0 && (
        <section className="operations-detail-section">
          <div className="operations-detail-section-title">
            <span>触发上下文</span>
            <strong>{event.incoming.length} 条</strong>
          </div>
          <div className="operations-context-stack">
            {event.incoming.map((message, index) => (
              <p key={`${message}-${index}`}>{message}</p>
            ))}
          </div>
        </section>
      )}

      {event.candidate && (
        <section className="operations-detail-section">
          <div className="operations-detail-section-title">
            <span>候选回复</span>
          </div>
          <blockquote className="operations-candidate">{event.candidate}</blockquote>
        </section>
      )}

      {event.generation && (
        <section className="operations-detail-section">
          <div className="operations-detail-section-title">
            <span>生成信息</span>
            <strong>{event.generation.provider || '本地规则'}</strong>
          </div>
          <div className="operations-generation-grid">
            <div>
              <span>对话动作</span>
              <strong>{event.generation.dialogue?.dialogue_act || '未知'}</strong>
            </div>
            <div>
              <span>主题</span>
              <strong>{event.generation.dialogue?.topic || 'general'}</strong>
            </div>
            <div>
              <span>审核</span>
              <strong>{event.generation.review?.decision || '未记录'}</strong>
            </div>
            <div>
              <span>模型回退</span>
              <strong>{event.generation.model_fallback ? '是' : '否'}</strong>
            </div>
          </div>
        </section>
      )}

      <TraceList title="草稿 Agent 链路" items={agentTrace} />
      <TraceList title="Hub 编排链路" items={hubTrace} type="hub" />

      <details className="operations-raw-record">
        <summary>
          <TerminalSquare size={15} />
          查看原始记录
        </summary>
        <pre>{JSON.stringify(event, null, 2)}</pre>
      </details>
    </article>
  )
}

function ModelDetail({ record }) {
  if (!record) {
    return (
      <RecordEmpty
        title="选择一次模型调用"
        description="模型日志只保存提供方、耗时和错误，不保存聊天正文或提示词。"
      />
    )
  }
  const failed = record.status !== 'success'
  return (
    <article className="operations-detail-card">
      <header className="operations-detail-header">
        <div>
          <span className="eyebrow">模型调用</span>
          <h2>{record.model || '未命名模型'}</h2>
          <p>{formatDateTime(record.created_at)}</p>
        </div>
        <span className={`operations-status status-${failed ? 'danger' : 'success'}`}>
          {failed ? <XCircle size={15} /> : <CheckCircle2 size={15} />}
          {failed ? '调用失败' : '调用成功'}
        </span>
      </header>

      {record.error && (
        <section className="operations-error-panel">
          <AlertTriangle size={19} />
          <div>
            <strong>模型错误</strong>
            <p>{record.error}</p>
          </div>
        </section>
      )}

      <section className="operations-facts-grid">
        <div>
          <span>提供方</span>
          <strong>{record.provider || '未知'}</strong>
        </div>
        <div>
          <span>服务端点</span>
          <strong>{record.endpoint || '本地'}</strong>
        </div>
        <div>
          <span>HTTP 状态</span>
          <strong>{record.http_status || '无'}</strong>
        </div>
        <div>
          <span>耗时</span>
          <strong>{typeof record.duration_ms === 'number' ? `${record.duration_ms}ms` : '未知'}</strong>
        </div>
      </section>

      <div className="privacy-note operations-privacy-note">
        <ShieldCheck size={18} />
        <span>该记录不包含 API Key、提示词、聊天正文或模型回复。</span>
      </div>

      <details className="operations-raw-record">
        <summary>
          <TerminalSquare size={15} />
          查看原始记录
        </summary>
        <pre>{JSON.stringify(record, null, 2)}</pre>
      </details>
    </article>
  )
}

export default function OperationsPage({
  api,
  contacts,
  onOpenContact,
  onOpenPending,
  onOpenWechat,
}) {
  const [events, setEvents] = useState([])
  const [modelCalls, setModelCalls] = useState([])
  const [worker, setWorker] = useState(null)
  const [activeTab, setActiveTab] = useState('automation')
  const [statusFilter, setStatusFilter] = useState('failures')
  const [contactFilter, setContactFilter] = useState('all')
  const [search, setSearch] = useState('')
  const [selectedEventId, setSelectedEventId] = useState('')
  const [selectedModelId, setSelectedModelId] = useState('')
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [retrying, setRetrying] = useState(false)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [error, setError] = useState('')

  const loadRecords = useCallback(
    async (quiet = false) => {
      if (!quiet) setRefreshing(true)
      try {
        const [nextEvents, nextModelCalls, nextWorker] = await Promise.all([
          api('/api/automation/events?limit=200'),
          api('/api/logs/model-calls?limit=200'),
          api('/api/automation/status'),
        ])
        const normalizedEvents = nextEvents
          .map((event, index) => ({
            ...event,
            _recordId: [
              event.created_at || 'event',
              event.contact_id || 'system',
              event.action || 'unknown',
              event.newest_local_id ?? index,
            ].join(':'),
          }))
          .reverse()
        const normalizedModels = nextModelCalls
          .map((record, index) => ({
            ...record,
            _recordId: [
              record.created_at || 'model',
              record.provider || 'provider',
              record.model || index,
            ].join(':'),
          }))
          .reverse()
        setEvents(normalizedEvents)
        setModelCalls(normalizedModels)
        setWorker(nextWorker)
        setSelectedEventId((current) =>
          normalizedEvents.some((event) => event._recordId === current)
            ? current
            : normalizedEvents[0]?._recordId || '',
        )
        setSelectedModelId((current) =>
          normalizedModels.some((record) => record._recordId === current)
            ? current
            : normalizedModels[0]?._recordId || '',
        )
        setError('')
      } catch (loadError) {
        setError(loadError.message)
      } finally {
        setLoading(false)
        setRefreshing(false)
      }
    },
    [api],
  )

  useEffect(() => {
    loadRecords()
  }, [loadRecords])

  useEffect(() => {
    if (!autoRefresh) return undefined
    const timer = window.setInterval(() => loadRecords(true), 5000)
    return () => window.clearInterval(timer)
  }, [autoRefresh, loadRecords])

  const summary = useMemo(
    () => ({
      total: events.length,
      failures: events.filter(isFailure).length,
      pending: events.filter((event) => event.action === 'needs_confirmation').length,
      sent: events.filter((event) => event.action === 'sent' && event.send_verified).length,
      modelFailures: modelCalls.filter((record) => record.status !== 'success').length,
    }),
    [events, modelCalls],
  )

  const eventContacts = useMemo(() => {
    const values = new Map()
    events.forEach((event) => {
      if (event.contact_id) {
        values.set(event.contact_id, event.display_name || event.contact_id)
      }
    })
    return [...values.entries()]
  }, [events])

  const filteredEvents = useMemo(() => {
    const query = search.trim().toLowerCase()
    return events.filter((event) => {
      if (contactFilter !== 'all' && event.contact_id !== contactFilter) return false
      if (statusFilter === 'failures' && !isFailure(event)) return false
      if (statusFilter === 'pending' && event.action !== 'needs_confirmation') return false
      if (statusFilter === 'sent' && !(event.action === 'sent' && event.send_verified)) return false
      if (statusFilter === 'system' && event.contact_id) return false
      return !query || eventSearchText(event).includes(query)
    })
  }, [contactFilter, events, search, statusFilter])

  const filteredModels = useMemo(() => {
    const query = search.trim().toLowerCase()
    return modelCalls.filter((record) => {
      if (statusFilter === 'failures' && record.status === 'success') return false
      if (statusFilter === 'sent' && record.status !== 'success') return false
      return !query || modelSearchText(record).includes(query)
    })
  }, [modelCalls, search, statusFilter])

  const selectedEvent =
    events.find((event) => event._recordId === selectedEventId) || filteredEvents[0] || null
  const selectedModel =
    modelCalls.find((record) => record._recordId === selectedModelId) || filteredModels[0] || null

  useEffect(() => {
    if (filteredEvents.length && !filteredEvents.some((event) => event._recordId === selectedEventId)) {
      setSelectedEventId(filteredEvents[0]._recordId)
    }
  }, [filteredEvents, selectedEventId])

  useEffect(() => {
    if (
      filteredModels.length &&
      !filteredModels.some((record) => record._recordId === selectedModelId)
    ) {
      setSelectedModelId(filteredModels[0]._recordId)
    }
  }, [filteredModels, selectedModelId])

  const retryEvent = async (event) => {
    if (!event.contact_id) return
    if (worker?.send_guard_ready) {
      const confirmed = window.confirm(
        '当前自动回复允许真实发送。重新检查该会话可能生成并发送新的 L0 回复，确认继续？',
      )
      if (!confirmed) return
    }
    setRetrying(true)
    setError('')
    try {
      const params = new URLSearchParams({ contact_id: event.contact_id })
      await api(`/api/automation/run-once?${params}`, { method: 'POST' })
      await loadRecords(true)
    } catch (retryError) {
      setError(retryError.message)
    } finally {
      setRetrying(false)
    }
  }

  const activeRecords = activeTab === 'automation' ? filteredEvents : filteredModels

  return (
    <section className="operations-page">
      <header className="operations-page-header">
        <div>
          <span className="eyebrow">Operations Center</span>
          <h2>运行记录中心</h2>
          <p>集中查看自动回复、发送验证、模型调用和失败原因。</p>
        </div>
        <div className="operations-header-actions">
          <label className="operations-live-toggle">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(event) => setAutoRefresh(event.target.checked)}
            />
            <span>{autoRefresh ? '实时刷新' : '已暂停刷新'}</span>
          </label>
          <button
            type="button"
            className="button secondary"
            onClick={() => loadRecords()}
            disabled={refreshing}
          >
            {refreshing ? <LoaderCircle className="spin" size={16} /> : <RefreshCw size={16} />}
            刷新记录
          </button>
        </div>
      </header>

      <div className="operations-summary-grid">
        <button type="button" onClick={() => { setActiveTab('automation'); setStatusFilter('all') }}>
          <Activity size={18} />
          <span>自动化记录</span>
          <strong>{summary.total}</strong>
        </button>
        <button
          type="button"
          className={summary.failures ? 'has-alert' : ''}
          onClick={() => { setActiveTab('automation'); setStatusFilter('failures') }}
        >
          <AlertTriangle size={18} />
          <span>失败与异常</span>
          <strong>{summary.failures}</strong>
        </button>
        <button type="button" onClick={() => { setActiveTab('automation'); setStatusFilter('pending') }}>
          <ShieldCheck size={18} />
          <span>等待确认</span>
          <strong>{summary.pending}</strong>
        </button>
        <button type="button" onClick={() => { setActiveTab('model'); setStatusFilter('failures') }}>
          <Bot size={18} />
          <span>模型失败</span>
          <strong>{summary.modelFailures}</strong>
        </button>
      </div>

      <div className="operations-tabs" role="tablist" aria-label="运行记录类型">
        <button
          type="button"
          className={activeTab === 'automation' ? 'active' : ''}
          onClick={() => { setActiveTab('automation'); setStatusFilter('failures') }}
        >
          <Activity size={16} />
          自动化记录
        </button>
        <button
          type="button"
          className={activeTab === 'model' ? 'active' : ''}
          onClick={() => { setActiveTab('model'); setStatusFilter('failures') }}
        >
          <Bot size={16} />
          模型调用
        </button>
      </div>

      <div className="operations-toolbar">
        <label className="operations-search">
          <Search size={16} />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder={activeTab === 'automation' ? '搜索联系人、动作或错误原因' : '搜索模型或错误'}
          />
        </label>
        {activeTab === 'automation' && (
          <label className="operations-select">
            <MessageCircle size={15} />
            <select value={contactFilter} onChange={(event) => setContactFilter(event.target.value)}>
              <option value="all">全部联系人</option>
              {eventContacts.map(([contactId, displayName]) => (
                <option value={contactId} key={contactId}>{displayName}</option>
              ))}
            </select>
          </label>
        )}
        <label className="operations-select">
          <Filter size={15} />
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="all">全部状态</option>
            <option value="failures">失败与异常</option>
            {activeTab === 'automation' && <option value="pending">等待确认</option>}
            <option value="sent">{activeTab === 'automation' ? '发送成功' : '调用成功'}</option>
            {activeTab === 'automation' && <option value="system">系统事件</option>}
          </select>
        </label>
      </div>

      {error && <p className="form-error operations-page-error">{error}</p>}

      <div className="operations-layout">
        <aside className="operations-record-list" aria-label="运行记录列表">
          <div className="operations-record-list-heading">
            <span>{activeTab === 'automation' ? '自动化事件' : '模型调用'}</span>
            <strong>{activeRecords.length} 条</strong>
          </div>
          {loading ? (
            <div className="operations-list-loading">
              <LoaderCircle className="spin" size={22} />
              正在读取本地记录
            </div>
          ) : activeRecords.length === 0 ? (
            <RecordEmpty title="没有匹配记录" description="调整筛选条件或等待下一次运行。" />
          ) : activeTab === 'automation' ? (
            filteredEvents.map((event) => {
              const meta = eventMeta(event)
              const StatusIcon = meta.icon
              return (
                <button
                  type="button"
                  className={`operations-record-item ${
                    selectedEvent?._recordId === event._recordId ? 'active' : ''
                  }`}
                  key={event._recordId}
                  onClick={() => setSelectedEventId(event._recordId)}
                >
                  <span className={`operations-record-icon status-${meta.tone}`}>
                    <StatusIcon size={15} />
                  </span>
                  <span className="operations-record-copy">
                    <strong>{event.display_name || '自动监听'}</strong>
                    <small>{eventError(event) || event.candidate || meta.label}</small>
                    <em>{formatDateTime(event.created_at)}</em>
                  </span>
                  <ChevronRight size={15} />
                </button>
              )
            })
          ) : (
            filteredModels.map((record) => {
              const failed = record.status !== 'success'
              return (
                <button
                  type="button"
                  className={`operations-record-item ${
                    selectedModel?._recordId === record._recordId ? 'active' : ''
                  }`}
                  key={record._recordId}
                  onClick={() => setSelectedModelId(record._recordId)}
                >
                  <span className={`operations-record-icon status-${failed ? 'danger' : 'success'}`}>
                    {failed ? <XCircle size={15} /> : <CheckCircle2 size={15} />}
                  </span>
                  <span className="operations-record-copy">
                    <strong>{record.model || record.provider || '模型调用'}</strong>
                    <small>{record.error || record.endpoint || record.status}</small>
                    <em>{formatDateTime(record.created_at)}</em>
                  </span>
                  <ChevronRight size={15} />
                </button>
              )
            })
          )}
        </aside>

        <div className="operations-detail-pane">
          {activeTab === 'automation' ? (
            <AutomationDetail
              event={selectedEvent}
              contacts={contacts}
              worker={worker}
              retrying={retrying}
              onRetry={retryEvent}
              onOpenContact={onOpenContact}
              onOpenPending={onOpenPending}
              onOpenWechat={onOpenWechat}
            />
          ) : (
            <ModelDetail record={selectedModel} />
          )}
        </div>
      </div>

      <footer className="operations-footer-note">
        <Clock3 size={16} />
        <span>页面最多读取最近 200 条本地记录，每 5 秒刷新一次；不会上传日志。</span>
        {autoRefresh ? <Play size={14} /> : <Pause size={14} />}
      </footer>
    </section>
  )
}
