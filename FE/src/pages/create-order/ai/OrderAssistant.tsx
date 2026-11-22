import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { ArrowClockwise, ArrowCounterClockwise, ArrowUp, X } from '@phosphor-icons/react'
import { useT } from '../../../i18n'
import { ApiError } from '../../../services/api'
import {
  aiConversation, aiStatus, applyProposal, redoSketch, redrawSketch, selectionSize, sendAiMessage, staleReason, undoSketch,
  type AiEvent, type AiMessage, type AiSelection, type AiStatus, type EnsureOrder, type ReloadOrder, type SketchInfo } from '../../../services/orderAi'
import { errText, orderErrorKey } from '../../../services/orders'
import ProposalCard from './ProposalCard'
import RichText from './RichText'

const TOOLS = new Set([
  'get_order', 'list_materials', 'list_templates', 'update_text', 'set_layout', 'choose_materials', 'set_options',
  'check_order', 'generate_sketch', 'get_sketch', 'edit_strokes', 'undo_sketch', 'redo_sketch', 'flag_for_staff',
])
/** The backend's limit for one message. */
const MAX_MESSAGE = 8000
/** The message box grows with the text up to this height, then scrolls. */
const MAX_INPUT_PX = 160

const newRef = () => (typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`)

/**
 * The assistant of a draft order, in the right column of Create Order at every step. The customer says what to write or
 * change; the backend answers with a proposal, which is applied at once (the customer asked for no Apply step), so the
 * sketch box beside the form shows the new sketch as soon as the answer arrives. Undo / redo in the header go back.
 * Every message starts from the order as it is (`from_order`), so a proposal left over from earlier is never built on.
 */
export default function OrderAssistant({ orderId, ensureOrder, sketch, canDraw, selection, onClearSelection, onChanged, onBusy, summary }: {
  orderId: number | null
  /** The draft on the server; it is created when the first message is sent. */
  ensureOrder: EnsureOrder
  sketch: SketchInfo | null
  /** The order already has the text and the style, so the sketch can be drawn from them. */
  canDraw: boolean
  /** What the customer picked on the sketch (sent with the next message). */
  selection: AiSelection
  onClearSelection: () => void
  /** After an answer is applied or the sketch moves: load the order and the sketch again. */
  onChanged: ReloadOrder
  /** True while the assistant is working, so the rest of the form stays still. */
  onBusy: (busy: boolean) => void
  /** The order's estimated price, shown under the title (the chat takes the estimate box's place). */
  summary?: ReactNode
}) {
  const t = useT()
  const [status, setStatus] = useState<AiStatus | null>(null)
  const [messages, setMessages] = useState<AiMessage[]>([])
  const [consented, setConsented] = useState(false)
  const [agree, setAgree] = useState(false)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [progress, setProgress] = useState<string[]>([])
  const [pending, setPending] = useState<string | null>(null)
  type Ask = 'undo' | 'redo' | 'redraw'
  const [ask, setAsk] = useState<Ask | null>(null)
  const [err, setErr] = useState('')
  // Dev only: the backend's status and code under the translated text, so a failure can be told apart.
  const [errInfo, setErrInfo] = useState('')
  const input = useRef<HTMLTextAreaElement>(null)
  const list = useRef<HTMLDivElement>(null)
  const loadedFor = useRef<number | null>(null)

  const fail = (e: unknown, key?: string) => {
    setErr(key ?? orderErrorKey(e))
    setErrInfo(import.meta.env.DEV && e instanceof ApiError ? `${e.status} ${e.code}` : '')
    if (import.meta.env.DEV) console.warn('[order-ai]', e)
  }

  useEffect(() => {
    let live = true
    aiStatus().then((s) => live && setStatus(s)).catch(() => live && setStatus({ enabled: false, available: false, left: null, limit: null }))
    return () => {
      live = false
    }
  }, [])

  // The conversation of a draft that already exists (the one just created in this panel is already on screen).
  useEffect(() => {
    if (orderId === null || loadedFor.current === orderId) return
    loadedFor.current = orderId
    let live = true
    aiConversation(orderId)
      .then((c) => {
        if (!live) return
        setMessages(c.messages)
        setConsented(c.consented)
      })
      .catch((e) => live && fail(e))
    return () => {
      live = false
    }
  }, [orderId])

  useEffect(() => {
    list.current?.scrollTo({ top: list.current.scrollHeight, behavior: 'smooth' })
  }, [messages.length, progress.length, pending])

  // The message box is one line and grows with what is typed.
  useLayoutEffect(() => {
    const el = input.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, MAX_INPUT_PX)}px`
  }, [text])

  const refresh = async (id: number) => {
    try {
      const c = await aiConversation(id)
      setMessages(c.messages)
      setConsented(c.consented)
    } catch {
      // The messages keep what they had; the next action loads them again.
    }
  }

  const work = async (job: ReloadOrder) => {
    setErr('')
    setErrInfo('')
    setBusy(true)
    onBusy(true)
    try {
      await job()
    } finally {
      setBusy(false)
      onBusy(false)
    }
  }

  const describe = (e: AiEvent): string =>
    e.type === 'failover'
      ? t('oa.failover')
      : t(e.ok ? 'oa.toolOk' : 'oa.toolFail', { tool: t(TOOLS.has(e.name) ? `oa.tool.${e.name}` : 'oa.tool.other') })

  const send = async (said?: string) => {
    const msg = (said ?? text).trim()
    if (!msg || busy || (!consented && !agree)) return
    setPending(msg)
    setProgress([])
    await work(async () => {
      let id: number | null = orderId
      try {
        id = await ensureOrder()
        const turn = await sendAiMessage(id, {
          text: msg,
          ai_consent: true,
          ...(sketch ? { base_revision_id: sketch.revisionId } : {}),
          ...(selectionSize(selection) ? { selection } : {}),
          from_order: true,
          client_ref: newRef(),
        }, (e) => setProgress((p) => [...p, describe(e)]))
        loadedFor.current = id
        setMessages((m) => [...m, turn.user, turn.reply])
        setConsented(true)
        setText('')
        onClearSelection()
        // The answer goes straight onto the order: the sketch box shows it now, Undo goes back.
        const p = turn.proposal
        if (p && p.status === 'PENDING' && p.applicable) {
          setProgress((x) => [...x, t('oa.applying')])
          try {
            await applyProposal(id, p.id)
          } catch (e) {
            const why = staleReason(e)
            fail(e, why ? `oa.stale.${why}` : undefined)
          }
        }
        await refresh(id)
        await onChanged()
        aiStatus().then(setStatus).catch(() => undefined)
      } catch (e) {
        fail(e)
        if (e instanceof ApiError && e.code === 'STALE_REVISION') await onChanged().catch(() => undefined)
        if (id !== null) await refresh(id)
      }
    })
    setPending(null)
    setProgress([])
  }

  /** Undo, redo or draw again. Undo and redo also bring the form back to that drawing, so the order is reloaded. */
  const move = (kind: Ask, discard = false) => {
    if (orderId === null) return
    void work(async () => {
      try {
        if (kind === 'undo') await undoSketch(orderId, discard)
        else if (kind === 'redo') await redoSketch(orderId, discard)
        else await redrawSketch(orderId, discard)
        setAsk(null)
        await refresh(orderId)
        await onChanged()
      } catch (e) {
        if (e instanceof ApiError && (e.code === 'UNDRAWN_INPUT_CHANGES' || e.code === 'SKETCH_HAS_EDITS')) setAsk(kind)
        else fail(e)
      }
    })
  }

  const unavailable = status !== null && !status.available
  const outOfTurns = status?.left === 0
  const needConsent = !consented
  const canWrite = !unavailable && !outOfTurns && (!needConsent || agree)
  const picked = selectionSize(selection)

  return (
    <section className="oa" aria-label={t('oa.title')}>
      <header className="oa-head">
        <b>{t('oa.title')}</b>
        {sketch && orderId !== null && (
          <div className="oa-tools">
            <button type="button" className="oa-tool" disabled={busy || !sketch.canUndo} title={t('oa.undoHint')} onClick={() => move('undo')}>
              <ArrowCounterClockwise aria-hidden="true" weight="bold" />{t('oa.undo')}
            </button>
            <button type="button" className="oa-tool" disabled={busy || !sketch.canRedo} title={t('oa.redo')} onClick={() => move('redo')}>
              <ArrowClockwise aria-hidden="true" weight="bold" />{t('oa.redo')}
            </button>
          </div>
        )}
      </header>
      {summary}

      <div className="oa-list" ref={list} role="log" aria-live="polite" aria-label={t('oa.title')}>
        <div className="oa-msg oa-msg--bot"><p>{t('oa.hello')}</p></div>
        {!messages.length && !pending && !unavailable && (
          <div className="oa-try">
            {[1, 2].map((n) => (
              <button key={n} type="button" className="co-example" disabled={busy} onClick={() => { setText(t(`oa.ex.${n}`)); input.current?.focus() }}>
                {t(`oa.ex.${n}`)}
              </button>
            ))}
          </div>
        )}

        {messages.map((m) => {
          if (m.role === 'USER') return <p key={m.id} className="oa-msg oa-msg--me">{m.content}</p>
          const body = m.status === 'FAILED' && !m.content ? t('oa.failed') : m.content
          return (
            <div key={m.id} className="oa-turn">
              {body && <div className={`oa-msg oa-msg--bot${m.status === 'FAILED' ? ' failed' : ''}`}><RichText text={body} /></div>}
              {m.proposal && <ProposalCard proposal={m.proposal} />}
            </div>
          )
        })}

        {pending && (
          <>
            <p className="oa-msg oa-msg--me">{pending}</p>
            <div className="oa-wait" aria-live="polite">
              <span className="oa-typing" aria-hidden="true"><i /><i /><i /></span>
              <span className="oa-fine">{progress[progress.length - 1] ?? t('oa.thinking')}</span>
            </div>
          </>
        )}
      </div>

      <div className="oa-foot">
        {!sketch && canDraw && orderId !== null && (
          <div className="oa-note" role="status">
            <span>{t('oa.noSketch')}</span>
            <button type="button" className="oa-link" disabled={busy} onClick={() => move('redraw')}>{t('oa.draw')}</button>
          </div>
        )}
        {sketch?.inputsChanged && (
          <div className="oa-note" role="status">
            <span>{t('oa.outdated')}</span>
            <button type="button" className="oa-link" disabled={busy || orderId === null} onClick={() => move('redraw')}>{t('oa.redraw')}</button>
          </div>
        )}
        {ask && (
          <div className="oa-note oa-note--warn" role="alert">
            <span>{t(`oa.ask.${ask}`)}</span>
            <button type="button" className="oa-link" disabled={busy} onClick={() => move(ask, true)}>{t(`oa.askYes.${ask}`)}</button>
            <button type="button" className="oa-link" disabled={busy} onClick={() => setAsk(null)}>{t('oa.cancel')}</button>
          </div>
        )}

        {unavailable ? (
          <p className="co-hint">{t('oa.unavailable')}</p>
        ) : (
          <>
            {needConsent && (
              <label className="oa-consent">
                <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} />
                <span><b>{t('oa.consentTitle')}.</b> {t('oa.consent')}</span>
              </label>
            )}
            <div className={`oa-composer${busy ? ' busy' : ''}`}>
              {picked > 0 && (
                <div className="oa-chips">
                  <span className="oa-chip" role="status">
                    {t('oa.picked', { n: picked })}
                    <button type="button" aria-label={t('oa.clearPick')} title={t('oa.clearPick')} disabled={busy} onClick={onClearSelection}><X aria-hidden="true" weight="bold" /></button>
                  </span>
                </div>
              )}
              <div className="oa-input">
                <textarea
                  ref={input}
                  rows={1}
                  maxLength={MAX_MESSAGE}
                  value={text}
                  disabled={busy || outOfTurns}
                  aria-label={t('oa.inputLabel')}
                  placeholder={t(outOfTurns ? 'oa.noTurns' : picked ? 'oa.placeholderPicked' : 'oa.placeholder')}
                  onChange={(e) => setText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                      e.preventDefault()
                      void send()
                    }
                  }}
                />
                <button type="button" className="oa-send" aria-label={t(busy ? 'oa.sending' : 'oa.send')} title={t(busy ? 'oa.sending' : 'oa.send')}
                  disabled={busy || !text.trim() || !canWrite} onClick={() => void send()}>
                  <ArrowUp aria-hidden="true" weight="bold" />
                </button>
              </div>
            </div>
            <div className="oa-meta">
              <span>{t('oa.enterHint')}</span>
              {!!status?.limit && <span className="vh-mono">{t('oa.quota', { left: status.left ?? 0, limit: status.limit })}</span>}
            </div>
          </>
        )}
        {err && <p className="lg-error" role="alert">{errText(t, err)}</p>}
        {err && errInfo && <p className="oa-fine vh-mono">{errInfo}</p>}
      </div>
    </section>
  )
}
