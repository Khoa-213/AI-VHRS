import { useEffect, useRef, useState } from 'react'
import { useT } from '../../../i18n'
import { ApiError } from '../../../services/api'
import {
  assistantStatus, conversation, proposalOf, sendTurn,
  type AssistantMessage, type AssistantStatus, type StreamEvent } from '../../../services/assistant'
import { errText, orderErrorKey } from '../../../services/orders'
import { sketchPreviewUrl, type Selection } from '../../../services/sketch'

/** One proposal picture, loaded with the Bearer header. */
function ProposalImage({ orderId, revisionId }: { orderId: number; revisionId: number }) {
  const t = useT()
  const [src, setSrc] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    let made: string | null = null
    let live = true
    sketchPreviewUrl(orderId, revisionId)
      .then((u) => {
        made = u
        if (live) setSrc(u)
        else URL.revokeObjectURL(u)
      })
      .catch(() => live && setFailed(true))
    return () => {
      live = false
      if (made) URL.revokeObjectURL(made)
    }
  }, [orderId, revisionId])
  if (failed) return <div className="sk-card-img sk-card-img--empty">{t('sk.ai.imgFailed')}</div>
  if (!src) return <div className="sk-card-img sk-card-img--empty" aria-busy="true">{t('sk.ai.imgLoading')}</div>
  return <img className="sk-card-img" src={src} alt={t('sk.ai.imgAlt')} />
}

