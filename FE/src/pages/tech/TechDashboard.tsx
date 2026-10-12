import SkipLink from '../../components/ui/SkipLink'
import { STATUS_COLORS } from '../../constants/catalog'
import ThemeToggle from '../../components/ui/ThemeToggle'
import { Link } from '../../router/router'
import { useAllStaffOrders, useUser } from '../../store/store'
import type { Order } from '../../types'
import { Donut } from '../staff/charts'
import { STATE_LABEL, loadOf, roster, type RobotState } from '../staff/technicians'
import { phaseOf, useNow, type Phase } from './phase'
import TechRail from './TechRail'
import '../staff/dashboard.css'
import './tech.css'
import '../staff/polish.css'

const greeting = () => {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening'
}

const minutesOf = (o: Order) => Math.max(1, (o.spec.mins || 4) * (o.spec.qty || 1))

interface TechGroup {
  id: Phase
  label: string
  note: string
}

const GROUPS: TechGroup[] = [
  { id: 'qc', label: 'Photo and QC', note: 'Robot finished, check and send' },
  { id: 'live', label: 'Writing now', note: 'Robot is running' },
  { id: 'ready', label: 'Ready to preview', note: 'Deposit paid' },
  { id: 'wait', label: 'Waiting for deposit', note: 'Preview allowed' },
  { id: 'done', label: 'Finished', note: 'Written and shipped' },
]

const RSTATE: Record<RobotState, string> = {
  idle: 'var(--s3)',
  writing: 'var(--s1)',
  calibrating: 'var(--s2)',
  offline: 'var(--fx-12)',
}

