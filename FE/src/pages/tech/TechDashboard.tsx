import { useLocale, useT, useTn } from '../../i18n'
import SkipLink from '../../components/ui/SkipLink'
import { STATUS_COLORS } from '../../constants/catalog'
import ThemeToggle from '../../components/ui/ThemeToggle'
import LanguageToggle from '../../components/ui/LanguageToggle'
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

const minutesOf = (o: Order) => Math.max(1, (o.spec.mins || 4) * (o.spec.qty || 1))

interface TechGroup {
  id: Phase
  label: string
  note: string
}

/** Labels are English catalog names, shown through the name translator. */
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
  const t = useT()
  const tn = useTn()
  const locale = useLocale()
  const hr = new Date().getHours()
  const greeting = t(hr < 12 ? 'sd.morning' : hr < 18 ? 'sd.afternoon' : 'sd.evening')
  const user = useUser()
  const all = useAllStaffOrders()
  const now = useNow(1000)
  const tech = roster().find((r) => r.id === user?.techId)
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
    label: tn(STATE_LABEL[s]),
    value: robots.filter((r) => r.state === s).length,
    color: RSTATE[s],
  }))
  const robotJob = (id: string) => mine.find((o) => phaseOf(o, now) === 'live' && o.run?.robotId === id)
  const today = new Date().toLocaleDateString(locale, { weekday: 'long', day: 'numeric', month: 'long' })

  return (
    <div className="sd">
      <SkipLink />
      <TechRail active="dashboard" />
      <main className="sd-body" id="main">
        <header className="sd-top">
          <div>
            <h1>{greeting}, {user?.name ?? t('td.technician')}</h1>
            <p>{today} · {tn(tech?.shift ?? 'Technician desk')}</p>
          </div>
          <div className="sd-top-right">
            <span className={`sd-state${counts.live ? ' busy' : ''}`}>{t('td.robotsState', { n: robots.length, state: t(counts.live ? 'td.stWriting' : 'td.stReady') })}</span>
            <ThemeToggle className="vh-icon-btn" />
            <LanguageToggle className="vh-icon-btn" />
          </div>
        </header>

        <div className="sd-grid">
          <section className="sd-card sd-orders" aria-labelledby="td-orders-h">
            <div className="sd-card-head">
              <h2 id="td-orders-h">{t('td.myOrders')}</h2>
              <span className="sd-tag">{t('td.assigned', { n: mine.length })}</span>
            </div>
            <div className="sd-total">
              <span>{t('td.queueTime')}</span>
              <b className="vh-mono">{t('td.min', { n: queueMinutes })}</b>
            </div>
            <div className="sd-groups">
              {GROUPS.map((g) => {
                const rows = inPhase(g.id)
                return (
                  <details key={g.id} className="sd-group" open={g.id !== 'done'}>
                    <summary>
                      <span className="sd-group-name">{tn(g.label)}</span>
                      <span className="sd-group-note">{tn(g.note)}</span>
                      <span className="sd-group-count vh-mono">{rows.length}</span>
                    </summary>
                    <ul>
                      {rows.map((o) => <TechRow key={o.id} order={o} group={g.id} />)}
                      {!rows.length && <li className="sd-none">{t('sd.nothing')}</li>}
                    </ul>
                  </details>
                )
              })}
            </div>
            {!mine.length && (
              <div className="sd-empty">
                <b>{t('td.none')}</b>
                <span>{t('td.noneBody')}</span>
              </div>
            )}
          </section>

          <div className="sd-stats">
            <div className="sd-kpis">
              <div className="sd-kpi accent"><span className="sd-label">{t('td.kpi.qc')}</span><b className="vh-mono">{counts.qc}</b><span className="sd-sub">{t('td.kpi.qcHint')}</span></div>
              <div className="sd-kpi"><span className="sd-label">{t('td.kpi.live')}</span><b className="vh-mono">{counts.live}</b><span className="sd-sub">{t('td.kpi.liveHint')}</span></div>
              <div className="sd-kpi"><span className="sd-label">{t('td.kpi.ready')}</span><b className="vh-mono">{counts.ready}</b><span className="sd-sub">{t('td.kpi.readyHint')}</span></div>
              <div className="sd-kpi"><span className="sd-label">{t('td.kpi.wait')}</span><b className="vh-mono">{counts.wait}</b><span className="sd-sub">{t('td.kpi.waitHint')}</span></div>
            </div>

            <section className="sd-card" aria-labelledby="td-robots-h">
              <div className="sd-card-head">
                <h2 id="td-robots-h">{t('td.myRobots')}</h2>
                <span className="sd-tag">{t('sd.simulated')}</span>
              </div>
              <div className="sd-robot">
                <div className="sd-donut">
                  <Donut slices={states} center={String(robots.length)} caption={t('td.robotsCaption')} />
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
                        <span className={`as-state as-state--${r.state}`}>{tn(STATE_LABEL[r.state])}</span>
                        <span className="sd-meter" role="progressbar" aria-valuenow={r.ink} aria-valuemin={0} aria-valuemax={100} aria-label={t('td.inkAria', { id: r.id })}>
                          <i style={{ width: `${r.ink}%` }} />
                        </span>
                        <span className="vh-mono td-ink">{r.ink}%</span>
                        <span className="sd-sub td-job">{job ? job.id : mine.some((o) => o.assignment?.robotId === r.id && phaseOf(o, now) !== 'done') ? t('td.orderWaiting') : t('td.noOrder')}</span>
                      </li>
                    )
                  })}
                </ul>
              </div>
            </section>

            <div className="sd-two">
              <section className="sd-card" aria-labelledby="td-queue-h">
                <div className="sd-card-head"><h2 id="td-queue-h">{t('td.queueTitle')}</h2></div>
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
                  <p className="sd-note">{t('td.noOpen')}</p>
                )}
                <p className="sd-note">{t('td.queueNote')}</p>
              </section>

              <section className="sd-card" aria-labelledby="td-load-h">
                <div className="sd-card-head"><h2 id="td-load-h">{t('td.workload')}</h2></div>
                <div className="sd-eval">
                  <div>
                    <b className="sd-big vh-mono">{tech ? loadOf(tech.id, all) : 0}</b>
                    <span className="sd-sub">{t('td.inQueue')}</span>
                  </div>
                  <div>
                    <b className="sd-big vh-mono">{robots.filter((r) => r.state === 'idle').length}</b>
                    <span className="sd-sub">{t('td.idleRobots')}</span>
                  </div>
                </div>
                <p className="sd-note">{tech ? tech.skills.map((k) => tn(k)).join(' · ') : ''}</p>
              </section>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}

function TechRow({ order: o, group }: { order: Order; group: Phase }) {
  const t = useT()
  const tn = useTn()
  const [base] = STATUS_COLORS[o.status]
  const label = group === 'done' ? t(`status.${o.status}`) : t(`td.row.${group}`)
  const color = group === 'qc' || group === 'live' ? 'var(--accent-text)' : group === 'ready' ? 'var(--good)' : group === 'wait' ? 'var(--warn)' : base
  const to = group === 'qc' ? `/tech/qc/${encodeURIComponent(o.id)}` : `/tech/preview/${encodeURIComponent(o.id)}`
  return (
    <li>
      <Link to={to} className={`sd-row td-row td-row--${group}`}>
        <span className="sd-row-main">
          <span className="sd-row-title">{tn(o.title)}</span>
          <span className="sd-row-meta">{o.id} · {o.name || t('common.customer')}</span>
        </span>
        <span className="sd-row-side">
          <span className="vh-chip" style={{ color }}>{label}</span>
          <span className="vh-mono sd-row-total">{o.assignment?.robotId} · {t('td.min', { n: minutesOf(o) })}</span>
        </span>
      </Link>
    </li>
  )
}
