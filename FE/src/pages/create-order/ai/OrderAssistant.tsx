import { useEffect, useRef, useState } from 'react'
import { useT } from '../../../i18n'
import { ApiError } from '../../../services/api'
import {
  aiConversation, aiStatus, applyProposal, openProposals, redoSketch, redrawSketch, rejectProposal, selectionSize, sendAiMessage, staleReason, undoSketch,
  type AiEvent, type AiMessage, type AiSelection, type AiStatus, type EnsureOrder, type ReloadOrder, type SketchInfo } from '../../../services/orderAi'
import { errText, orderErrorKey } from '../../../services/orders'
import ProposalCard from './ProposalCard'

const TOOLS = new Set([
  'get_order', 'list_materials', 'list_templates', 'update_text', 'set_layout', 'choose_materials', 'set_options',
  'check_order', 'generate_sketch', 'get_sketch', 'edit_strokes', 'undo_sketch', 'redo_sketch', 'flag_for_staff',
])
/** Proposal pictures are loaded for the newest proposals only, so an old conversation does not fetch dozens of previews. */
const PICTURES = 3

const newRef = () => (typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`)

/**
 * The assistant of a draft order, at every step of Create Order. The customer types what to write or change; the assistant
 * answers with a proposal (what changes, the new price, the new sketch) and the order changes only when the customer applies it.
 * A message sent while a proposal is waiting adds to that proposal (the backend's default), unless the customer starts again
 * from the order. While a proposal waits, `onPending` tells the page to hold the form still.
 */
export default function OrderAssistant({ orderId, ensureOrder, sketch, canDraw, selection, onClearSelection, onChanged, onBusy, onPending }: {
  orderId: number | null
  /** The draft on the server; it is created when the first message is sent. */
  ensureOrder: EnsureOrder
  sketch: SketchInfo | null
  /** The order already has the text and the style, so the sketch can be drawn from them. */
  canDraw: boolean
  /** What the customer picked on the sketch (sent with the next message). */
  selection: AiSelection
  onClearSelection: () => void
  /** After a proposal is applied or the sketch is drawn again: load the order and the sketch again. */
  onChanged: ReloadOrder
  /** True while the assistant is working, so the rest of the form stays still. */
  onBusy: (busy: boolean) => void
  /** True while a proposal waits for the customer: the form stays locked until it is applied or skipped. */
  onPending: (pending: boolean) => void
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
  const [fromOrder, setFromOrder] = useState(false)
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

  const waiting = openProposals(messages)
  const hasWaiting = waiting.length > 0
  useEffect(() => {
    onPending(hasWaiting)
  }, [hasWaiting, onPending])
  useEffect(() => () => onPending(false), [onPending])
  // "Start again" only means something while a proposal waits.
  const again = fromOrder && hasWaiting

  /** The server decides what can still be applied (another proposal or a change of the form makes the others stale), so ask again. */
  const refresh = async (id: number) => {
    try {
      const c = await aiConversation(id)
      setMessages(c.messages)
      setConsented(c.consented)
    } catch {
      // The cards keep what they had; the next action loads them again.
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

  const send = async () => {
    const msg = text.trim()
    if (!msg || busy || (!consented && !agree)) return
    setPending(msg)
    setProgress([])
    await work(async () => {
      try {
        const id = await ensureOrder()
        const turn = await sendAiMessage(id, {
          text: msg,
          ai_consent: true,
          ...(sketch ? { base_revision_id: sketch.revisionId } : {}),
          ...(selectionSize(selection) ? { selection } : {}),
          ...(again ? { from_order: true } : {}),
          client_ref: newRef(),
        }, (e) => setProgress((p) => [...p, describe(e)]))
        loadedFor.current = id
        setMessages((m) => [...m, turn.user, turn.reply])
        setConsented(true)
        setText('')
        setFromOrder(false)
        onClearSelection()
        await refresh(id)
        await onChanged()
        aiStatus().then(setStatus).catch(() => undefined)
      } catch (e) {
        fail(e)
        if (e instanceof ApiError && e.code === 'STALE_REVISION') await onChanged().catch(() => undefined)
        // A proposal that went stale in the meantime: show the cards as the server now sees them.
        if (e instanceof ApiError && e.code.startsWith('PROPOSAL_') && orderId !== null) await refresh(orderId)
      }
    })
    setPending(null)
    setProgress([])
  }

  const decide = (kind: 'apply' | 'reject', id: number) => {
    if (orderId === null) return
    void work(async () => {
      try {
        if (kind === 'apply') await applyProposal(orderId, id)
        else await rejectProposal(orderId, id)
        setFromOrder(false)
        await refresh(orderId)
        if (kind === 'apply') await onChanged()
      } catch (e) {
        const why = staleReason(e)
        fail(e, why ? `oa.stale.${why}` : undefined)
        await refresh(orderId)
      }
    })
  }

  /**
   * Undo, redo or draw again (offered only while no proposal waits). Undo and redo also bring the form back to what it was when
   * that sketch was drawn, so the order is reloaded. When something would be lost the customer is asked first.
   */
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

  // The newest proposals with a sketch show their picture; so does every proposal that still waits.
  const withSketch = messages.filter((m) => m.proposal?.preview != null).map((m) => m.proposal!.id)
  const pictured = new Set([...withSketch.slice(-PICTURES), ...waiting.map((p) => p.id)])

  return (
    <section className="oa" aria-label={t('oa.title')}>
      <header className="oa-head">
        <b>{t('oa.title')}</b>
        {!!status?.limit && <span className="oa-quota vh-mono">{t('oa.quota', { left: status.left ?? 0, limit: status.limit })}</span>}
      </header>

      <div className="oa-list" ref={list} role="log" aria-live="polite" aria-label={t('oa.title')}>
        <p className="oa-msg oa-msg--bot">{t('oa.hello')}</p>
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
              {body && <p className={`oa-msg oa-msg--bot${m.status === 'FAILED' ? ' failed' : ''}`}>{body}</p>}
              {m.proposal && orderId !== null && (
                <ProposalCard
                  proposal={m.proposal}
                  busy={busy}
                  showPicture={pictured.has(m.proposal.id)}
                  continued={m.proposal.parentId !== null}
                  onApply={() => decide('apply', m.proposal!.id)}
                  onReject={() => decide('reject', m.proposal!.id)}
                />
              )}
            </div>
          )
        })}

        {pending && (
          <>
            <p className="oa-msg oa-msg--me">{pending}</p>
            <div className="oa-card oa-card--wait" aria-live="polite">
              {progress.length
                ? progress.map((x, i) => <span key={i} className="oa-fine">{x}</span>)
                : <span className="oa-fine">{t('oa.thinking')}</span>}
            </div>
          </>
        )}
      </div>

      <div className="oa-foot">
        {!hasWaiting && !sketch && canDraw && orderId !== null && (
          <div className="co-notice oa-stale-row" role="status">
            <span>{t('oa.noSketch')}</span>
            <button type="button" className="co-btn co-btn--solid co-btn--sm" disabled={busy} onClick={() => move('redraw')}>{t('oa.draw')}</button>
          </div>
        )}
        {!hasWaiting && sketch?.inputsChanged && (
          <div className="co-notice oa-stale-row" role="status">
            <span>{t('oa.outdated')}</span>
            <button type="button" className="co-btn co-btn--line co-btn--sm" disabled={busy || orderId === null} onClick={() => move('redraw')}>{t('oa.redraw')}</button>
          </div>
        )}
        {ask && (
          <div className="co-notice oa-stale-row" role="alert">
            <span>{t(`oa.ask.${ask}`)}</span>
            <button type="button" className="co-btn co-btn--line co-btn--sm" disabled={busy} onClick={() => move(ask, true)}>{t(`oa.askYes.${ask}`)}</button>
            <button type="button" className="co-btn co-btn--line co-btn--sm" disabled={busy} onClick={() => setAsk(null)}>{t('oa.cancel')}</button>
          </div>
        )}
        {!hasWaiting && sketch && (sketch.canUndo || sketch.canRedo) && (
          <div className="oa-history">
            <button type="button" className="co-btn co-btn--line co-btn--sm" disabled={busy || !sketch.canUndo} onClick={() => move('undo')}>{t('oa.undo')}</button>
            <button type="button" className="co-btn co-btn--line co-btn--sm" disabled={busy || !sketch.canRedo} onClick={() => move('redo')}>{t('oa.redo')}</button>
            <span className="oa-fine">{t('oa.historyHint')}</span>
          </div>
        )}

        {hasWaiting && (
          <div className="co-notice oa-stale-row" role="status">
            <span>{t(again ? 'oa.fromOrderOn' : 'oa.addsTo')}</span>
            <button type="button" className="co-btn co-btn--line co-btn--sm" disabled={busy} onClick={() => setFromOrder((v) => !v)}>
              {t(again ? 'oa.addToProposal' : 'oa.startAgain')}
            </button>
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
            {picked > 0 && (
              <div className="oa-picked" role="status">
                <span>{t('oa.picked', { n: picked })}</span>
                <button type="button" className="co-btn co-btn--line co-btn--sm" disabled={busy} onClick={onClearSelection}>{t('oa.clearPick')}</button>
              </div>
            )}
            <div className="oa-input">
              <textarea
                ref={input}
                className="co-text"
                rows={2}
                maxLength={2000}
                value={text}
                disabled={busy || outOfTurns}
                aria-label={t('oa.inputLabel')}
                placeholder={t(outOfTurns ? 'oa.noTurns' : picked ? 'oa.placeholderPicked' : hasWaiting && !again ? 'oa.placeholderMore' : 'oa.placeholder')}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    void send()
                  }
                }}
              />
              <button type="button" className="co-btn co-btn--solid" disabled={busy || !text.trim() || !canWrite} onClick={() => void send()}>
                {t(busy ? 'oa.sending' : 'oa.send')}
              </button>
            </div>
          </>
        )}
        {err && <p className="lg-error" role="alert">{errText(t, err)}</p>}
        {err && errInfo && <p className="oa-fine vh-mono">{errInfo}</p>}
      </div>
    </section>
  )
}
