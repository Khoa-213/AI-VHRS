import { useEffect, useMemo, useRef, useState } from 'react'
import SkipLink from '../../components/ui/SkipLink'
import ThemeToggle from '../../components/ui/ThemeToggle'
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
    document.fonts?.load(`600 40px ${fontKey}`)?.then(() => alive && setFontTick((t) => t + 1)).catch(() => {})
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
    const tick = (t: number) => {
      const dt = (t - last) / 1000
      last = t
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
    const t = window.setInterval(() => setNow(Date.now()), 100)
    return () => window.clearInterval(t)
  }, [live])

  const shown = live && run ? Math.min(1, Math.max(0, (now - run.startedAt) / (run.seconds * 1000))) : progress

  const header = (
    <header className="sd-top">
      <div>
        <h1>{order ? `Preview ${order.id}` : 'Preview'}</h1>
        <p>{order ? `${order.title} · ${order.name || 'Customer'}` : 'Order not found'}</p>
      </div>
      <div className="sd-top-right">
        <Link to="/tech/preview" className="sd-btn">Choose another order</Link>
        <ThemeToggle className="vh-icon-btn" />
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
      <section className="sd-card"><p className="sd-note">There is no order {id}. Go back to the dashboard.</p></section>,
    )
  }
  const asg = order.assignment
  if (!asg || asg.techId !== user?.techId) {
    return shell(
      <section className="sd-card">
        <h2 className="tp-h">Not your order</h2>
        <p className="sd-note">
          {asg ? `${order.id} is assigned to ${asg.techName}.` : `${order.id} has not been assigned to a technician yet.`}
        </p>
      </section>,
    )
  }

  const sp = order.spec
  const L = layoutById(order.layout)
  const robot = roster().find((t) => t.id === asg.techId)?.robots.find((r) => r.id === asg.robotId)
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
    { ok: watched || live, label: 'Preview played to the end' },
    { ok: checked, label: 'Preflight checks done' },
    { ok: paid, label: paid ? 'Deposit paid' : 'Customer deposit not paid yet' },
    { ok: robotOk, label: robotOk ? `${asg.robotId} available` : `${asg.robotId} is offline` },
  ]
  const canStart = gates.every((g) => g.ok) && !live

  const checkLabel: Record<Check, string> = {
    paper: `${sp.paper} paper loaded and flat`,
    pen: `${sp.pen} mounted, nib ${sp.penW || 2} mm`,
    ink: `${sp.ink} ink level ${robot ? robot.ink : 80}%`,
    calibration: 'Pen height calibrated to the sheet',
    clear: 'Workspace clear of hands and tools',
  }

  const scrub = (v: number) => {
    setProgress(v)
    setPlaying(false)
    if (v >= 1) setWatched(true)
  }
  const options: [string, React.ReactNode][] = [
    ['Format', `${sp.type}${sp.land ? ', landscape' : ''}`],
    ['Input', MODE_LABEL[sp.mode]],
    ['Paper', <><i className="tp-sw" style={{ background: sp.paperColor }} />{sp.paper}</>],
    ['Pen', `${sp.pen}, ${sp.penW || 2} mm`],
    ['Ink', <><i className="tp-sw" style={{ background: sp.inkColor }} />{sp.ink}</>],
    ['Font', sp.fontName],
    ['Layout', L.name],
    ['Pieces', String(pieces)],
  ]

  const finished = live && shown >= 1

  return shell(
    <>
      {confirm && (
        <div className="sc-modal" onClick={() => setConfirm(false)}>
          <div className="sc-modal-card" role="dialog" aria-modal="true" aria-labelledby="tp-confirm-h" onClick={(e) => e.stopPropagation()}>
            <span className="sc-modal-mark sc-modal-mark--accent" aria-hidden="true" />
            <div className="sc-modal-head">
              <h2 id="tp-confirm-h">Start the real robot?</h2>
              <p>
                {asg.robotId} will write {pieces} piece{pieces > 1 ? 's' : ''} of {order.id} with {sp.pen} and {sp.ink}.
                Keep the workspace clear until it finishes.
              </p>
            </div>
            <ul className="sc-modal-facts">
              <li><span>Estimated time</span><b>about {Math.max(1, Math.round(totalSeconds / 60))} min</b></li>
              <li><span>Pen speed</span><b>{tuning.speed} mm/s</b></li>
            </ul>
            <div className="sc-modal-actions">
              <button
                className="vh-btn vh-btn--primary"
                onClick={() => {
                  startRobotRun(order.id, asg.robotId)
                  setConfirm(false)
                }}
              >
                Start writing
              </button>
              <button className="vh-btn vh-btn--ghost vh-btn--sm" onClick={() => setConfirm(false)}>Not yet</button>
            </div>
          </div>
        </div>
      )}

      <div className="tp-grid">
        <div className="tp-main">
          <section className="sd-card tp-view" aria-label="Simulation viewport">
            <div className="tp-stage">
              <SimCanvas
                order={order} plan={plan} vp={vp} pen={pen} arm={arm}
                tuning={tuning} flags={flags} fontTick={fontTick} live={live}
              />
              <span className={`tp-badge${live ? ' live' : ''}`}>
                {live ? `LIVE · ${asg.robotId}` : 'ISAAC SIM · PREVIEW'}
              </span>
              <span className="tp-badge tp-badge--tr">Piece 1 of {pieces}</span>
              {!live && <span className="tp-sim-note">Simulated viewport, not connected to Isaac Sim</span>}
            </div>

            {live ? (
              <div className="tp-transport">
                <div className="tp-live-row">
                  <b className="vh-mono">{Math.round(shown * 100)}%</b>
                  <div className="sd-meter" role="progressbar" aria-valuenow={Math.round(shown * 100)} aria-valuemin={0} aria-valuemax={100} aria-label="Live run progress">
                    <i style={{ width: `${shown * 100}%`, background: 'var(--good)' }} />
                  </div>
                  <span className="vh-mono tp-time">{finished ? 'Done' : `${Math.ceil(run!.seconds * (1 - shown))} s left`}</span>
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
                  {playing ? 'Pause' : shown >= 1 ? 'Replay' : 'Play'}
                </button>
                <button className="vh-btn vh-btn--ghost vh-btn--sm" onClick={() => { setProgress(0); setPlaying(false) }}>Reset</button>
                <input
                  className="tp-range tp-scrub"
                  type="range" min={0} max={1000} value={Math.round(progress * 1000)}
                  onChange={(e) => scrub(Number(e.target.value) / 1000)}
                  aria-label="Scrub preview"
                />
                <span className="vh-mono tp-time">{clock(elapsed)} / {clock(seconds)}</span>
                <div className="tp-rates" role="group" aria-label="Playback speed">
                  {RATES.map((r) => (
                    <button key={r} className={r === rate ? 'on' : ''} aria-pressed={r === rate} onClick={() => setRate(r)}>{r}x</button>
                  ))}
                </div>
              </div>
            )}
          </section>

          <section className="tp-tele" aria-label="Telemetry">
            {[
              ['Progress', `${Math.round(shown * 100)}%`],
              ['Words', `${pen.words} / ${plan.text.split(/\s+/).filter(Boolean).length}`],
              ['Strokes', `${Math.round(shown * ev.strokes)} / ${ev.strokes}`],
              ['Pen', pen.down ? 'Down' : 'Lifted'],
              ['Tip X, Y', `${mmOf(arm.tip.x - vp.paper.x).toFixed(0)}, ${mmOf(arm.tip.y - vp.paper.y).toFixed(0)} mm`],
              ['Reach', arm.reachable ? 'In range' : 'Clamped'],
            ].map(([k, v]) => (
              <div key={k}><span className="sd-label">{k}</span><b className="vh-mono">{v}</b></div>
            ))}
          </section>
          <section className="sd-card tp-joints" aria-label="Joint angles">
            <div className="sd-card-head"><h2 className="tp-h">Joint angles</h2><span className="sd-tag">Simulated</span></div>
            <ul>
              {arm.q.map((q, i) => (
                <li key={i}><span className="sd-label">J{i + 1}</span><b className="vh-mono">{q.toFixed(1)}°</b></li>
              ))}
            </ul>
          </section>
        </div>

        <aside className="tp-side">
          <section className="sd-card" aria-label="Order options">
            <div className="sd-card-head"><h2 className="tp-h">Order options</h2><span className="sd-tag">From the order</span></div>
            <dl className="tp-opts">
              {options.map(([k, v]) => (<div key={k}><dt>{k}</dt><dd>{v}</dd></div>))}
            </dl>
            <p className="tp-text">{plan.text}</p>
          </section>

          <section className="sd-card" aria-label="Simulation tuning">
            <div className="sd-card-head"><h2 className="tp-h">Tuning</h2></div>
            {([
              ['speed', 'Pen speed', 20, 120, 5, 'mm/s'],
              ['force', 'Contact force', 0.5, 3, 0.1, 'N'],
              ['lift', 'Pen lift', 2, 20, 1, 'mm'],
            ] as const).map(([k, label, min, max, step, unit]) => (
              <label key={k} className="tp-slider">
                <span className="sd-label">{label}</span>
                <input
                  className="tp-range" type="range" min={min} max={max} step={step}
                  value={tuning[k]} disabled={live}
                  onChange={(e) => setTuning((t) => ({ ...t, [k]: Number(e.target.value) }))}
                />
                <b className="vh-mono">{tuning[k]} {unit}</b>
              </label>
            ))}
            <p className="sd-note">
              One piece takes about {Math.max(1, Math.round(seconds / 60))} min; {pieces} piece{pieces > 1 ? 's' : ''} about {Math.max(1, Math.round(totalSeconds / 60))} min. Changing tuning restarts nothing, scrub to compare.
            </p>
            <div className="tp-flags" role="group" aria-label="View options">
              {([['trajectory', 'Planned path'], ['reach', 'Reach envelope'], ['joints', 'Joint labels']] as const).map(([k, label]) => (
                <label key={k}>
                  <input type="checkbox" checked={flags[k]} onChange={(e) => setFlags((f) => ({ ...f, [k]: e.target.checked }))} />
                  {label}
                </label>
              ))}
            </div>
          </section>

          <section className="sd-card tp-start" aria-label="Start the robot">
            <div className="sd-card-head">
              <h2 className="tp-h">Preflight</h2>
              {robot && <span className="sd-tag">{asg.robotId} · {STATE_LABEL[robot.state]}</span>}
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
                  <b>Writing finished</b>
                  <span>{pieces} piece{pieces > 1 ? 's' : ''} written on {run!.robotId}. Check the sheets and send photos to the customer.</span>
                  <Link to={`/tech/qc/${encodeURIComponent(order.id)}`} className="vh-btn vh-btn--primary vh-btn--md">
                    Go to photo and QC
                  </Link>
                </div>
              ) : (
                <div className="tp-done run" role="status">
                  <b>Robot is writing</b>
                  <span>{run!.robotId} started this order. This page follows the run live.</span>
                  {prototype && (
                    <button className="vh-btn vh-btn--ghost vh-btn--sm" onClick={() => finishRobotRun(order.id)}>
                      Prototype: finish the run now
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
                  Start real robot
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
                    Prototype: play preview and pass preflight
                  </button>
                )}
                {!paid && prototype && (
                  <button
                    className="vh-btn vh-btn--ghost vh-btn--sm"
                    onClick={() => updateOrder(order.id, { status: 'Queued', depositMethod: 'Prototype' })}
                  >
                    Prototype: simulate deposit paid ({fmt(Math.round(order.total * 0.3 / 1000) * 1000)})
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
