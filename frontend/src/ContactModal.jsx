import { useEffect, useState } from 'react'
import { Check, LoaderCircle, Plus } from 'lucide-react'
import { api } from './api'
import { Modal } from './ui'
import { relationshipMeta } from './relationshipMeta'

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

export default ContactModal
