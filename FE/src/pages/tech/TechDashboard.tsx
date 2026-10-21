import { ClipboardText, PlayCircle, Timer } from '@phosphor-icons/react'
import { Kpi } from '../../components/ws/parts'
import Shell from '../../components/ws/Shell'
import { useLocale, useT, useTn } from '../../i18n'
import { Link } from '../../router/router'
import { useAllStaffOrders, useUser } from '../../store/store'
import type { Order } from '../../types'
import { STATE_LABEL, loadOf, roster } from '../staff/technicians'
import { phaseOf, useNow, type Phase } from './phase'

const minutesOf = (o: Order) => Math.max(1, (o.spec.mins || 4) * (o.spec.qty || 1))

/** Labels are English catalog names, shown through the name translator. */
const GROUPS: { id: Phase; label: string; note: string }[] = [
  { id: 'qc', label: 'Photo and QC', note: 'Robot finished, check and send' },
  { id: 'live', label: 'Writing now', note: 'Robot is running' },
  { id: 'ready', label: 'Ready to preview', note: 'Deposit paid' },
  { id: 'wait', label: 'Waiting for deposit', note: 'Preview allowed' },
  { id: 'done', label: 'Finished', note: 'Written and shipped' },
]

const RCHIP = { idle: 'good', writing: 'orange', calibrating: 'info', offline: 'mute' } as const

