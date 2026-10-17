import { useEffect, useRef, useState } from 'react'
import { useT, useTn } from '../../i18n'
import SkipLink from '../../components/ui/SkipLink'
import PaperSheet from '../../components/ui/PaperSheet'
import ThemeToggle from '../../components/ui/ThemeToggle'
import LanguageToggle from '../../components/ui/LanguageToggle'
import { fontScale, fmt, depositOf } from '../../utils/format'
import { Link, navigate } from '../../router/router'
import { saveStaffOrder, useOrders, useStaffQueue } from '../../store/store'
import type { Order } from '../../types'
import {
  MODE_HEADING, MODE_LABEL, PASS_SCORE, REJECT_REASONS,
  checkTone, evaluate, recognitionRows, recognizedText,
} from './evaluate'
import StaffRail from './StaffRail'
import './dashboard.css'
import './staff.css'
import './polish.css'

type Tab = 'pending' | 'accepted' | 'rejected'
const TABS: { id: Tab; status: Order['status'] }[] = [
  { id: 'pending', status: 'Pending' },
  { id: 'accepted', status: 'Accepted' },
  { id: 'rejected', status: 'Rejected' },
]
const STAFF = 'Minh · AI-VHRS Studio'
const STEP_KEYS = ['sc.step.input', 'sc.step.sketch', 'sc.step.done']

type Stage = 'input' | 'sketch' | 'done'
const stageOf = (o: Order): Stage => (o.status === 'Pending' ? o.staffStage ?? 'input' : 'done')

export default function StaffConsole({ id }: { id?: string }) {
  const t = useT()
  const tn = useTn()
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
    <div className="sd sd--sc">
      <StaffRail active="review" />
      <div className="sc">
      <SkipLink />
      <header className="vh-header sc-header">
        <div className="vh-header-inner">
          <div className="sc-brand">
            <Link to="/" className="vh-logo">AI-VHRS</Link>
            <span className="sc-badge">{t('sc.badge')}</span>
          </div>
          <span className="sc-nav" />
          <div className="sc-head-right">
            <span className={`sc-robot${writing ? ' busy' : ''}`}>{t(writing ? 'sc.robotBusy' : 'sc.robotIdle')}</span>
            <ThemeToggle className="vh-icon-btn" />
            <LanguageToggle className="vh-icon-btn" />
            <span className="sc-staff"><span className="vh-avatar">M</span>{t('sc.staffName')}</span>
          </div>
        </div>
      </header>

      <div className="sc-layout">
        <aside className="sc-rail" aria-label={t('sc.queue')}>
          <div className="sc-tabs" role="tablist">
            {TABS.map((tb) => (
              <button
                key={tb.id}
                role="tab"
                aria-selected={tab === tb.id}
                className={tab === tb.id ? 'on' : ''}
                onClick={() => setTab(tb.id)}
              >
                {t(`sc.tab.${tb.id}`)} <span className="vh-mono">{queue.filter((o) => o.status === tb.status).length}</span>
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
                    <span className={`sc-mode sc-mode--${o.spec.mode}`}>{tn(MODE_LABEL[o.spec.mode])}</span>
                  </span>
                  <span className="sc-item-title">{tn(o.title)}</span>
                  <span className="sc-item-bottom">
                    <span>{o.name || t('common.customer')}</span>
                    <span className={`sc-state sc-state--${o.status === 'Accepted' ? (o.assignment ? 'assigned' : 'needs') : o.status.toLowerCase()}`}>
                      {o.status === 'Pending'
                        ? t(st === 'sketch' ? 'sc.aiSketch' : 'sc.inputReview')
                        : o.status === 'Accepted'
                          ? o.assignment ? t('sc.assignedTo', { name: o.assignment.techName }) : t('sc.needsTech')
                          : t(`status.${o.status}`)}
                    </span>
                  </span>
                </button>
              )
            })}
            {!list.length && <span className="sc-empty">{t('sc.empty')}</span>}
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
            <div className="sc-none">{t('sc.select')}</div>
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
    </div>
  )
}