const newRef = () => (typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`)

/**
 * The assistant, beside the canvas. Every request comes back as a proposal card ("Version n") with its picture and two
 * actions: continue editing from it, or apply it to the canvas. The canvas never changes until the customer applies.
 */
export default function AssistantPanel({ orderId, applied, cursor, selection, selectionLabel, reachable, onBeforeSend, onApply, onTurn, onClose, onProposals }: {
  orderId: number
  /** Revision on the canvas. */
  applied: number | null
  /** Backend's current revision. */
  cursor: number | null
  selection: Selection | null
  selectionLabel: string
  reachable: (revisionId: number) => boolean
  /** Puts the backend cursor on `base` before a message is sent from it. */
  onBeforeSend(base: number): Promise<void>
  onApply: (revisionId: number) => void
  /** After a turn: reload the revision list; `orderChanged` when the assistant changed the order's text or materials. */
  onTurn: (orderChanged: boolean) => void
  onClose: () => void
  /** The proposal revisions in conversation order, so the canvas can name the applied one "Version n" too. */
  onProposals: (ids: number[]) => void
}) {
  const t = useT()
  const [status, setStatus] = useState<AssistantStatus | null>(null)
  const [messages, setMessages] = useState<AssistantMessage[]>([])
  const [consented, setConsented] = useState(false)
  const [agreeing, setAgreeing] = useState(false)
  const [text, setText] = useState('')
  const [base, setBase] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [progress, setProgress] = useState<string[]>([])
  const [pending, setPending] = useState<string | null>(null)
  const [err, setErr] = useState('')
  const input = useRef<HTMLTextAreaElement>(null)
  const list = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let live = true
    assistantStatus().then((s) => live && setStatus(s)).catch(() => live && setStatus({ enabled: false, available: false, left: null, limit: null }))
    conversation(orderId)
      .then((c) => {
        if (!live) return
        setMessages(c.messages)
        setConsented(c.consented)
      })
      .catch((e) => live && setErr(orderErrorKey(e)))
    return () => {
      live = false
    }
  }, [orderId])

  useEffect(() => {
    list.current?.scrollTo({ top: list.current.scrollHeight, behavior: 'smooth' })
  }, [messages.length, progress.length, pending])

  // Proposal numbers follow the conversation order.
  const proposals: number[] = []
  for (const m of messages) {
    const p = m.role === 'assistant' ? proposalOf(m) : null
    if (p && !proposals.includes(p)) proposals.push(p)
  }
  const latest = proposals[proposals.length - 1] ?? null
  const key = proposals.join(',')
  useEffect(() => {
    onProposals(key ? key.split(',').map(Number) : [])
  }, [key]) // eslint-disable-line react-hooks/exhaustive-deps
  const from = base ?? cursor
  const fromName = from === null ? '' : proposals.includes(from) ? t('sk.ai.version', { n: proposals.indexOf(from) + 1 }) : from === applied ? t('sk.ai.canvasVersion') : t('sk.ai.current')

  const describe = (e: StreamEvent): string =>
    e.type === 'provider' ? t('sk.ai.asking', { provider: e.provider })
      : e.type === 'failover' ? t('sk.ai.failover', { provider: e.provider })
        : t(e.ok ? 'sk.ai.toolOk' : 'sk.ai.toolFail', { tool: e.name })

  const send = async () => {
    const msg = text.trim()
    if (!msg || busy || from === null) return
    setErr('')
    setBusy(true)
    setPending(msg)
    setProgress([])
    try {
      await onBeforeSend(from)
      const turn = await sendTurn(orderId, {
        text: msg,
        ai_consent: true,
        base_revision_id: from,
        ...(selection ? { selection } : {}),
        client_ref: newRef(),
      }, (e) => setProgress((p) => [...p, describe(e)]))
      setMessages((m) => [...m, turn.user, turn.reply])
      setConsented(true)
      setText('')
      setBase(null)
      const changedOrder = turn.reply.toolCalls.some((c) => c.ok && !c.revisionId && !/^(get_|read_|check|list_)/.test(c.name))
      onTurn(changedOrder)
      assistantStatus().then(setStatus).catch(() => undefined)
    } catch (e) {
      setErr(e instanceof ApiError && e.code === 'UNREACHABLE' ? 'sk.err.unreachable' : orderErrorKey(e))
    } finally {
      setBusy(false)
      setPending(null)
      setProgress([])
    }
  }

  const unavailable = status !== null && !status.available
  const outOfTurns = status?.left === 0
  const needConsent = !consented && !agreeing

  return (
    <aside className="sk-ai" aria-label={t('sk.ai.title')}>
      <div className="sk-ai-head">
        <span className="sk-ai-dot" aria-hidden="true" />
        <b>{t('sk.ai.title')}</b>
        {status?.limit ? <span className="sk-ai-quota">{t('sk.ai.quota', { left: status.left ?? 0, limit: status.limit })}</span> : null}
        <button type="button" className="sk-icon" aria-label={t('sk.ai.collapse')} title={t('sk.ai.collapse')} onClick={onClose}>⟩</button>
      </div>

      <div className="sk-ai-list" ref={list}>
        <p className="sk-msg sk-msg--ai">{t('sk.ai.hello')}</p>
        {messages.map((m) => {
          if (m.role === 'user') return <p key={m.id} className="sk-msg sk-msg--me">{m.content}</p>
          const p = proposalOf(m)
          if (!p) return <p key={m.id} className={`sk-msg sk-msg--ai${m.status === 'FAILED' ? ' failed' : ''}`}>{m.content}</p>
          const n = proposals.indexOf(p) + 1
          const isApplied = p === applied
          const isLatest = p === latest
          const canApply = !isApplied && reachable(p)
          return (
            <div key={m.id} className={`sk-card${isApplied ? ' applied' : ''}`}>
              <div className="sk-card-head">
                <b>{t('sk.ai.version', { n })}</b>
                {isApplied && <span className="sk-badge">{t('sk.ai.onCanvas')}</span>}
              </div>
              <ProposalImage orderId={orderId} revisionId={p} />
              {m.content && <p className="sk-card-text">{m.content}</p>}
              {isLatest && !isApplied && canApply && (
                <div className="sk-card-actions">
                  <button type="button" className="sk-btn" onClick={() => { setBase(p); input.current?.focus() }}>{t('sk.ai.continue')}</button>
                  <button type="button" className="sk-btn sk-btn--solid" onClick={() => onApply(p)}>{t('sk.ai.apply')}</button>
                </div>
              )}
              {isLatest && !isApplied && !canApply && <span className="sk-fine">{t('sk.ai.gone')}</span>}
              {!isLatest && !isApplied && (canApply
                ? <button type="button" className="sk-btn sk-btn--sm" onClick={() => onApply(p)}>{t('sk.ai.applyThis')}</button>
                : <span className="sk-fine">{t('sk.ai.gone')}</span>)}
            </div>
          )
        })}
        {pending && (
          <>
            <p className="sk-msg sk-msg--me">{pending}</p>
            <div className="sk-card sk-card--wait" aria-live="polite">
              {progress.length ? progress.map((x, i) => <span key={i} className="sk-fine">{x}</span>) : <span className="sk-fine">{t('sk.ai.thinking')}</span>}
              <div className="sk-card-img sk-card-img--empty" />
            </div>
          </>
        )}
      </div>

      <div className="sk-ai-foot">
        {unavailable ? (
          <p className="sk-fine">{t('sk.ai.unavailable')}</p>
        ) : needConsent ? (
          <div className="sk-consent">
            <b>{t('sk.ai.consentTitle')}</b>
            <p>{t('sk.ai.consent')}</p>
            <button type="button" className="sk-btn sk-btn--solid" onClick={() => setAgreeing(true)}>{t('sk.ai.agree')}</button>
          </div>
        ) : (
          <>
            <div className="sk-chips">
              {fromName && <span className="sk-chip">{t('sk.ai.from', { name: fromName })}</span>}
              {selectionLabel && <span className="sk-chip">{t('sk.ai.scope', { what: selectionLabel })}</span>}
            </div>
            <div className="sk-ai-input">
              <textarea
                ref={input}
                rows={2}
                value={text}
                maxLength={2000}
                disabled={busy || outOfTurns}
                aria-label={t('sk.ai.inputLabel')}
                placeholder={t(outOfTurns ? 'sk.ai.noTurns' : busy ? 'sk.ai.waiting' : 'sk.ai.placeholder')}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    void send()
                  }
                }}
              />
              <button type="button" className="sk-btn sk-btn--solid" disabled={busy || outOfTurns || !text.trim()} onClick={() => void send()}>{t('sk.ai.send')}</button>
            </div>
          </>
        )}
        {err && <p className="lg-error" role="alert">{errText(t, err)}</p>}
      </div>
    </aside>
  )
}