/** The technician's day. The jobs and robots here still come from the local mock until the backend has technician endpoints (phase 4). */
export default function TechDashboard() {
  const t = useT()
  const tn = useTn()
  const locale = useLocale()
  const user = useUser()
  const all = useAllStaffOrders()
  const now = useNow(1000)
  const tech = roster().find((r) => r.id === user?.techId)
  const mine = all.filter((o) => o.assignment?.techId === user?.techId)
  const robots = tech?.robots ?? []
  const inPhase = (p: Phase) => mine.filter((o) => phaseOf(o, now) === p)
  const counts = { qc: inPhase('qc').length, live: inPhase('live').length, ready: inPhase('ready').length, wait: inPhase('wait').length }
  const open = mine.filter((o) => ['qc', 'live', 'ready', 'wait'].includes(phaseOf(o, now) ?? ''))
  const queueMinutes = open.reduce((a, o) => a + minutesOf(o), 0)
  const maxMin = Math.max(1, ...open.map(minutesOf))
  const robotJob = (id: string) => mine.find((o) => phaseOf(o, now) === 'live' && o.run?.robotId === id)
  const today = new Date().toLocaleDateString(locale, { weekday: 'long', day: 'numeric', month: 'long' })

  return (
    <Shell area="tech" active="dashboard" title={t('wk.hello', { name: user?.name ?? t('td.technician') })} lede={`${today} · ${tn(tech?.shift ?? 'Technician desk')}`}>
      <div className="row3">
        <Kpi icon={<ClipboardText size={20} aria-hidden />} tone="a" title={t('td.kpi.qc')} value={counts.qc} note={t('td.kpi.qcHint')} to="/tech/qc" />
        <Kpi icon={<PlayCircle size={20} aria-hidden />} tone="p" title={t('td.kpi.live')} value={counts.live} note={t('td.kpi.liveHint')} to="/tech/preview" />
        <Kpi icon={<Timer size={20} aria-hidden />} tone="b" title={t('td.kpi.ready')} value={counts.ready} note={t('td.kpi.readyHint')} to="/tech/preview" />
      </div>

      <div className="flex">
        <section className="panel" style={{ flex: '2 1 560px' }} aria-labelledby="td-orders-h">
          <div className="ph"><h2 id="td-orders-h">{t('td.myOrders')}</h2><span className="sub">{t('td.assigned', { n: mine.length })} · {t('td.queueTime')} {t('td.min', { n: queueMinutes })}</span></div>
          {GROUPS.map((g) => {
            const rows = inPhase(g.id)
            if (!rows.length) return null
            return (
              <div key={g.id} className="list">
                <div className="ph" style={{ padding: '6px 2px' }}><b>{tn(g.label)}</b><span className="sub">{tn(g.note)}</span></div>
                {rows.map((o) => <TechRow key={o.id} order={o} group={g.id} />)}
              </div>
            )
          })}
          {!mine.length && (
            <div className="sd-empty">
              <b>{t('td.none')}</b>
              <span>{t('td.noneBody')}</span>
            </div>
          )}
        </section>

        <section className="panel" style={{ flex: '1 1 340px' }} aria-labelledby="td-robots-h">
          <div className="ph"><h2 id="td-robots-h">{t('td.myRobots')}</h2><span className="sub">{t('td.robotsState', { n: robots.length, state: t(counts.live ? 'td.stWriting' : 'td.stReady') })}</span></div>
          <div className="list">
            {robots.map((r) => {
              const job = robotJob(r.id)
              return (
                <div key={r.id} className="item">
                  <div className="t">
                    <b>{r.id}</b>
                    <span>{job ? job.id : mine.some((o) => o.assignment?.robotId === r.id && phaseOf(o, now) !== 'done') ? t('td.orderWaiting') : t('td.noOrder')}</span>
                  </div>
                  <div style={{ width: 90 }} role="progressbar" aria-valuenow={r.ink} aria-valuemin={0} aria-valuemax={100} aria-label={t('td.inkAria', { id: r.id })}><div className="bar"><i style={{ width: `${r.ink}%` }} /></div></div>
                  <span className={`chip ${RCHIP[r.state]}`}>{tn(STATE_LABEL[r.state])}</span>
                </div>
              )
            })}
            {!robots.length && <p className="sub">{t('td.noRobots')}</p>}
          </div>
        </section>
      </div>

      <div className="flex">
        <section className="panel" style={{ flex: '1 1 440px' }} aria-labelledby="td-queue-h">
          <div className="ph"><h2 id="td-queue-h">{t('td.queueTitle')}</h2></div>
          {open.length ? (
            <div className="list">
              {open.map((o) => (
                <div key={o.id} className="item">
                  <div className="t"><b>{o.id}</b></div>
                  <div style={{ width: 200 }}><div className="bar"><i style={{ width: `${(minutesOf(o) / maxMin) * 100}%` }} /></div></div>
                  <b className="mono">{minutesOf(o)}m</b>
                </div>
              ))}
            </div>
          ) : (
            <p className="sub">{t('td.noOpen')}</p>
          )}
          <p className="sub">{t('td.queueNote')}</p>
        </section>

        <section className="panel" style={{ flex: '1 1 440px' }} aria-labelledby="td-load-h">
          <div className="ph"><h2 id="td-load-h">{t('td.workload')}</h2></div>
          <div className="flex">
            <div className="k" style={{ flex: '1 1 160px', boxShadow: 'none', background: 'var(--field)' }}><div className="num"><b>{tech ? loadOf(tech.id, all) : 0}</b></div><span className="sub">{t('td.inQueue')}</span></div>
            <div className="k" style={{ flex: '1 1 160px', boxShadow: 'none', background: 'var(--field)' }}><div className="num"><b>{robots.filter((r) => r.state === 'idle').length}</b></div><span className="sub">{t('td.idleRobots')}</span></div>
          </div>
          <p className="sub">{tech ? tech.skills.map((k) => tn(k)).join(' · ') : ''}</p>
        </section>
      </div>
    </Shell>
  )
}

function TechRow({ order: o, group }: { order: Order; group: Phase }) {
  const t = useT()
  const tn = useTn()
  const label = group === 'done' ? t(`status.${o.status}`) : t(`td.row.${group}`)
  const tone = group === 'qc' || group === 'live' ? 'orange' : group === 'ready' ? 'good' : group === 'wait' ? 'warn' : 'mute'
  const to = group === 'qc' ? `/tech/qc/${encodeURIComponent(o.id)}` : `/tech/preview/${encodeURIComponent(o.id)}`
  return (
    <Link to={to} className="item">
      <div className="t"><b>{tn(o.title)}</b><span>{o.id} · {o.name || t('common.customer')}</span></div>
      <span className={`chip ${tone}`}>{label}</span>
      <span className="mono sub">{o.assignment?.robotId} · {t('td.min', { n: minutesOf(o) })}</span>
    </Link>
  )
}
