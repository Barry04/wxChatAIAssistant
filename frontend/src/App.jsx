import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Check,
  ChevronDown,
  Clipboard,
  Database,
  Heart,
  LoaderCircle,
  MessageCircle,
  Pencil,
  Plus,
  RefreshCw,
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
import './App.css'
import './Modern.css'
import { api } from './api'
import { IconButton, Modal } from './ui'
import { relationshipMeta } from './relationshipMeta'
import { AgentFlowGraph } from './flow'
import { PendingWorkbench } from './pending'
import WeChatModal from './WeChatModal'
import ContactModal from './ContactModal'
import ImportModal from './ImportModal'
import SettingsModal from './SettingsModal'

const autoSendLevelOptions = [
  { level: 'L0', label: 'L0 日常聊天' },
  { level: 'L1', label: 'L1 轻度计划/提醒' },
  { level: 'L2', label: 'L2 敏感关系场景' },
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
    (level) => level !== 'L3',
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
  const [workspaceMode, setWorkspaceMode] = useState('draft')
  const [pendingScope, setPendingScope] = useState('current')
  const [pendingCount, setPendingCount] = useState(0)
  const [pendingItems, setPendingItems] = useState([])
  const [pendingDrafts, setPendingDrafts] = useState({})
  const lastPendingL1Ids = useRef(null)

  const selectedContact = useMemo(
    () => contacts.find((item) => item.contact_id === selectedId),
    [contacts, selectedId],
  )

  const selectedSkill = useMemo(
    () => skills.find((item) => item.id === selectedContact?.relationship),
    [skills, selectedContact],
  )

  const selectableStylePresets = useMemo(
    () => stylePresets.filter((preset) => preset.id !== 'style:balanced'),
    [stylePresets],
  )

  const showNotice = (message, type = 'success') => {
    setNotice({ message, type })
    window.setTimeout(() => setNotice(null), 3200)
  }

  const refreshStats = async () => {
    const nextStats = await api('/api/stats')
    setStats(nextStats)
  }

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
    if (!text) return
    setBusy(`confirm:${item.id}`)
    try {
      await api(`/api/automation/confirm/${encodeURIComponent(item.id)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      })
      const pending = await api('/api/automation/pending')
      setPendingCount(pending.length)
      setPendingItems(pending)
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
                    setSelectedId(contact.contact_id)
                    if (workspaceMode === 'pending') {
                      setPendingScope('current')
                    } else {
                      setWorkspaceMode('draft')
                    }
                    setMobileSidebar(false)
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
                <h1>{selectedContact?.display_name || '选择联系人'}</h1>
                {selectedContact && (
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
              <p>{selectedSkill?.description || '建立联系人后开始生成草稿'}</p>
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
            {pendingCount > 0 && (
              <button
                type="button"
                className={`connection-button pending ${
                  workspaceMode === 'pending' ? 'active' : ''
                }`}
                onClick={() => {
                  setPendingScope('current')
                  setWorkspaceMode('pending')
                }}
              >
                <ShieldCheck size={16} />
                {pendingCount} 条待确认
              </button>
            )}
            {selectedContact && (
              <IconButton
                label="编辑联系人"
                onClick={() => setModal('edit-contact')}
              >
                <Pencil size={18} />
              </IconButton>
            )}
            {selectedContact && !selectedContact.is_demo && (
              <IconButton label="删除联系人" onClick={removeContact}>
                <Trash2 size={18} />
              </IconButton>
            )}
            <button
              type="button"
              className="button secondary"
              onClick={() => setModal('import')}
              disabled={!selectedContact}
            >
              <Upload size={17} />
              导入记录
            </button>
            <IconButton label="模型设置" onClick={() => setModal('settings')}>
              <Settings size={18} />
            </IconButton>
          </div>
        </header>

        <nav className="workspace-nav" aria-label="工作区">
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
            onClick={() => {
              setPendingScope('current')
              setWorkspaceMode('pending')
            }}
          >
            <ShieldCheck size={16} />
            待确认
            {pendingCount > 0 && <span>{pendingCount}</span>}
          </button>
        </nav>

        {workspaceMode === 'pending' ? (
          <PendingWorkbench
            pending={pendingItems}
            selectedContact={selectedContact}
            scope={pendingScope}
            setScope={setPendingScope}
            pendingDrafts={pendingDrafts}
            setPendingDrafts={setPendingDrafts}
            working={busy}
            onConfirm={confirmWorkspacePending}
            onDiscard={discardWorkspacePending}
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
                      默认只自动发送 L0；可以针对关系稳定、日常沟通较多的联系人开放 L1。
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
                      ).join('、')}。L3 始终禁止自动发送。`
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

        <section className="insight-bar">
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

export default App