function AssignPrompt({ order, onChoose, onLater }: { order: Order; onChoose: () => void; onLater: () => void }) {
  const t = useT()
  const tn = useTn()
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
          <h2 id="sc-modal-title">{t('sc.modalTitle')}</h2>
          <p>{t('sc.modalBody', { id: order.id, deposit: fmt(depositOf(order.total)) })}</p>
        </div>
        <ul className="sc-modal-facts">
          <li><span>{t('sc.modalOrder')}</span><b>{tn(order.title)}</b></li>
          <li><span>{t('sc.modalScore')}</span><b>{order.evalScore !== undefined ? `${order.evalScore} / 100` : t('sc.na')}</b></li>
        </ul>
        <div className="sc-modal-actions">
          <button ref={btn} className="vh-btn vh-btn--primary" onClick={onChoose}>{t('sc.choose')}</button>
          <button className="vh-btn vh-btn--ghost vh-btn--sm" onClick={onLater}>{t('sc.later')}</button>
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
  const t = useT()
  const tn = useTn()
  const { order: o, g } = p
  const sp = o.spec
  const mode = sp.mode
  const stage = stageOf(o)
  const text = recognizedText(o, p.ocr, t)
  const rows = recognitionRows(o, text, t, tn)
  const ev = evaluate(o, text)
  const stepIdx = { input: 0, sketch: 1, done: 2 }[stage]
  const accepted = o.status === 'Accepted'
  const chips = [
    [t('sc.chip.format'), tn(sp.type)], [t('sc.chip.paper'), tn(sp.paper)], [t('sc.chip.pen'), tn(sp.pen)], [t('sc.chip.ink'), tn(sp.ink)],
    [t('sc.chip.qty'), String(sp.qty || 1)], [t('sc.chip.total'), fmt(o.total)],
  ]
  const genStage =
    g < 0.3 ? t('sc.gen.vec')
    : g < 0.6 ? t('sc.gen.font')
    : g < 0.85 ? t('sc.gen.plan')
    : t('sc.gen.score')
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
          <span className="sc-eyebrow">{o.id} · {o.name || t('common.customer')} · {o.date}</span>
          <h1>{tn(o.title)}</h1>
        </div>
        <ol className="sc-steps" aria-label={t('sc.reviewProgress')}>
          {STEP_KEYS.map((k, i) => (
            <li key={k} className={i < stepIdx ? 'done' : i === stepIdx ? 'now' : ''}>
              <i />
              <span>{t(k)}</span>
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
              <h2>{tn(MODE_HEADING[mode])}</h2>
              <span className={`sc-mode sc-mode--${mode}`}>{tn(MODE_LABEL[mode])}</span>
            </div>

            {mode === 'text' ? (
              <>
                <div className="sc-quote">{sp.text || '…'}</div>
                <div className="sc-paper-strip" style={{ background: sp.paperColor }}>
                  <span style={{ fontFamily: sp.font, color: sp.inkColor }}>{sp.text || '…'}</span>
                </div>
              </>
            ) : (
              <button type="button" className="sc-photo" onClick={p.onZoom} aria-label={t('sc.toggleZoom')}>
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
                    <span>…</span>
                  </div>
                )}
                <span className="sc-photo-tag sc-photo-tag--tl">
                  {mode === 'upload' ? t('sc.customerPhoto', { name: sp.fileName ?? t('sc.upload') }) : t('sc.canvasExport')}
                </span>
                <span className="sc-photo-tag sc-photo-tag--br">{t(p.zoom > 1 ? 'sc.zoomFit' : 'sc.zoomIn')}</span>
              </button>
            )}
          </section>

          <section className="sc-block sc-block--rail">
            <h2>{t('sc.recognition')}</h2>
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
                  {t(mode === 'upload' ? 'sc.ocr' : 'sc.ocrStrokes')}
                </label>
                <textarea
                  id="sc-ocr"
                  className="vh-textarea"
                  rows={4}
                  value={text}
                  onChange={(e) => p.onOcr(e.target.value)}
                />
                <span className="sc-hint">{t('sc.ocrHint')}</span>
              </div>
            )}

            {!p.rejecting ? (
              <div className="sc-actions">
                <button className="vh-btn vh-btn--primary vh-btn--md" onClick={() => p.onApproveInput(text)}>
                  {t('sc.approveInput')}
                </button>
                <button className="vh-btn vh-btn--ghost vh-btn--md sc-danger" onClick={p.onStartReject}>
                  {t('sc.reject')}
                </button>
              </div>
            ) : (
              <div className="sc-actions">
                <div className="sc-reasons" role="group" aria-label={t('sc.rejectReasons')}>
                  {REJECT_REASONS[mode].map((r) => (
                    <button
                      key={r}
                      className={`sc-reason${p.reasons.includes(r) ? ' on' : ''}`}
                      aria-pressed={p.reasons.includes(r)}
                      onClick={() => p.onToggleReason(r)}
                    >
                      {tn(r)}
                    </button>
                  ))}
                </div>
                <div className="sc-row">
                  <button className="vh-btn vh-btn--ghost vh-btn--md" style={{ flex: 1 }} onClick={p.onCancelReject}>
                    {t('sc.cancel')}
                  </button>
                  <button
                    className="vh-btn vh-btn--md sc-reject-confirm"
                    style={{ flex: 1.4 }}
                    disabled={!p.reasons.length}
                    onClick={p.onConfirmReject}
                  >
                    {t('sc.rejectNotify')}
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
              <h2>{t('sc.systemEval')}</h2>
              <span className="sc-hint">{t('sd.evalSvc')}</span>
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
                    <b>{t(verdictOk ? 'sc.ready' : 'sc.recommend')}</b>
                    <small>{t('sc.overall', { n: PASS_SCORE })}</small>
                  </div>
                </div>

                <div className="sc-checks">
                  {ev.checks.map((c) => (
                    <div key={c.k} className={`sc-check sc-check--${checkTone(c.value)}`}>
                      <div><span>{tn(c.k)}</span><span className="vh-mono">{c.value}%</span></div>
                      <i><b style={{ width: `${c.value}%` }} /></i>
                    </div>
                  ))}
                </div>

                <div className="vh-metrics">
                  <div className="vh-metric"><b>{ev.strokes}</b><span>{t('sc.strokes')}</span></div>
                  <div className="vh-metric"><b>{ev.penLifts}</b><span>{t('sc.penLifts')}</span></div>
                  <div className="vh-metric"><b>{t('sc.minutes', { n: sp.mins || 4 })}</b><span>{t('sc.perPiece')}</span></div>
                </div>

                <div className="sc-actions">
                  <button className="vh-btn vh-btn--primary vh-btn--md" onClick={() => p.onAccept(ev.overall)}>
                    {t('sc.accept')}
                  </button>
                  <div className="sc-row">
                    <button className="vh-btn vh-btn--ghost vh-btn--md" style={{ flex: 1 }} onClick={p.onRegen}>
                      {t('sc.regen')}
                    </button>
                    <button className="vh-btn vh-btn--ghost vh-btn--md" style={{ flex: 1 }} onClick={p.onBack}>
                      {t('sc.back')}
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
              ? o.assignment ? t('sc.assignedHeading', { name: o.assignment.techName, robot: o.assignment.robotId }) : t('sc.acceptedNeeds')
              : t('sc.rejectedHeading')}
          </h2>
          <p>
            {accepted
              ? `${t('sc.acceptedBody', { score: o.evalScore ?? t('sc.na'), deposit: fmt(depositOf(o.total)) })}${o.assignment ? '' : ' ' + t('sc.chooseWho')}`
              : t('sc.rejectedBody', { reasons: (o.rejectReasons ?? []).map((r) => tn(r)).join(', ') || t('sc.noReasons') })}
          </p>
          {accepted && (
            <Link to={`/staff/assign/${encodeURIComponent(o.id)}`} className={`vh-btn vh-btn--md sc-self-start ${o.assignment ? 'vh-btn--ghost' : 'vh-btn--primary'}`}>
              {t(o.assignment ? 'sc.changeTech' : 'sc.assignTech')}
            </Link>
          )}
        </section>
      )}
    </div>
  )
}
