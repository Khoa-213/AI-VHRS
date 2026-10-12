import { useEffect, useRef, useState } from 'react'
import SkipLink from '../../components/ui/SkipLink'
import PaperSheet from '../../components/ui/PaperSheet'
import ThemeToggle from '../../components/ui/ThemeToggle'
import { fontScale, fmt, depositOf } from '../../utils/format'
import { Link, navigate } from '../../router/router'
import { saveStaffOrder, useOrders, useStaffQueue } from '../../store/store'
import type { Order } from '../../types'
import {
  MODE_HEADING, MODE_LABEL, PASS_SCORE, REJECT_REASONS,
  checkTone, evaluate, recognitionRows, recognizedText,
} from './evaluate'
import './staff.css'
import './polish.css'

type Tab = 'pending' | 'accepted' | 'rejected'
const TABS: { id: Tab; label: string; status: Order['status'] }[] = [
  { id: 'pending', label: 'Pending', status: 'Pending' },
  { id: 'accepted', label: 'Accepted', status: 'Accepted' },
  { id: 'rejected', label: 'Rejected', status: 'Rejected' },
]
const STAFF = 'Minh · AI-VHRS Studio'
const STEPS = ['Input review', 'AI sketch and evaluation', 'Accepted']

type Stage = 'input' | 'sketch' | 'done'
const stageOf = (o: Order): Stage => (o.status === 'Pending' ? o.staffStage ?? 'input' : 'done')

