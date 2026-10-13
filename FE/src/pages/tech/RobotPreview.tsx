import { useEffect, useMemo, useRef, useState } from 'react'
import { useT, useTn } from '../../i18n'
import SkipLink from '../../components/ui/SkipLink'
import ThemeToggle from '../../components/ui/ThemeToggle'
import LanguageToggle from '../../components/ui/LanguageToggle'
import { layoutById } from '../../constants/catalog'
import { Link } from '../../router/router'
import {
  finishRobotRun, startRobotRun, updateOrder, useAllStaffOrders, usePrototypeMode, useUser,
} from '../../store/store'
import { fmt } from '../../utils/format'
import { MODE_LABEL, evaluate } from '../staff/evaluate'
import { STATE_LABEL, roster } from '../staff/technicians'
import SimCanvas from './SimCanvas'
import TechRail from './TechRail'
import {
  DEFAULT_TUNING, buildPlan, penAt, pieceSeconds, solveArm, viewportFor, mmOf,
  type Tuning, type ViewFlags,
} from './sim'
import '../staff/dashboard.css'
import '../staff/staff.css'
import './tech.css'
import '../staff/polish.css'

const RATES = [1, 10, 30, 60]
const CHECKS = ['paper', 'pen', 'ink', 'calibration', 'clear'] as const
type Check = (typeof CHECKS)[number]

