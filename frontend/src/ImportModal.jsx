import { useState } from 'react'
import { Clipboard, FileText, LoaderCircle, Upload } from 'lucide-react'
import { api } from './api'
import { Modal } from './ui'

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

export default ImportModal