export default function StaffConsole({ id }: { id?: string }) {
  const queue = useStaffQueue()
  const allOrders = useOrders()
  const [tab, setTab] = useState<Tab>('pending')
  const [selId, setSelId] = useState<string | null>(id ?? null)
  const [g, setG] = useState(1)
  const [rejecting, setRejecting] = useState(false)
  const [reasons, setReasons] = useState<string[]>([])
  const [zoom, setZoom] = useState(1)
  const [assignFor, setAssignFor] = useState<string | null>(null)
  const [ocr, setOcr] = useState<Record<string, string>>({})
  const timer = useRef<number | undefined>(undefined)
  useEffect(() => () => window.clearInterval(timer.current), [])

  // Opening an order from the dashboard lands on the tab it lives in.
  useEffect(() => {
    const o = id ? queue.find((x) => x.id === id) : undefined
    if (o) setTab(o.status.toLowerCase() as Tab)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  const inTab = (o: Order) => o.status.toLowerCase() === tab
  const list = queue.filter(inTab)
  const sel = queue.find((o) => o.id === selId) ?? queue.find((o) => o.status === 'Pending') ?? queue[0]
  const writing = allOrders.some((o) => o.status === 'Queued')

  const runGen = () => {
    window.clearInterval(timer.current)
    const t0 = Date.now()
    setG(0)
    timer.current = window.setInterval(() => {
      const p = Math.min(1, (Date.now() - t0) / 3200)
      setG(p)
      if (p >= 1) window.clearInterval(timer.current)
    }, 50)
  }

  const assignOrder = assignFor ? queue.find((o) => o.id === assignFor) : undefined
  const closeAssign = () => {
    setAssignFor(null)
    setTab('accepted')
  }

  const pick = (id: string) => {
    window.clearInterval(timer.current)
    setSelId(id)
    setRejecting(false)
    setReasons([])
    setZoom(1)
    setG(1)
  }

  return (
    <div className="sc">
      <SkipLink />
      <header className="vh-header sc-header">
        <div className="vh-header-inner">
          <div className="sc-brand">
            <Link to="/" className="vh-logo">AI-VHRS</Link>
            <span className="sc-badge">STUDIO</span>
          </div>
          <nav className="sc-nav" aria-label="Staff">
            <Link to="/staff">Dashboard</Link>
            <Link to="/staff/review" className="on" aria-current="page">Review</Link>
          </nav>
          <div className="sc-head-right">
            <span className={`sc-robot${writing ? ' busy' : ''}`}>FR3 #01 · {writing ? 'WRITING' : 'IDLE'}</span>
            <ThemeToggle className="vh-icon-btn" />
            <span className="sc-staff"><span className="vh-avatar">M</span>Minh · Staff</span>
          </div>
        </div>
      </header>

      <div className="sc-layout">
        <aside className="sc-rail" aria-label="Order queue">
          <div className="sc-tabs" role="tablist">
            {TABS.map((t) => (
              <button
                key={t.id}
                role="tab"
                aria-selected={tab === t.id}
                className={tab === t.id ? 'on' : ''}
                onClick={() => setTab(t.id)}
              >
                {t.label} <span className="vh-mono">{queue.filter((o) => o.status === t.status).length}</span>
              </button>
            ))}
          </div>
          <div className="sc-list">
            {list.map((o) => {
              const st = stageOf(o)
              return (
                <button key={o.id} className={`sc-item${o.id === sel?.id ? ' on' : ''}`} onClick={() => pick(o.id)}>
                  <span className="sc-item-top">
                    <span className="vh-mono sc-item-id">{o.id}</span>
                    <span className={`sc-mode sc-mode--${o.spec.mode}`}>{MODE_LABEL[o.spec.mode]}</span>
                  </span>
                  <span className="sc-item-title">{o.title}</span>
                  <span className="sc-item-bottom">
                    <span>{o.name || 'Customer'}</span>
                    <span className={`sc-state sc-state--${o.status === 'Accepted' ? (o.assignment ? 'assigned' : 'needs') : o.status.toLowerCase()}`}>
                      {o.status === 'Pending'
                        ? st === 'sketch' ? 'AI sketch' : 'Input review'
                        : o.status === 'Accepted'
                          ? o.assignment ? `Assigned · ${o.assignment.techName}` : 'Needs technician'
                          : o.status}
                    </span>
                  </span>
                </button>
              )
            })}
            {!list.length && <span className="sc-empty">Nothing here.</span>}
          </div>
        </aside>

        <main className="sc-main" id="main">
          {sel ? (
            <Detail
              key={sel.id}
              order={sel}
              g={g}
              zoom={zoom}
              onZoom={() => setZoom((z) => (z > 1 ? 1 : 2))}
              ocr={ocr[sel.id]}
              onOcr={(v) => setOcr((m) => ({ ...m, [sel.id]: v }))}
              rejecting={rejecting}
              onStartReject={() => {
                setRejecting(true)
                setReasons([])
              }}
              onCancelReject={() => setRejecting(false)}
              reasons={reasons}
              onToggleReason={(r) => setReasons((rs) => (rs.includes(r) ? rs.filter((x) => x !== r) : [...rs, r]))}
              onConfirmReject={() => {
                if (!reasons.length) return
                saveStaffOrder({ ...sel, status: 'Rejected', rejectReasons: reasons, staff: STAFF })
                setRejecting(false)
                setTab('rejected')
              }}
              onApproveInput={(text) => {
                saveStaffOrder({ ...sel, staffStage: 'sketch', ocrText: text })
                runGen()
              }}
              onAccept={(score) => {
                saveStaffOrder({ ...sel, status: 'Accepted', staffStage: undefined, staff: STAFF, evalScore: score })
                setAssignFor(sel.id)
              }}
              onRegen={() => {
                saveStaffOrder({ ...sel, regen: (sel.regen ?? 0) + 1 })
                runGen()
              }}
              onBack={() => {
                window.clearInterval(timer.current)
                saveStaffOrder({ ...sel, staffStage: 'input' })
                setG(1)
              }}
            />
          ) : (
            <div className="sc-none">Select an order from the queue.</div>
          )}
        </main>
      </div>

      {assignOrder && (
        <AssignPrompt
          order={assignOrder}
          onChoose={() => navigate(`/staff/assign/${encodeURIComponent(assignOrder.id)}`)}
          onLater={closeAssign}
        />
      )}
    </div>
  )
}

function AssignPrompt({ order, onChoose, onLater }: { order: Order; onChoose: () => void; onLater: () => void }) {
  const btn = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    btn.current?.focus()
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onLater()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onLater])

  return (
    <div className="sc-modal" onClick={onLater}>
      <div
        className="sc-modal-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="sc-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <span className="sc-modal-mark" aria-hidden="true" />
        <div className="sc-modal-head">
          <h2 id="sc-modal-title">Order accepted</h2>
          <p>
            {order.id} is accepted and the customer has been asked for the {fmt(depositOf(order.total))} deposit.
            Choose a technician and one of their robots to write it.
          </p>
        </div>
        <ul className="sc-modal-facts">
          <li><span>Order</span><b>{order.title}</b></li>
          <li><span>AI score</span><b>{order.evalScore !== undefined ? `${order.evalScore} / 100` : 'n/a'}</b></li>
        </ul>
        <div className="sc-modal-actions">
          <button ref={btn} className="vh-btn vh-btn--primary" onClick={onChoose}>Choose technician</button>
          <button className="vh-btn vh-btn--ghost vh-btn--sm" onClick={onLater}>Later</button>
        </div>
      </div>
    </div>
  )
}

