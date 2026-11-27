import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import {
  ArrowClockwise, ArrowCounterClockwise, ArrowUp, CaretLeft, ChatCircleText, ChatsCircle, ClockCounterClockwise, NotePencil, PencilSimpleLine,
  Sparkle, Trash, X,
} from '@phosphor-icons/react'
import { useLocale, useT } from '../../../i18n'
import { ApiError } from '../../../services/api'
import {
  aiConversation, aiSessions, aiStatus, applyProposal, deleteAiSession, redoSketch, redrawSketch, rejectProposal, revertProposal,
  selectionSize, sendAiMessage, staleReason, undoSketch,
  type AiEvent, type AiMessage, type AiProposal, type AiSelection, type AiSession, type AiStatus, type EnsureOrder, type ReloadOrder,
  type SketchInfo,
} from '../../../services/orderAi'
import { errText, orderErrorKey } from '../../../services/orders'
import ProposalCard, { type ProposalAction } from './ProposalCard'
import RichText from './RichText'
import StaffChat from './StaffChat'
import ThinkingStage, { type StageFinish } from './ThinkingStage'

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
 *
 * Conversations (migration 0031): "New chat" clears the panel without calling the backend; the first message then goes with
 * `new_session` and the next ones with the `session_id` it returned. The history lists the order's conversations; a draft's can
 * be deleted. A new conversation does not remember the others but still sees the order as it is now.
 */