export default function TechDashboard() {
  const user = useUser()
  const all = useAllStaffOrders()
  const now = useNow(1000)
  const tech = roster().find((t) => t.id === user?.techId)
  const mine = all.filter((o) => o.assignment?.techId === user?.techId)
  const robots = tech?.robots ?? []

  const inPhase = (p: Phase) => mine.filter((o) => phaseOf(o, now) === p)
  const counts = {
    qc: inPhase('qc').length,
    live: inPhase('live').length,
    ready: inPhase('ready').length,
    wait: inPhase('wait').length,
    done: inPhase('done').length,
  }
  const open = mine.filter((o) => ['qc', 'live', 'ready', 'wait'].includes(phaseOf(o, now) ?? ''))
  const queueMinutes = open.reduce((a, o) => a + minutesOf(o), 0)
  const maxMin = Math.max(1, ...open.map(minutesOf))
  const states = (['idle', 'writing', 'calibrating', 'offline'] as RobotState[]).map((s) => ({
    label: STATE_LABEL[s],
    value: robots.filter((r) => r.state === s).length,
    color: RSTATE[s],
  }))
  const robotJob = (id: string) => mine.find((o) => phaseOf(o, now) === 'live' && o.run?.robotId === id)
  const today = new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' })

  return (
    <div className="sd">
      <SkipLink />
      <TechRail active="dashboard" />
      <main className="sd-body" id="main">
        <header className="sd-top">
          <div>
            <h1>{greeting()}, {user?.name ?? 'Technician'}</h1>
            <p>{today} · {tech?.shift ?? 'Technician desk'}</p>
          </div>
          <div className="sd-top-right">
            <span className={`sd-state${counts.live ? ' busy' : ''}`}>{robots.length} robots · {counts.live ? 'WRITING' : 'READY'}</span>
            <ThemeToggle className="vh-icon-btn" />
          </div>
        </header>

        <div className="sd-grid">
          <section className="sd-card sd-orders" aria-labelledby="td-orders-h">
            <div className="sd-card-head">
              <h2 id="td-orders-h">My orders</h2>
              <span className="sd-tag">{mine.length} assigned</span>
            </div>
            <div className="sd-total">
              <span>Queue time</span>
              <b className="vh-mono">{queueMinutes} min</b>
            </div>
            <div className="sd-groups">
              {GROUPS.map((g) => {
                const rows = inPhase(g.id)
                return (
                  <details key={g.id} className="sd-group" open={g.id !== 'done'}>
                    <summary>
                      <span className="sd-group-name">{g.label}</span>
                      <span className="sd-group-note">{g.note}</span>
                      <span className="sd-group-count vh-mono">{rows.length}</span>
                    </summary>
                    <ul>
                      {rows.map((o) => <TechRow key={o.id} order={o} group={g.id} />)}
                      {!rows.length && <li className="sd-none">Nothing here.</li>}
                    </ul>
                  </details>
                )
              })}
            </div>
            {!mine.length && (
              <div className="sd-empty">
                <b>Nothing assigned yet</b>
                <span>Staff choose a technician right after they accept an order. New orders appear here by themselves.</span>
              </div>
            )}
          </section>

          <div className="sd-stats">
            <div className="sd-kpis">
              <div className="sd-kpi accent"><span className="sd-label">Needs QC</span><b className="vh-mono">{counts.qc}</b><span className="sd-sub">Photos to send</span></div>
              <div className="sd-kpi"><span className="sd-label">Writing now</span><b className="vh-mono">{counts.live}</b><span className="sd-sub">Robot running</span></div>
              <div className="sd-kpi"><span className="sd-label">Ready to preview</span><b className="vh-mono">{counts.ready}</b><span className="sd-sub">Deposit paid</span></div>
              <div className="sd-kpi"><span className="sd-label">Waiting deposit</span><b className="vh-mono">{counts.wait}</b><span className="sd-sub">Customer paying</span></div>
            </div>

            <section className="sd-card" aria-labelledby="td-robots-h">
              <div className="sd-card-head">
                <h2 id="td-robots-h">My robots</h2>
                <span className="sd-tag">Simulated telemetry</span>
              </div>
              <div className="sd-robot">
                <div className="sd-donut">
                  <Donut slices={states} center={String(robots.length)} caption="robots" />
                  <ul className="sd-legend">
                    {states.map((s) => (
                      <li key={s.label}><i style={{ background: s.color }} /><span>{s.label}</span><b className="vh-mono">{s.value}</b></li>
                    ))}
                  </ul>
                </div>
                <ul className="td-robots">
                  {robots.map((r) => {
                    const job = robotJob(r.id)
                    return (
                      <li key={r.id}>
                        <span className="vh-mono td-robot-id">{r.id}</span>
                        <span className={`as-state as-state--${r.state}`}>{STATE_LABEL[r.state]}</span>
                        <span className="sd-meter" role="progressbar" aria-valuenow={r.ink} aria-valuemin={0} aria-valuemax={100} aria-label={`${r.id} ink`}>
                          <i style={{ width: `${r.ink}%` }} />
                        </span>
                        <span className="vh-mono td-ink">{r.ink}%</span>
                        <span className="sd-sub td-job">{job ? job.id : mine.some((o) => o.assignment?.robotId === r.id && phaseOf(o, now) !== 'done') ? 'Order waiting' : 'No order'}</span>
                      </li>
                    )
                  })}
                </ul>
              </div>
            </section>

            <div className="sd-two">
              <section className="sd-card" aria-labelledby="td-queue-h">
                <div className="sd-card-head"><h2 id="td-queue-h">Queue time</h2></div>
                {open.length ? (
                  <ul className="sd-bars">
                    {open.map((o) => (
                      <li key={o.id}>
                        <span>{o.id}</span>
                        <i><b style={{ width: `${(minutesOf(o) / maxMin) * 100}%` }} /></i>
                        <span className="vh-mono">{minutesOf(o)}m</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="sd-note">No open orders.</p>
                )}
                <p className="sd-note">Estimated writing minutes at the order's pen settings, all pieces.</p>
              </section>

              <section className="sd-card" aria-labelledby="td-load-h">
                <div className="sd-card-head"><h2 id="td-load-h">Workload</h2></div>
                <div className="sd-eval">
                  <div>
                    <b className="sd-big vh-mono">{tech ? loadOf(tech.id, all) : 0}</b>
                    <span className="sd-sub">orders in your queue</span>
                  </div>
                  <div>
                    <b className="sd-big vh-mono">{robots.filter((r) => r.state === 'idle').length}</b>
                    <span className="sd-sub">idle robots</span>
                  </div>
                </div>
                <p className="sd-note">{tech ? tech.skills.join(' · ') : ''}</p>
              </section>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}

const ROW_LABEL: Record<Phase, string> = { qc: 'Needs QC', live: 'Writing', ready: 'Ready', wait: 'Deposit pending', done: '' }

function TechRow({ order: o, group }: { order: Order; group: Phase }) {
  const [base] = STATUS_COLORS[o.status]
  const label = ROW_LABEL[group] || o.status
  const color = group === 'qc' || group === 'live' ? 'var(--accent-text)' : group === 'ready' ? 'var(--good)' : group === 'wait' ? 'var(--warn)' : base
  const to = group === 'qc' ? `/tech/qc/${encodeURIComponent(o.id)}` : `/tech/preview/${encodeURIComponent(o.id)}`
  return (
    <li>
      <Link to={to} className={`sd-row td-row td-row--${group}`}>
        <span className="sd-row-main">
          <span className="sd-row-title">{o.title}</span>
          <span className="sd-row-meta">{o.id} · {o.name || 'Customer'}</span>
        </span>
        <span className="sd-row-side">
          <span className="vh-chip" style={{ color }}>{label}</span>
          <span className="vh-mono sd-row-total">{o.assignment?.robotId} · {minutesOf(o)} min</span>
        </span>
      </Link>
    </li>
  )
}