interface DetailProps {
  order: Order
  g: number
  zoom: number
  onZoom: () => void
  ocr: string | undefined
  onOcr: (v: string) => void
  rejecting: boolean
  onStartReject: () => void
  onCancelReject: () => void
  reasons: string[]
  onToggleReason: (r: string) => void
  onConfirmReject: () => void
  onApproveInput: (text: string) => void
  onAccept: (score: number) => void
  onRegen: () => void
  onBack: () => void
}

function Detail(p: DetailProps) {
  const { order: o, g } = p
  const sp = o.spec
  const mode = sp.mode
  const stage = stageOf(o)
  const text = recognizedText(o, p.ocr)
  const rows = recognitionRows(o, text)
  const ev = evaluate(o, text)
  const stepIdx = { input: 0, sketch: 1, done: 2 }[stage]
  const accepted = o.status === 'Accepted'
  const chips = [
    ['Format', sp.type], ['Paper', sp.paper], ['Pen', sp.pen], ['Ink', sp.ink],
    ['Qty', String(sp.qty || 1)], ['Total', fmt(o.total)],
  ]
  const genStage =
    g < 0.3 ? 'Vectorizing input'
    : g < 0.6 ? 'Fitting single-line font'
    : g < 0.85 ? 'Planning 6-DoF trajectory'
    : 'Scoring with evaluation service'
  const pct = `${Math.round(g * 100)}%`
  const sketchHasImg = !!sp.img && mode !== 'text' && !text
  const sketchSpec = {
    ...sp,
    text: text || '—',
    img: sketchHasImg ? sp.img : null,
    font: mode === 'text' ? sp.font : "'Caveat', cursive",
  }
  const verdictOk = ev.overall >= PASS_SCORE

  return (
    <div className="sc-detail">
      <div className="sc-title-row">
        <div className="sc-title">
          <span className="sc-eyebrow">{o.id} · {o.name || 'Customer'} · {o.date}</span>
          <h1>{o.title}</h1>
        </div>
        <ol className="sc-steps" aria-label="Review progress">
          {STEPS.map((label, i) => (
            <li key={label} className={i < stepIdx ? 'done' : i === stepIdx ? 'now' : ''}>
              <i />
              <span>{label}</span>
            </li>
          ))}
        </ol>
      </div>

      <ul className="sc-chips">
        {chips.map(([k, v]) => (
          <li key={k}><span>{k}</span> {v}</li>
        ))}
      </ul>

      {stage === 'input' && (
        <div className="sc-cols">
          <section className="sc-block sc-block--wide">
            <div className="sc-block-head">
              <h2>{MODE_HEADING[mode]}</h2>
              <span className={`sc-mode sc-mode--${mode}`}>{MODE_LABEL[mode]}</span>
            </div>

            {mode === 'text' ? (
              <>
                <div className="sc-quote">{sp.text || '…'}</div>
                <div className="sc-paper-strip" style={{ background: sp.paperColor }}>
                  <span style={{ fontFamily: sp.font, color: sp.inkColor }}>{sp.text || '…'}</span>
                </div>
              </>
            ) : (
              <button type="button" className="sc-photo" onClick={p.onZoom} aria-label="Toggle zoom">
                {sp.img ? (
                  <div
                    className="sc-photo-img"
                    style={{ backgroundImage: `url("${sp.img}")`, transform: `scale(${p.zoom})` }}
                  />
                ) : (
                  <div
                    className="sc-photo-paper"
                    style={{
                      aspectRatio: sp.aspect,
                      background: mode === 'draw' ? '#f4eee0' : '#e9e2d2',
                      transform: `rotate(${mode === 'upload' ? -2.5 : 0}deg) scale(${p.zoom})`,
                      alignItems: mode === 'upload' ? 'flex-start' : 'center',
                    }}
                  >
                    <span>{sp.simText || '…'}</span>
                  </div>
                )}
                <span className="sc-photo-tag sc-photo-tag--tl">
                  {mode === 'upload' ? `CUSTOMER PHOTO · ${sp.fileName ?? 'upload'}` : 'CANVAS EXPORT · PNG'}
                </span>
                <span className="sc-photo-tag sc-photo-tag--br">{p.zoom > 1 ? '200% · click to fit' : 'Fit · click to zoom'}</span>
              </button>
            )}
          </section>

          <section className="sc-block sc-block--rail">
            <h2>Input recognition</h2>
            <div className="vh-rows sc-rows">
              {rows.map((r) => (
                <div key={r.k} className="vh-row">
                  <span>{r.k}</span>
                  <span className={`sc-tone sc-tone--${r.tone}${r.tone === 'mode' ? ` sc-mode--${mode}` : ''}`}>{r.v}</span>
                </div>
              ))}
            </div>

            {mode !== 'text' && (
              <div className="vh-stack" style={{ gap: 8 }}>
                <label className="vh-label" htmlFor="sc-ocr">
                  {mode === 'upload' ? 'Recognized text (OCR)' : 'Recognized text (from strokes)'}
                </label>
                <textarea
                  id="sc-ocr"
                  className="vh-textarea"
                  rows={4}
                  value={text}
                  onChange={(e) => p.onOcr(e.target.value)}
                />
                <span className="sc-hint">Correct the recognized text if needed. It guides the sketch.</span>
              </div>
            )}

            {!p.rejecting ? (
              <div className="sc-actions">
                <button className="vh-btn vh-btn--primary vh-btn--md" onClick={() => p.onApproveInput(text)}>
                  Approve input, generate sketch
                </button>
                <button className="vh-btn vh-btn--ghost vh-btn--md sc-danger" onClick={p.onStartReject}>
                  Reject
                </button>
              </div>
            ) : (
              <div className="sc-actions">
                <div className="sc-reasons" role="group" aria-label="Reject reasons">
                  {REJECT_REASONS[mode].map((r) => (
                    <button
                      key={r}
                      className={`sc-reason${p.reasons.includes(r) ? ' on' : ''}`}
                      aria-pressed={p.reasons.includes(r)}
                      onClick={() => p.onToggleReason(r)}
                    >
                      {r}
                    </button>
                  ))}
                </div>
                <div className="sc-row">
                  <button className="vh-btn vh-btn--ghost vh-btn--md" style={{ flex: 1 }} onClick={p.onCancelReject}>
                    Cancel
                  </button>
                  <button
                    className="vh-btn vh-btn--md sc-reject-confirm"
                    style={{ flex: 1.4 }}
                    disabled={!p.reasons.length}
                    onClick={p.onConfirmReject}
                  >
                    Reject and notify
                  </button>
                </div>
              </div>
            )}
          </section>
        </div>
      )}

      {stage === 'sketch' && (
        <div className="sc-cols">
          <section className="sc-block sc-block--wide sc-stage">
            <div className="sc-stage-well">
              <PaperSheet
                spec={sketchSpec}
                height={sp.land ? '50%' : '84%'}
                maxWidth="90%"
                fs={fontScale(text.length || 12)}
                shadow="0 30px 60px var(--sh-55)"
                reveal={g}
                style={{ position: 'relative' }}
              >
                {g < 1 && <div className="or-nib" style={{ left: `${(g * 100).toFixed(1)}%` }} aria-hidden="true" />}
              </PaperSheet>
            </div>
            {g < 1 && (
              <div className="or-progress">
                <div><span>{genStage}</span><span className="vh-mono">{pct}</span></div>
                <div className="or-bar"><div style={{ width: pct }} /></div>
              </div>
            )}
          </section>

          <section className="sc-block sc-block--rail">
            <div className="sc-block-head">
              <h2>System evaluation</h2>
              <span className="sc-hint">Evaluation service</span>
            </div>

            {g < 1 ? (
              <div className="sc-skeleton" aria-busy="true">
                {[0, 1, 2, 3, 4, 5].map((i) => <div key={i} />)}
              </div>
            ) : (
              <>
                <div className={`sc-verdict ${verdictOk ? 'ok' : 'warn'}`}>
                  <span className="vh-mono">{ev.overall}</span>
                  <div>
                    <b>{verdictOk ? 'Ready to write' : 'Review recommended'}</b>
                    <small>Overall score out of 100, threshold {PASS_SCORE}</small>
                  </div>
                </div>

                <div className="sc-checks">
                  {ev.checks.map((c) => (
                    <div key={c.k} className={`sc-check sc-check--${checkTone(c.value)}`}>
                      <div><span>{c.k}</span><span className="vh-mono">{c.value}%</span></div>
                      <i><b style={{ width: `${c.value}%` }} /></i>
                    </div>
                  ))}
                </div>

                <div className="vh-metrics">
                  <div className="vh-metric"><b>{ev.strokes}</b><span>Strokes</span></div>
                  <div className="vh-metric"><b>{ev.penLifts}</b><span>Pen lifts</span></div>
                  <div className="vh-metric"><b>{sp.mins || 4} min</b><span>Per piece</span></div>
                </div>

                <div className="sc-actions">
                  <button className="vh-btn vh-btn--primary vh-btn--md" onClick={() => p.onAccept(ev.overall)}>
                    Accept order, request deposit
                  </button>
                  <div className="sc-row">
                    <button className="vh-btn vh-btn--ghost vh-btn--md" style={{ flex: 1 }} onClick={p.onRegen}>
                      Regenerate
                    </button>
                    <button className="vh-btn vh-btn--ghost vh-btn--md" style={{ flex: 1 }} onClick={p.onBack}>
                      Back to input
                    </button>
                  </div>
                </div>
              </>
            )}
          </section>
        </div>
      )}

      {stage === 'done' && (
        <section className={`sc-done ${accepted ? (o.assignment ? 'assigned' : 'needs') : 'bad'}`}>
          <h2>
            {accepted
              ? o.assignment ? `Assigned to ${o.assignment.techName} on ${o.assignment.robotId}` : 'Accepted, needs a technician'
              : 'Rejected'}
          </h2>
          <p>
            {accepted
              ? `Score ${o.evalScore ?? 'n/a'} out of 100. The customer has been asked for the 30% deposit (${fmt(depositOf(o.total))}).${o.assignment ? '' : ' Choose who writes it.'}`
              : `Reasons: ${(o.rejectReasons ?? []).join(', ') || 'none recorded'}. The customer has been notified.`}
          </p>
          {accepted && (
            <Link to={`/staff/assign/${encodeURIComponent(o.id)}`} className={`vh-btn vh-btn--md sc-self-start ${o.assignment ? 'vh-btn--ghost' : 'vh-btn--primary'}`}>
              {o.assignment ? 'Change technician' : 'Assign a technician'}
            </Link>
          )}
        </section>
      )}
    </div>
  )
}
