import { PaperPlaneRight, Sparkle, Wrench } from '@phosphor-icons/react'
import { useEffect, useRef, useState } from 'react'
import { useAsync } from '../../hooks/useAsync'
import { useT } from '../../i18n'
import { errText, orderErrorKey } from '../../services/orders'
import {
  getAssistantStatus, getDraftMessages, sendDraftMessage, type ChatMessage, type Draft,
} from '../../services/studio'

/** The backend may answer with simple markdown; show it as plain text. */
const plain = (s: string) => s.replace(/\*\*(.+?)\*\*/g, '$1').replace(/^#+\s*/gm, '')

/** AI assistant of a draft. It only changes the draft through the backend's tools, and every change is a revision the customer can undo. */
export default function Assistant({ draft, onDraft }: { draft: Draft; onDraft: (d: Draft) => void }) {
  const t = useT()
  const status = useAsync(getAssistantStatus, [])
  const history = useAsync(() => getDraftMessages(draft.id), [draft.id])
  const [local, setLocal] = useState<ChatMessage[]>([])
  const [text, setText] = useState('')
  const [consent, setConsent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const end = useRef<HTMLDivElement>(null)

  const shown = [...(history.data ?? []), ...local.filter((m) => !(history.data ?? []).some((h) => h.id === m.id))]
  const open = draft.status === 'OPEN'
  const off = !!status.data && (!status.data.enabled || !status.data.available)
  const left = status.data?.messagesLeftToday ?? 1
  const needConsent = !shown.some((m) => m.role.toUpperCase() === 'USER')

  useEffect(() => {
    end.current?.scrollIntoView({ block: 'nearest' })
  }, [shown.length])

  const send = async () => {
    const msg = text.trim()
    if (!msg || busy) return
    setBusy(true)
    setErr('')
    try {
      const r = await sendDraftMessage(draft.id, msg, consent || !needConsent)
      setLocal((l) => [...l, r.user, r.reply])
      setText('')
      onDraft(r.draft)
      void status.reload()
    } catch (e) {
      setErr(orderErrorKey(e))
      void status.reload()
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="stu-card" aria-labelledby="stu-ai-h">
      <header className="stu-card-head">
        <Sparkle size={20} aria-hidden />
        <div>
          <h2 id="stu-ai-h" className="stu-h2">{t('stu.ai.title')}</h2>
          <p className="stu-hint">{t('stu.ai.sub')}</p>
        </div>
      </header>

      {off ? (
        <p className="stu-note" role="status">{t('stu.ai.off')}</p>
      ) : (
        <>
          <div className="stu-chat" role="log" aria-live="polite" aria-label={t('stu.ai.title')}>
            {history.loading && !history.data && <p className="stu-hint">{t('stu.loading')}</p>}
            {!history.loading && !shown.length && <p className="stu-hint">{t('stu.ai.empty')}</p>}
            {shown.map((m) => {
              const mine = m.role.toUpperCase() === 'USER'
              return (
                <div key={m.id} className={`stu-msg${mine ? ' me' : ''}${m.status === 'FAILED' ? ' failed' : ''}`}>
                  <b className="stu-msg-who">{t(mine ? 'stu.ai.you' : 'stu.ai.bot')}</b>
                  <p>{m.status === 'FAILED' && !m.content ? t('stu.ai.failed') : plain(m.content)}</p>
                  {!!m.toolCalls.length && (
                    <span className="stu-msg-tools"><Wrench size={14} aria-hidden />{t('stu.ai.tools', { n: m.toolCalls.filter((c) => c.ok).length })}</span>
                  )}
                </div>
              )
            })}
            <div ref={end} />
          </div>

          {status.data && <p className="stu-hint">{t('stu.ai.left', { n: status.data.messagesLeftToday, total: status.data.dailyMessageLimit })}</p>}
          {!!err && <p className="stu-error" role="alert">{errText(t, err)}</p>}

          {open && (
            <>
              {needConsent && (
                <label className="stu-check">
                  <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
                  <span>{t('stu.ai.consent')}</span>
                </label>
              )}
              <form className="stu-chat-form" onSubmit={(e) => { e.preventDefault(); void send() }}>
                <textarea
                  className="stu-input"
                  rows={2}
                  maxLength={2000}
                  value={text}
                  aria-label={t('stu.ai.phShown')}
                  placeholder={t('stu.ai.ph')}
                  disabled={busy || left <= 0}
                  onChange={(e) => setText(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void send() } }}
                />
                <button type="submit" className="co-btn co-btn--solid co-btn--sm" disabled={busy || !text.trim() || left <= 0 || (needConsent && !consent)}>
                  <PaperPlaneRight size={16} aria-hidden />{t(busy ? 'stu.ai.sending' : 'stu.ai.send')}
                </button>
              </form>
            </>
          )}
        </>
      )}
    </section>
  )
}