export default function OrderAssistant({ orderId, ensureOrder, sketch, selection, onClearSelection, onChanged, onBusy, onConsentNeeded }: {
  orderId: number | null
  /** The draft on the server; it is created when the first message is sent. */
  ensureOrder: EnsureOrder
  sketch: SketchInfo | null
  /** What the customer picked on the sketch (sent with the next message). */
  selection: AiSelection
  onClearSelection: () => void
  /** After an answer is applied or the sketch moves: load the order and the sketch again. */
  onChanged: ReloadOrder
  /** True while the assistant is working, so the rest of the form stays still. */
  onBusy: (busy: boolean) => void
  /** The backend asks for the data policy again (consent withdrawn or a new version): Create Order shows its dialog. */
  onConsentNeeded: () => void
}) {
  const t = useT()
  const locale = useLocale()
  const [status, setStatus] = useState<AiStatus | null>(null)
  const [messages, setMessages] = useState<AiMessage[]>([])
  /** The conversation on screen; `null` with `fresh` = a new chat that starts with the next message. */
  const [sessionId, setSessionId] = useState<number | null>(null)
  const [fresh, setFresh] = useState(false)
  const [sessions, setSessions] = useState<AiSession[]>([])
  /** Who the panel talks to: the assistant, or the workshop staff (the chats of the orders already sent). */
  const [who, setWho] = useState<'ai' | 'staff'>('ai')
  const [history, setHistory] = useState(false)
  const [doomed, setDoomed] = useState<number | null>(null)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [progress, setProgress] = useState<string[]>([])
  const [pending, setPending] = useState<string | null>(null)
  /** How the turn on screen ended; the thinking stage plays its ending and then calls back. */
  const [stageEnd, setStageEnd] = useState<StageFinish>(null)
  const stageDone = useRef<(() => void) | null>(null)
  const stageOn = useRef(false)
  /** The answer that just arrived: held back while the stage plays its ending (`holdId`), then unfolded word by word (`freshId`). */
  const [holdId, setHoldId] = useState<number | string | null>(null)
  const [freshId, setFreshId] = useState<number | string | null>(null)
  /** True once the sent message is in `messages`, so the "sending" bubble gives way to it. */
  const [echoed, setEchoed] = useState(false)
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
        setSessionId(c.sessionId)
      })
      .catch((e) => live && fail(e))
    aiSessions(orderId).then((l) => live && setSessions(l)).catch(() => undefined)
    return () => {
      live = false
    }
  }, [orderId])

  useEffect(() => {
    list.current?.scrollTo({ top: list.current.scrollHeight, behavior: 'smooth' })
  }, [messages.length, progress.length, pending, freshId])

  // The message box is one line and grows with what is typed.
  useLayoutEffect(() => {
    const el = input.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, MAX_INPUT_PX)}px`
  }, [text])

  const refresh = async (id: number, sid: number | null = sessionId) => {
    try {
      const c = await aiConversation(id, sid)
      setMessages(c.messages)
      setSessionId(c.sessionId)
    } catch {
      // The messages keep what they had; the next action loads them again.
    }
    aiSessions(id).then(setSessions).catch(() => undefined)
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
    if (!msg || busy) return
    setPending(msg)
    setProgress([])
    setFreshId(null)
    setHoldId(null)
    setEchoed(false)
    let answered: number | string | null = null
    await work(async () => {
      let id: number | null = orderId
      let sid: number | null = fresh ? null : sessionId
      try {
        id = await ensureOrder()
        const turn = await sendAiMessage(id, {
          text: msg,
          ...(sketch ? { base_revision_id: sketch.revisionId } : {}),
          ...(selectionSize(selection) ? { selection } : {}),
          from_order: true,
          ...(fresh || sessionId === null ? (fresh ? { new_session: true } : {}) : { session_id: sessionId }),
          client_ref: newRef(),
        }, (e) => setProgress((p) => [...p, describe(e)]))
        loadedFor.current = id
        sid = turn.sessionId
        setSessionId(sid)
        setFresh(false)
        if (stageOn.current) setHoldId(turn.reply.id)
        setEchoed(true)
        setMessages((m) => [...m, turn.user, turn.reply])
        setText('')
        onClearSelection()
        // An answer that only changes what Undo brings back goes straight onto the order (the sketch box shows it now). One that
        // changes more, or draws over the customer's own edits, waits on its card for Apply or Skip.
        const p = turn.proposal
        if (p && p.status === 'PENDING' && p.applicable && !p.needsConfirmation) {
          setProgress((x) => [...x, t('oa.applying')])
          try {
            await applyProposal(id, p.id)
          } catch (e) {
            const why = staleReason(e)
            fail(e, why ? `oa.stale.${why}` : undefined)
          }
        }
        await refresh(id, sid)
        await onChanged()
        aiStatus().then(setStatus).catch(() => undefined)
        answered = turn.reply.id
      } catch (e) {
        if (e instanceof ApiError && e.code === 'AI_CONSENT_REQUIRED') {
          // Consent withdrawn elsewhere or a new policy version: the dialog asks again, the typed text stays.
          onConsentNeeded()
          return
        }
        fail(e)
        if (e instanceof ApiError && e.code === 'STALE_REVISION') await onChanged().catch(() => undefined)
        // A refused first message of a new chat leaves the new chat open.
        if (id !== null && sid !== null) await refresh(id, sid)
      }
    })
    // The stage plays its ending (green, then the ball settles on the avatar) before the answer unfolds; never longer than 4 s.
    if (stageOn.current) {
      setStageEnd(answered !== null ? 'ok' : 'fail')
      await new Promise<void>((done) => {
        const timer = window.setTimeout(done, 4000)
        stageDone.current = () => {
          window.clearTimeout(timer)
          done()
        }
      })
      stageDone.current = null
    }
    setStageEnd(null)
    setHoldId(null)
    setFreshId(answered)
    setPending(null)
    setProgress([])
  }

  /** Apply or skip a waiting answer, or take an applied one back; then the order and the sketch are loaded again. */
  const decide = (action: ProposalAction, p: AiProposal) => {
    if (orderId === null) return
    void work(async () => {
      try {
        if (action === 'apply') await applyProposal(orderId, p.id)
        else if (action === 'skip') await rejectProposal(orderId, p.id)
        else await revertProposal(orderId, p.id)
      } catch (e) {
        const why = staleReason(e)
        fail(e, why ? `oa.stale.${why}` : undefined)
      }
      await refresh(orderId)
      await onChanged()
    })
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

  /** A new chat: the panel is cleared now, the conversation is created with the next message. */
  const newChat = () => {
    setHistory(false)
    setDoomed(null)
    setMessages([])
    setSessionId(null)
    setFresh(true)
    setErr('')
    setText('')
    input.current?.focus()
  }

  const openSession = (sid: number) => {
    if (orderId === null) return
    setHistory(false)
    setDoomed(null)
    setFresh(false)
    void work(() => refresh(orderId, sid))
  }

  const removeSession = (sid: number) => {
    if (orderId === null) return
    void work(async () => {
      try {
        await deleteAiSession(orderId, sid)
        setDoomed(null)
        setSessions((l) => l.filter((x) => x.id !== sid))
        if (sid === sessionId) {
          setMessages([])
          setSessionId(null)
          setFresh(true)
        }
      } catch (e) {
        fail(e)
      }
    })
  }

  const clock = (iso: string) => new Date(iso).toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' })
  const when = (iso: string) => new Date(iso).toLocaleString(locale, { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
  const current = sessions.find((x) => x.id === sessionId)
  const chatName = fresh || (!current && !messages.length) ? t('oa.newChat') : current?.title || t('oa.untitled')

  const unavailable = status !== null && !status.available
  const outOfTurns = status?.left === 0
  const canWrite = !unavailable && !outOfTurns
  const picked = selectionSize(selection)
  const staff = who === 'staff'
  const staged = !!pending && !staff && !history
  useEffect(() => {
    stageOn.current = staged
  })

  return (
    <section className="oa" aria-label={t('oa.title')}>
      <header className="oa-head">
        <span className="oa-avatar" aria-hidden="true">{staff ? <ChatsCircle weight="fill" /> : <Sparkle weight="fill" />}</span>
        <div className="oa-head-text">
          <b>{t(staff ? 'cd.title' : 'oa.title')}</b>
          {staff ? <span>{t('cd.sub')}</span> : <span title={chatName}>{chatName}</span>}
        </div>
        <div className="oa-tools" hidden={staff}>
          {sketch && orderId !== null && (
            <>
              <button type="button" className="oa-tool" disabled={busy || !sketch.canUndo} title={t('oa.undoHint')} onClick={() => move('undo')}>
                <ArrowCounterClockwise aria-hidden="true" weight="bold" /><span className="oa-sr">{t('oa.undo')}</span>
              </button>
              <button type="button" className="oa-tool" disabled={busy || !sketch.canRedo} title={t('oa.redo')} onClick={() => move('redo')}>
                <ArrowClockwise aria-hidden="true" weight="bold" /><span className="oa-sr">{t('oa.redo')}</span>
              </button>
              <span className="oa-tools-sep" aria-hidden="true" />
            </>
          )}
          {orderId !== null && (
            <button type="button" className={`oa-tool${history ? ' on' : ''}`} aria-expanded={history} title={t('oa.history')} disabled={busy}
              onClick={() => { setHistory((h) => !h); setDoomed(null) }}>
              <ClockCounterClockwise aria-hidden="true" weight="bold" /><span className="oa-sr">{t('oa.history')}</span>
            </button>
          )}
          <button type="button" className="oa-tool oa-tool--new" title={t('oa.newChat')} disabled={busy || unavailable || (fresh && !messages.length) || (!messages.length && sessionId === null)}
            onClick={newChat}>
            <NotePencil aria-hidden="true" weight="bold" /><span className="oa-tool-label">{t('oa.newChat')}</span>
          </button>
        </div>
      </header>

      <div className="oa-who" role="radiogroup" aria-label={t('oa.chatWith')}>
        <button type="button" role="radio" aria-checked={!staff} className={staff ? '' : 'on'} onClick={() => setWho('ai')}>
          <Sparkle aria-hidden="true" weight="fill" />{t('oa.title')}
        </button>
        <button type="button" role="radio" aria-checked={staff} className={staff ? 'on' : ''} onClick={() => { setWho('staff'); setHistory(false); setDoomed(null) }}>
          <ChatsCircle aria-hidden="true" weight="fill" />{t('oa.staffTab')}
        </button>
      </div>

      {staff ? (
        <StaffChat />
      ) : history ? (
        <div className="oa-history" role="region" aria-label={t('oa.history')}>
          <div className="oa-history-head">
            <button type="button" className="oa-tool" title={t('oa.back')} onClick={() => { setHistory(false); setDoomed(null) }}>
              <CaretLeft aria-hidden="true" weight="bold" /><span className="oa-sr">{t('oa.back')}</span>
            </button>
            <b>{t('oa.history')}</b>
            <span className="oa-fine">{t('oa.sessionsN', { n: sessions.length })}</span>
          </div>
          {sessions.length ? (
            <ul className="oa-sessions">
              {sessions.map((x) => (
                <li key={x.id} className={`oa-session${x.id === sessionId && !fresh ? ' on' : ''}`}>
                  {doomed === x.id ? (
                    <div className="oa-session-ask" role="alert">
                      <span>{t('oa.delConfirm')}</span>
                      <div className="oa-session-ask-btns">
                        <button type="button" className="oa-btn oa-btn--line" disabled={busy} onClick={() => setDoomed(null)}>{t('oa.cancel')}</button>
                        <button type="button" className="oa-btn oa-btn--danger" disabled={busy} onClick={() => removeSession(x.id)}>{t('oa.delYes')}</button>
                      </div>
                    </div>
                  ) : (
                    <>
                      <button type="button" className="oa-session-open" disabled={busy} onClick={() => openSession(x.id)}>
                        <ChatCircleText aria-hidden="true" className="oa-session-icon" />
                        <span className="oa-session-text">
                          <b>{x.title || t('oa.untitled')}</b>
                          {x.preview && <span>{x.preview}</span>}
                          <small>{when(x.lastMessageAt ?? x.createdAt)} · {t('oa.messagesN', { n: x.messageCount })}</small>
                        </span>
                      </button>
                      {x.canDelete && (
                        <button type="button" className="oa-tool" title={t('oa.del')} disabled={busy} onClick={() => setDoomed(x.id)}>
                          <Trash aria-hidden="true" /><span className="oa-sr">{t('oa.del')}</span>
                        </button>
                      )}
                    </>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className="oa-history-empty">{t('oa.historyEmpty')}</p>
          )}
          <button type="button" className="oa-btn oa-btn--line oa-history-new" disabled={busy || unavailable} onClick={newChat}>
            <NotePencil aria-hidden="true" weight="bold" />{t('oa.newChat')}
          </button>
        </div>
      ) : (
      <div className="oa-list" ref={list} role="log" aria-live="polite" aria-label={t('oa.title')}>
        {!messages.length && !pending && (
          <div className="oa-hero">
            <b className="oa-hero-title">{t(fresh ? 'oa.newChat' : 'oa.emptyTitle')}</b>
            {fresh && <span className="oa-fine">{t('oa.newChatHint')}</span>}
          </div>
        )}
        <div className="oa-row">
          <span className="oa-avatar oa-avatar--sm" aria-hidden="true"><Sparkle weight="fill" /></span>
          <div className="oa-col">
            <div className="oa-by"><b>{t('oa.title')}</b></div>
            <div className="oa-msg oa-msg--bot"><p>{t('oa.hello')}</p></div>
          </div>
        </div>
        {!messages.length && !pending && !unavailable && (
          <div className="oa-try">
            {[1, 2].map((n) => (
              <button key={n} type="button" className="oa-suggest" disabled={busy} onClick={() => { setText(t(`oa.ex.${n}`)); input.current?.focus() }}>
                <PencilSimpleLine aria-hidden="true" className="oa-suggest-icon" />
                <span>{t(`oa.ex.${n}`)}</span>
              </button>
            ))}
          </div>
        )}

        {messages.map((m) => {
          if (m.role === 'USER') {
            return (
              <div key={m.id} className="oa-row oa-row--me">
                <div className="oa-col">
                  <div className="oa-by"><span className="oa-time">{clock(m.createdAt)}</span><b>{t('oa.you')}</b></div>
                  <p className="oa-msg oa-msg--me">{m.content}</p>
                </div>
              </div>
            )
          }
          if (m.id === holdId) return null
          const body = m.status === 'FAILED' && !m.content ? t('oa.failed') : m.content
          return (
            <div key={m.id} className={`oa-row${m.id === freshId ? ' oa-row--fresh' : ''}`}>
              <span className="oa-avatar oa-avatar--sm" aria-hidden="true"><Sparkle weight="fill" /></span>
              <div className="oa-col oa-turn">
                <div className="oa-by"><b>{t('oa.title')}</b><span className="oa-time">{clock(m.createdAt)}</span></div>
                {body && <div className={`oa-msg oa-msg--bot${m.status === 'FAILED' ? ' failed' : ''}`}><RichText text={body} reveal={m.id === freshId} /></div>}
                {m.proposal && <ProposalCard proposal={m.proposal} busy={busy} onAction={canWrite ? decide : undefined} />}
              </div>
            </div>
          )
        })}

        {pending && !echoed && (
          <div className="oa-row oa-row--me oa-row--sent">
            <div className="oa-col">
              <div className="oa-by"><b>{t('oa.you')}</b></div>
              <p className="oa-msg oa-msg--me">{pending}</p>
            </div>
          </div>
        )}
        {pending && (
          <ThinkingStage
            label={progress[progress.length - 1] ?? null}
            labels={[t('oa.thinking'), t('oa.think.search'), t('oa.think.analyze'), t('oa.think.compose')]}
            doneLabel={t('oa.done')}
            finish={stageEnd}
            onFinished={() => stageDone.current?.()}
          />
        )}
      </div>
      )}

      <div className="oa-foot" hidden={staff}>
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
              </div>
              <div className="oa-bar">
                {!!status?.limit && <span className="oa-quota">{t('oa.quota', { left: status.left ?? 0, limit: status.limit })}</span>}
                <button type="button" className="oa-send" aria-label={t(busy ? 'oa.sending' : 'oa.send')} title={t(busy ? 'oa.sending' : 'oa.send')}
                  disabled={busy || !text.trim() || !canWrite} onClick={() => void send()}>
                  <ArrowUp aria-hidden="true" weight="bold" />
                </button>
              </div>
            </div>
          </>
        )}
        {err && <p className="lg-error" role="alert">{errText(t, err)}</p>}
        {err && errInfo && <p className="oa-fine vh-mono">{errInfo}</p>}
      </div>
    </section>
  )
}
