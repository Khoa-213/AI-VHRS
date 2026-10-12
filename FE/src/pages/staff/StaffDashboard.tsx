import SkipLink from '../../components/ui/SkipLink'
import { ClipboardText, House, SignOut, SquaresFour } from '@phosphor-icons/react'
import { STATUS_COLORS } from '../../constants/catalog'
import ThemeToggle from '../../components/ui/ThemeToggle'
import { Link } from '../../router/router'
import { signOut, useAllStaffOrders, useUser } from '../../store/store'
import type { Order } from '../../types'
import { fmt } from '../../utils/format'
import { Donut, Spark } from './charts'
import { GROUPS, aiTelemetry, reviewTelemetry, robotTelemetry } from './telemetry'
import './dashboard.css'
import './polish.css'

const greeting = () => {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening'
}

const hours = (m: number) => `${(m / 60).toFixed(1)} h`

export default function StaffDashboard() {
  const user = useUser()
  const orders = useAllStaffOrders()
  const robot = robotTelemetry(orders)
  const ai = aiTelemetry(orders)
  const review = reviewTelemetry(orders)

  const robotTotal = robot.minutes.writing + robot.minutes.idle + robot.minutes.calibrating
  const slices = [
    { label: 'Writing', value: robot.minutes.writing, color: 'var(--s1)' },
    { label: 'Idle', value: robot.minutes.idle, color: 'var(--s2)' },
    { label: 'Calibrating', value: robot.minutes.calibrating, color: 'var(--s3)' },
  ]
  const days = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(Date.now() - (6 - i) * 864e5)
    return d.toLocaleDateString('en-GB', { weekday: 'short' })
  })
  const maxService = Math.max(...ai.services.map((s) => s.v))
  const today = new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' })

  return (
    <div className="sd">
      <SkipLink />
      <nav className="sd-rail" aria-label="Staff navigation">
        <Link to="/staff" className="sd-mark" aria-label="AI-VHRS studio">AV</Link>
        <Link to="/staff" className="sd-nav on" aria-current="page">
          <SquaresFour size={22} />
          <span>Dashboard</span>
        </Link>
        <Link to="/staff/review" className="sd-nav">
          <ClipboardText size={22} />
          <span>Review</span>
          {review.pending > 0 && <b className="sd-count">{review.pending}</b>}
        </Link>
        <div className="sd-rail-end">
          <Link to="/" className="sd-nav">
            <House size={22} />
            <span>Site</span>
          </Link>
          <button type="button" className="sd-nav" onClick={() => signOut()}>
            <SignOut size={22} />
            <span>Sign out</span>
          </button>
        </div>
      </nav>

      <main className="sd-body" id="main">
        <header className="sd-top">
          <div>
            <h1>{greeting()}, {user?.name ?? 'Staff'}</h1>
            <p>{today}</p>
          </div>
          <div className="sd-top-right">
            <span className={`sd-state${robot.state === 'Writing' ? ' busy' : ''}`}>FR3 #01 · {robot.state}</span>
            <ThemeToggle className="vh-icon-btn" />
          </div>
        </header>

        <div className="sd-grid">
          <section className="sd-card sd-orders" aria-labelledby="sd-orders-h">
            <div className="sd-card-head">
              <h2 id="sd-orders-h">Orders</h2>
              <Link to="/staff/review" className="sd-btn">Open review</Link>
            </div>
            <div className="sd-total">
              <span>In pipeline</span>
              <b className="vh-mono">{fmt(review.queuedValue)}</b>
            </div>

            <div className="sd-groups">
              {GROUPS.map((g) => {
                const rows = orders.filter((o) => g.statuses.includes(o.status))
                return (
                  <details key={g.id} className="sd-group" open={g.id === 'review' || g.id === 'producing'}>
                    <summary>
                      <span className="sd-group-name">{g.label}</span>
                      <span className="sd-group-note">{g.note}</span>
                      <span className="sd-group-count vh-mono">{rows.length}</span>
                    </summary>
                    <ul>
                      {rows.map((o) => <OrderRow key={o.id} order={o} link={g.reviewable} />)}
                      {!rows.length && <li className="sd-none">Nothing here.</li>}
                    </ul>
                  </details>
                )
              })}
            </div>
          </section>

          <div className="sd-stats">
            <div className="sd-kpis">
              <Kpi label="Needs review" value={String(review.pending)} hint="Pending staff" tone="accent" />
              <Kpi label="Waiting deposit" value={String(review.accepted)} hint="Accepted orders" />
              <Kpi label="In production" value={String(review.producing)} hint="Robot queue" />
              <Kpi label="Rejected" value={String(review.rejected)} hint="Sent back" />
            </div>

            <section className="sd-card" aria-labelledby="sd-robot-h">
              <div className="sd-card-head">
                <h2 id="sd-robot-h">Robot FR3 #01</h2>
                <span className="sd-tag">Simulated telemetry</span>
              </div>
              <div className="sd-robot">
                <div className="sd-donut">
                  <Donut slices={slices} center={hours(robotTotal)} caption="today" />
                  <ul className="sd-legend">
                    {slices.map((s) => (
                      <li key={s.label}>
                        <i style={{ background: s.color }} />
                        <span>{s.label}</span>
                        <b className="vh-mono">{hours(s.value)}</b>
                      </li>
                    ))}
                  </ul>
                </div>
                <div className="sd-robot-side">
                  <div className="sd-job">
                    <span className="sd-label">Current job</span>
                    {robot.job ? (
                      <>
                        <b>{robot.job.title}</b>
                        <span className="sd-sub">{robot.job.id} · about {robot.minutesLeft} min left</span>
                        <div className="sd-meter" role="progressbar" aria-valuenow={robot.progress} aria-valuemin={0} aria-valuemax={100} aria-label="Job progress">
                          <i style={{ width: `${robot.progress}%` }} />
                        </div>
                      </>
                    ) : (
                      <span className="sd-sub">No job in the queue. Accepted orders appear here after the deposit.</span>
                    )}
                  </div>
                  <div className="sd-consumables">
                    {robot.consumables.map((c) => (
                      <div key={c.k}>
                        <span className="sd-label">{c.k}</span>
                        <div className="sd-meter" role="progressbar" aria-valuenow={c.v} aria-valuemin={0} aria-valuemax={100} aria-label={c.k}>
                          <i style={{ width: `${c.v}%` }} />
                        </div>
                        <b className="vh-mono">{c.v}%</b>
                      </div>
                    ))}
                  </div>
                  <div className="sd-pieces"><b className="vh-mono">{robot.piecesToday}</b><span>pieces written today</span></div>
                </div>
              </div>
            </section>

            <div className="sd-two">
              <section className="sd-card" aria-labelledby="sd-ai-h">
                <div className="sd-card-head">
                  <h2 id="sd-ai-h">AI usage</h2>
                  <span className="sd-tag">Simulated telemetry</span>
                </div>
                <div className="sd-ai-top">
                  <div>
                    <b className="sd-big vh-mono">{ai.total}</b>
                    <span className="sd-sub">requests today</span>
                  </div>
                  <Spark values={ai.week} labels={days} />
                </div>
                <ul className="sd-bars">
                  {ai.services.map((s) => (
                    <li key={s.k}>
                      <span>{s.k}</span>
                      <i><b style={{ width: `${(s.v / maxService) * 100}%` }} /></i>
                      <span className="vh-mono">{s.v}</span>
                    </li>
                  ))}
                </ul>
              </section>

              <section className="sd-card" aria-labelledby="sd-eval-h">
                <div className="sd-card-head">
                  <h2 id="sd-eval-h">Quality</h2>
                </div>
                <div className="sd-eval">
                  <div>
                    <b className="sd-big vh-mono">{ai.avg}</b>
                    <span className="sd-sub">average score of 100</span>
                  </div>
                  <div>
                    <b className="sd-big vh-mono">{ai.pass}%</b>
                    <span className="sd-sub">pass threshold 80</span>
                  </div>
                </div>
                <p className="sd-note">
                  {ai.scoredCount
                    ? `Based on ${ai.scoredCount} order${ai.scoredCount > 1 ? 's' : ''} you evaluated.`
                    : 'No orders evaluated yet. Typical values are shown until you accept one.'}
                </p>
              </section>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}

