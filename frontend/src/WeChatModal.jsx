import { useEffect, useMemo, useState } from 'react'
import {
  Check,
  Database,
  LoaderCircle,
  Pause,
  Plus,
  Play,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  Sparkles,
} from 'lucide-react'
import { api } from './api'
import { Modal } from './ui'
import { AutomationFlowGraph } from './flow'
import { PendingConfirmationList } from './pending'

function WeChatModal({
  status,
  contacts,
  girlsChatStyle,
  onClose,
  onRefresh,
  onChanged,
  onAddContact,
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
    const text = (pendingDrafts[item.id] || '').trim()
    if (!text) return
    setWorking(`confirm:${item.id}`)
    setError('')
    try {
      await api(`/api/automation/confirm/${encodeURIComponent(item.id)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
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

export default WeChatModal
