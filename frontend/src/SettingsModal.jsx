import { useState } from 'react'
import { LoaderCircle, Send, ShieldCheck } from 'lucide-react'
import { api } from './api'
import { Modal } from './ui'

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

export default SettingsModal