function Kpi({ label, value, hint, tone }: { label: string; value: string; hint: string; tone?: 'accent' }) {
  return (
    <div className={`sd-kpi${tone ? ' ' + tone : ''}`}>
      <span className="sd-label">{label}</span>
      <b className="vh-mono">{value}</b>
      <span className="sd-sub">{hint}</span>
    </div>
  )
}

function OrderRow({ order: o, link }: { order: Order; link: boolean }) {
  const [baseColor] = STATUS_COLORS[o.status]
  // Accepted orders: green once a technician has them, amber until then.
  const needsTech = o.status === 'Accepted' && !o.assignment
  const assigned = o.status === 'Accepted' && !!o.assignment
  const color = assigned ? 'var(--good)' : needsTech ? 'var(--warn)' : baseColor
  const label = assigned ? 'Assigned' : needsTech ? 'Needs technician' : o.status
  const body = (
    <>
      <span className="sd-row-main">
        <span className="sd-row-title">{o.title}</span>
        <span className="sd-row-meta">
          {o.id} · {o.name || 'Customer'}
          {assigned && ` · ${o.assignment!.techName} on ${o.assignment!.robotId}`}
        </span>
      </span>
      <span className="sd-row-side">
        <span className="vh-chip" style={{ color }}>{label}</span>
        <span className="vh-mono sd-row-total">{fmt(o.total)}</span>
      </span>
    </>
  )
  return (
    <li>
      {link ? <Link to={`/staff/${o.status === 'Accepted' ? 'assign' : 'review'}/${encodeURIComponent(o.id)}`} className={`sd-row${assigned ? ' assigned' : needsTech ? ' needs' : ''}`}>{body}</Link> : <div className="sd-row static">{body}</div>}
    </li>
  )
}