const clock = (s: number) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(Math.floor(s % 60)).padStart(2, '0')}`

export default function RobotPreview({ id }: { id: string }) {
  const t = useT()
  const tn = useTn()
  const user = useUser()
  const orders = useAllStaffOrders()
  const prototype = usePrototypeMode()
  const order = orders.find((o) => o.id === id)

  const [tuning, setTuning] = useState<Tuning>(DEFAULT_TUNING)
  const [flags, setFlags] = useState<ViewFlags>({ trajectory: true, reach: false, joints: true })
  const [rate, setRate] = useState(30)
  const [playing, setPlaying] = useState(false)
  const [progress, setProgress] = useState(0)
  const [watched, setWatched] = useState(false)
  const [checks, setChecks] = useState<Record<Check, boolean>>({ paper: false, pen: false, ink: false, calibration: false, clear: false })
  const [confirm, setConfirm] = useState(false)
  const [fontTick, setFontTick] = useState(0)
  const [now, setNow] = useState(() => Date.now())

  const measure = useMemo(() => document.createElement('canvas').getContext('2d')!, [])
  const aspect = order?.spec.aspect ?? '105/148'
  const vp = useMemo(() => viewportFor(aspect), [aspect])
  const fontKey = order?.spec.font ?? ''

  // Web fonts are not in the canvas until used once, so load, then redo the layout.
  useEffect(() => {
    if (!fontKey) return
    let alive = true
    document.fonts?.load(`600 40px ${fontKey}`)?.then(() => alive && setFontTick((n) => n + 1)).catch(() => {})
    return () => { alive = false }
  }, [fontKey])

  const plan = useMemo(
    () => (order ? buildPlan(measure, order, vp) : null),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [order?.id, order?.spec.font, order?.spec.text, order?.ocrText, order?.layout, vp, measure, fontTick],
  )

  const run = order?.run
  const live = !!run && !!order && (order.status === 'Queued' || order.status === 'Rewriting')
  const seconds = order && plan ? pieceSeconds(plan, tuning) : 60
  const rateRef = useRef(rate)
  rateRef.current = rate

  // Preview playback loop.
  useEffect(() => {
    if (!playing || live) return
    let raf = 0
    let last = performance.now()
    const tick = (ts: number) => {
      const dt = (ts - last) / 1000
      last = ts
      setProgress((p) => {
        const n = Math.min(1, p + (dt * rateRef.current) / seconds)
        if (n >= 1) {
          setPlaying(false)
          setWatched(true)
        }
        return n
      })
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [playing, live, seconds])

  // Live run clock.
  useEffect(() => {
    if (!live) return
    const iv = window.setInterval(() => setNow(Date.now()), 100)
    return () => window.clearInterval(iv)
  }, [live])

  const shown = live && run ? Math.min(1, Math.max(0, (now - run.startedAt) / (run.seconds * 1000))) : progress

  const header = (
    <header className="sd-top">
      <div>
        <h1>{order ? t('rp.title', { id: order.id }) : t('rp.titleShort')}</h1>
        <p>{order ? t('rp.subtitle', { title: tn(order.title), name: order.name || t('common.customer') }) : t('rp.notFound')}</p>
      </div>
      <div className="sd-top-right">
        <Link to="/tech/preview" className="sd-btn">{t('rp.another')}</Link>
        <ThemeToggle className="vh-icon-btn" />
        <LanguageToggle className="vh-icon-btn" />
      </div>
    </header>
  )

  const shell = (body: React.ReactNode) => (
    <div className="sd">
      <SkipLink />
      <TechRail active="preview" />
      <main className="sd-body" id="main">{header}{body}</main>
    </div>
  )

  if (!order || !plan) {
    return shell(
      <section className="sd-card"><p className="sd-note">{t('rp.noOrder', { id })}</p></section>,
    )
  }
  const asg = order.assignment
  if (!asg || asg.techId !== user?.techId) {
    return shell(
      <section className="sd-card">
        <h2 className="tp-h">{t('rp.notYours')}</h2>
        <p className="sd-note">
          {asg ? t('rp.assignedTo', { id: order.id, name: asg.techName }) : t('rp.unassigned', { id: order.id })}
        </p>
      </section>,
    )
  }

  const sp = order.spec
  const L = layoutById(order.layout)
  const robot = roster().find((r) => r.id === asg.techId)?.robots.find((r) => r.id === asg.robotId)
  const pieces = sp.qty || 1
  const pen = penAt(measure, plan, order, shown)
  const arm = solveArm(vp, { x: pen.x, y: pen.y }, shown * 40)
  const ev = evaluate(order, plan.text)
  const elapsed = shown * seconds
  const totalSeconds = seconds * pieces

  const paid = order.status === 'Queued' || order.status === 'Rewriting'
  const robotOk = robot?.state !== 'offline'
  const checked = CHECKS.every((c) => checks[c])
  const gates = [
    { ok: watched || live, label: t('rp.gate.preview') },
    { ok: checked, label: t('rp.gate.preflight') },
    { ok: paid, label: t(paid ? 'rp.gate.paid' : 'rp.gate.unpaid') },
    { ok: robotOk, label: t(robotOk ? 'rp.gate.robotOk' : 'rp.gate.robotOff', { robot: asg.robotId }) },
  ]
  const canStart = gates.every((g) => g.ok) && !live

  const checkLabel: Record<Check, string> = {
    paper: t('rp.check.paper', { paper: tn(sp.paper) }),
    pen: t('rp.check.pen', { pen: tn(sp.pen), mm: sp.penW || 2 }),
    ink: t('rp.check.ink', { ink: tn(sp.ink), pct: robot ? robot.ink : 80 }),
    calibration: t('rp.check.cal'),
    clear: t('rp.check.clear'),
  }

  const scrub = (v: number) => {
    setProgress(v)
    setPlaying(false)
    if (v >= 1) setWatched(true)
  }
  const options: [string, React.ReactNode][] = [
    [t('rp.opt.format'), `${tn(sp.type)}${sp.land ? t('rp.opt.landscape') : ''}`],
    [t('rp.opt.input'), tn(MODE_LABEL[sp.mode])],
    [t('rp.opt.paper'), <><i className="tp-sw" style={{ background: sp.paperColor }} />{tn(sp.paper)}</>],
    [t('rp.opt.pen'), `${tn(sp.pen)}, ${sp.penW || 2} mm`],
    [t('rp.opt.ink'), <><i className="tp-sw" style={{ background: sp.inkColor }} />{tn(sp.ink)}</>],
    [t('rp.opt.font'), tn(sp.fontName)],
    [t('rp.opt.layout'), tn(L.name)],
    [t('rp.opt.pieces'), String(pieces)],
  ]

  const finished = live && shown >= 1

  return shell(
    <>
      {confirm && (
        <div className="sc-modal" onClick={() => setConfirm(false)}>
          <div className="sc-modal-card" role="dialog" aria-modal="true" aria-labelledby="tp-confirm-h" onClick={(e) => e.stopPropagation()}>
            <span className="sc-modal-mark sc-modal-mark--accent" aria-hidden="true" />
            <div className="sc-modal-head">
              <h2 id="tp-confirm-h">{t('rp.startQ')}</h2>
              <p>{t('rp.startBody', { robot: asg.robotId, pieces: t(pieces > 1 ? 'rp.pieces' : 'rp.piece', { n: pieces }), id: order.id, pen: tn(sp.pen), ink: tn(sp.ink) })}</p>
            </div>
            <ul className="sc-modal-facts">
              <li><span>{t('rp.estTime')}</span><b>{t('rp.aboutMin', { n: Math.max(1, Math.round(totalSeconds / 60)) })}</b></li>
              <li><span>{t('rp.penSpeed')}</span><b>{tuning.speed} mm/s</b></li>
            </ul>
            <div className="sc-modal-actions">
              <button
                className="vh-btn vh-btn--primary"
                onClick={() => {
                  startRobotRun(order.id, asg.robotId)
                  setConfirm(false)
                }}
              >
                {t('rp.startWriting')}
              </button>
              <button className="vh-btn vh-btn--ghost vh-btn--sm" onClick={() => setConfirm(false)}>{t('rp.notYet')}</button>
            </div>
          </div>
        </div>
      )}

      <div className="tp-grid">
        <div className="tp-main">
          <section className="sd-card tp-view" aria-label={t('rp.viewport')}>
            <div className="tp-stage">
              <SimCanvas
                order={order} plan={plan} vp={vp} pen={pen} arm={arm}
                tuning={tuning} flags={flags} fontTick={fontTick} live={live}
              />
              <span className={`tp-badge${live ? ' live' : ''}`}>
                {live ? t('rp.badgeLive', { robot: asg.robotId }) : t('rp.badgePreview')}
              </span>
              <span className="tp-badge tp-badge--tr">{t('rp.pieceOf', { n: pieces })}</span>
              {!live && <span className="tp-sim-note">{t('rp.simNote')}</span>}
            </div>

            {live ? (
              <div className="tp-transport">
                <div className="tp-live-row">
                  <b className="vh-mono">{Math.round(shown * 100)}%</b>
                  <div className="sd-meter" role="progressbar" aria-valuenow={Math.round(shown * 100)} aria-valuemin={0} aria-valuemax={100} aria-label={t('rp.liveProgress')}>
                    <i style={{ width: `${shown * 100}%`, background: 'var(--good)' }} />
                  </div>
                  <span className="vh-mono tp-time">{finished ? t('rp.done') : t('rp.secLeft', { n: Math.ceil(run!.seconds * (1 - shown)) })}</span>
                </div>
              </div>
            ) : (
              <div className="tp-transport">
                <button
                  className="vh-btn vh-btn--primary vh-btn--sm"
                  onClick={() => {
                    if (shown >= 1) setProgress(0)
                    setPlaying((p) => !p)
                  }}
                >
                  {t(playing ? 'rp.pause' : shown >= 1 ? 'rp.replay' : 'rp.play')}
                </button>
                <button className="vh-btn vh-btn--ghost vh-btn--sm" onClick={() => { setProgress(0); setPlaying(false) }}>{t('rp.reset')}</button>
                <input
                  className="tp-range tp-scrub"
                  type="range" min={0} max={1000} value={Math.round(progress * 1000)}
                  onChange={(e) => scrub(Number(e.target.value) / 1000)}
                  aria-label={t('rp.scrub')}
                />
                <span className="vh-mono tp-time">{clock(elapsed)} / {clock(seconds)}</span>
                <div className="tp-rates" role="group" aria-label={t('rp.speed')}>
                  {RATES.map((r) => (
                    <button key={r} className={r === rate ? 'on' : ''} aria-pressed={r === rate} onClick={() => setRate(r)}>{r}x</button>
                  ))}
                </div>
              </div>
            )}
          </section>

          <section className="tp-tele" aria-label={t('rp.telemetry')}>
            {[
              [t('rp.tele.progress'), `${Math.round(shown * 100)}%`],
              [t('rp.tele.words'), `${pen.words} / ${plan.text.split(/\s+/).filter(Boolean).length}`],
              [t('rp.tele.strokes'), `${Math.round(shown * ev.strokes)} / ${ev.strokes}`],
              [t('rp.tele.pen'), t(pen.down ? 'rp.tele.down' : 'rp.tele.lifted')],
              [t('rp.tele.tip'), `${mmOf(arm.tip.x - vp.paper.x).toFixed(0)}, ${mmOf(arm.tip.y - vp.paper.y).toFixed(0)} mm`],
              [t('rp.tele.reach'), t(arm.reachable ? 'rp.tele.inRange' : 'rp.tele.clamped')],
            ].map(([k, v]) => (
              <div key={k}><span className="sd-label">{k}</span><b className="vh-mono">{v}</b></div>
            ))}
          </section>
          <section className="sd-card tp-joints" aria-label={t('rp.joints')}>
            <div className="sd-card-head"><h2 className="tp-h">{t('rp.joints')}</h2><span className="sd-tag">{t('rp.simulated')}</span></div>
            <ul>
              {arm.q.map((q, i) => (
                <li key={i}><span className="sd-label">J{i + 1}</span><b className="vh-mono">{q.toFixed(1)}°</b></li>
              ))}
            </ul>
          </section>
        </div>

        <aside className="tp-side">
          <section className="sd-card" aria-label={t('rp.options')}>
            <div className="sd-card-head"><h2 className="tp-h">{t('rp.options')}</h2><span className="sd-tag">{t('rp.fromOrder')}</span></div>
            <dl className="tp-opts">
              {options.map(([k, v]) => (<div key={k}><dt>{k}</dt><dd>{v}</dd></div>))}
            </dl>
            <p className="tp-text">{plan.text}</p>
          </section>

          <section className="sd-card" aria-label={t('rp.tuning')}>
            <div className="sd-card-head"><h2 className="tp-h">{t('rp.tuningTitle')}</h2></div>
            {([
              ['speed', 'rp.t.speed', 20, 120, 5, 'mm/s'],
              ['force', 'rp.t.force', 0.5, 3, 0.1, 'N'],
              ['lift', 'rp.t.lift', 2, 20, 1, 'mm'],
            ] as const).map(([k, label, min, max, step, unit]) => (
              <label key={k} className="tp-slider">
                <span className="sd-label">{t(label)}</span>
                <input
                  className="tp-range" type="range" min={min} max={max} step={step}
                  value={tuning[k]} disabled={live}
                  onChange={(e) => setTuning((tu) => ({ ...tu, [k]: Number(e.target.value) }))}
                />
                <b className="vh-mono">{tuning[k]} {unit}</b>
              </label>
            ))}
            <p className="sd-note">
              {t('rp.tuneNote', { one: Math.max(1, Math.round(seconds / 60)), pieces: t(pieces > 1 ? 'rp.pieces' : 'rp.piece', { n: pieces }), all: Math.max(1, Math.round(totalSeconds / 60)) })}
            </p>
            <div className="tp-flags" role="group" aria-label={t('rp.viewOptions')}>
              {([['trajectory', 'rp.f.trajectory'], ['reach', 'rp.f.reach'], ['joints', 'rp.f.joints']] as const).map(([k, label]) => (
                <label key={k}>
                  <input type="checkbox" checked={flags[k]} onChange={(e) => setFlags((f) => ({ ...f, [k]: e.target.checked }))} />
                  {t(label)}
                </label>
              ))}
            </div>
          </section>

          <section className="sd-card tp-start" aria-label={t('rp.startRobot')}>
            <div className="sd-card-head">
              <h2 className="tp-h">{t('rp.preflight')}</h2>
              {robot && <span className="sd-tag">{asg.robotId} · {tn(STATE_LABEL[robot.state])}</span>}
            </div>
            <ul className="tp-checks">
              {CHECKS.map((c) => (
                <li key={c}>
                  <label>
                    <input type="checkbox" checked={checks[c]} disabled={live} onChange={(e) => setChecks((m) => ({ ...m, [c]: e.target.checked }))} />
                    {checkLabel[c]}
                  </label>
                </li>
              ))}
            </ul>

            {live ? (
              finished ? (
                <div className="tp-done" role="status">
                  <b>{t('rp.finished')}</b>
                  <span>{t('rp.finishedBody', { pieces: t(pieces > 1 ? 'rp.pieces' : 'rp.piece', { n: pieces }), robot: run!.robotId })}</span>
                  <Link to={`/tech/qc/${encodeURIComponent(order.id)}`} className="vh-btn vh-btn--primary vh-btn--md">
                    {t('rp.goQc')}
                  </Link>
                </div>
              ) : (
                <div className="tp-done run" role="status">
                  <b>{t('rp.writing')}</b>
                  <span>{t('rp.writingBody', { robot: run!.robotId })}</span>
                  {prototype && (
                    <button className="vh-btn vh-btn--ghost vh-btn--sm" onClick={() => finishRobotRun(order.id)}>
                      {t('rp.protoFinish')}
                    </button>
                  )}
                </div>
              )
            ) : (
              <>
                <ul className="tp-gates">
                  {gates.map((g) => (
                    <li key={g.label} className={g.ok ? 'ok' : ''}>{g.label}</li>
                  ))}
                </ul>
                <button className="vh-btn vh-btn--primary vh-btn--md" disabled={!canStart} onClick={() => setConfirm(true)}>
                  {t('rp.startReal')}
                </button>
                {prototype && !(watched && checked) && (
                  <button
                    className="vh-btn vh-btn--ghost vh-btn--sm"
                    onClick={() => {
                      setProgress(1)
                      setPlaying(false)
                      setWatched(true)
                      setChecks({ paper: true, pen: true, ink: true, calibration: true, clear: true })
                    }}
                  >
                    {t('rp.protoPlay')}
                  </button>
                )}
                {!paid && prototype && (
                  <button
                    className="vh-btn vh-btn--ghost vh-btn--sm"
                    onClick={() => updateOrder(order.id, { status: 'Queued', depositMethod: 'Prototype' })}
                  >
                    {t('rp.protoDeposit', { amount: fmt(Math.round(order.total * 0.3 / 1000) * 1000) })}
                  </button>
                )}
              </>
            )}
          </section>
        </aside>
      </div>
    </>,
  )
}
