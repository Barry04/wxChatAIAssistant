import { useEffect, useState } from 'react'
import {
  Check,
  LoaderCircle,
  Send,
  ShieldCheck,
  Trash2,
} from 'lucide-react'

function PendingConfirmationList({
  pending,
  pendingDrafts,
  setPendingDrafts,
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
            <div className="pending-actions">
              <button
                type="button"
                className="button primary"
                onClick={() => onConfirm(item)}
                disabled={
                  Boolean(working) ||
                  !(pendingDrafts[item.id] || item.candidate || '').trim()
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
  scope,
  setScope,
  pendingDrafts,
  setPendingDrafts,
  working,
  onConfirm,
  onDiscard,
}) {
  const [activeId, setActiveId] = useState('')
  const showingCurrentContact = scope === 'current' && Boolean(selectedContact)
  const visiblePending = showingCurrentContact
    ? pending.filter((item) => item.contact_id === selectedContact.contact_id)
    : pending

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
          <span className="eyebrow">人工确认</span>
          <h2>逐条检查，再决定是否发送</h2>
          <p>
            {showingCurrentContact
              ? `仅显示“${selectedContact.display_name}”的待确认回复。`
              : '左侧选择消息，右侧确认上下文、候选和最终发送文本。'}
          </p>
        </div>
        <div className="pending-header-actions">
          <div className="pending-scope" role="group" aria-label="待确认回复筛选">
            <button
              type="button"
              className={showingCurrentContact ? 'active' : ''}
              onClick={() => setScope('current')}
              disabled={!selectedContact}
            >
              当前会话
            </button>
            <button
              type="button"
              className={!showingCurrentContact ? 'active' : ''}
              onClick={() => setScope('all')}
            >
              全部会话
            </button>
          </div>
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
              ? `${selectedContact.display_name} 暂无待确认回复`
              : '队列已经清空'}
          </strong>
          <p>
            {showingCurrentContact && pending.length > 0
              ? '可以切换到“全部会话”查看其他联系人的待确认回复。'
              : '新的待确认回复会出现在这里，不会自动发送。'}
          </p>
          {showingCurrentContact && pending.length > 0 && (
            <button
              type="button"
              className="button secondary"
              onClick={() => setScope('all')}
            >
              查看全部会话
            </button>
          )}
        </div>
      ) : (
        <div className="pending-workbench-grid">
          <nav className="pending-inbox" aria-label="待确认消息">
            {visiblePending.map((item) => {
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

              <div className="pending-context-card">
                <span>对方最新消息</span>
                <p>{activeItem.incoming?.slice(-2).join('\n') || '无可用上下文'}</p>
              </div>

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
                    !(pendingDrafts[activeItem.id] || activeItem.candidate || '').trim()
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

export { PendingConfirmationList, PendingWorkbench }
