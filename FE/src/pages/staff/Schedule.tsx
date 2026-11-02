import { useState } from 'react'
import Shell from '../../components/ws/Shell'
import type { Job as JobFn } from '../../services/async'
import { useAsync } from '../../hooks/useAsync'
import { useLocale, useT } from '../../i18n'
import { Link, navigate } from '../../router/router'
import { orderErrorKey, errText } from '../../services/orders'
import {
  listJobs, listRobots, listTechnicians, orderJobs, rescheduleJob, scheduleQueue, unscheduleJob, type Job,
} from '../../services/workshop'
import ScheduleCalendar from './ScheduleCalendar'

/** Manager only: paid orders waiting for a robot, a technician and a time slot (FR-40 to FR-42). This only writes the schedule; nothing contacts a robot. */
export default function Schedule({ id }: { id?: number }) {
  const t = useT()
  const queue = useAsync(() => scheduleQueue(), [], 30000)
  const rows = queue.data?.items ?? []
  const locale = useLocale()
  const [version, setVersion] = useState(0)
  const changed = () => {
    setVersion((v) => v + 1)
    void queue.reload()
  }
  const current = rows.find((r) => r.orderId === id)
  return (
    <Shell area="manager" active="schedule" title={t('wk.scheduleTitle')} lede={t('wk.scheduleLede')}>
      <div className="wk-layout">
        <aside className="wk-list" aria-label={t('wk.scheduleQueue')}>
          <h2 className="wk-list-title">{t('wk.scheduleQueue')}</h2>
          {!!queue.error && <p className="lg-error" role="alert">{errText(t, orderErrorKey(queue.error))}</p>}
          {queue.loading && !queue.data && <p className="sd-sub" role="status">{t('co.loading')}</p>}
          <ul>
            {rows.map((r) => (
              <li key={r.orderId}>
                <Link to={`/staff/schedule/${r.orderId}`} className={`wk-item${r.orderId === id ? ' on' : ''}`}>
                  <span className="wk-item-main">
                    <b>{r.code}</b>
                    <span>{r.customerName} · {t(`ot.${r.type}`)} × {r.quantity}</span>
                    <span>{r.eta ? t('wk.cal.etaOn', { date: new Date(`${r.eta}T00:00:00Z`).toLocaleDateString(locale, { timeZone: 'UTC', day: '2-digit', month: '2-digit' }) }) : t('wk.cal.noEta')}</span>
                  </span>
                  <span className="wk-item-side">
                    <span className="chip info">{t(`wk.ps.${r.production}`)}</span>
                    {r.durationMin !== null && <span className="mono">{t('wk.minutes', { n: r.durationMin })}</span>}
                  </span>
                </Link>
              </li>
            ))}
            {queue.data && !rows.length && <li className="sd-sub">{t('wk.scheduleNone')}</li>}
          </ul>
        </aside>
        <section className="wk-detail">
          <div className="wk-order">
            <ScheduleCalendar
              key={id ?? 'all'}
              order={id ? { id, code: current?.code ?? t('wk.orderN', { id }) } : undefined}
              version={version}
              onBooked={() => {
                changed()
                navigate('/staff/schedule')
              }}
            />
            {id ? <OrderJobs id={id} version={version} onChanged={changed} /> : <UpcomingJobs version={version} onChanged={changed} />}
          </div>
        </section>
      </div>
    </Shell>
  )
}

function UpcomingJobs({ version, onChanged }: { version: number; onChanged: () => void }) {
  const t = useT()
  const jobs = useAsync(() => listJobs({ status: ['SCHEDULED', 'PREPARING', 'WRITING', 'PAUSED'] }), [version], 30000)
  return (
    <section className="wk-block">
      <h3>{t('wk.upcoming')}</h3>
      {jobs.data && !jobs.data.items.length && <p className="sd-sub">{t('wk.noJobs')}</p>}
      <JobList jobs={jobs.data?.items ?? []} onChanged={onChanged} />
    </section>
  )
}

function JobList({ jobs, onChanged }: { jobs: Job[]; onChanged: () => void }) {
  const t = useT()
  const locale = useLocale()
  const robots = useAsync(listRobots, [])
  const techs = useAsync(listTechnicians, [])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [asking, setAsking] = useState<{ id: number; kind: 'remove' | 'move' } | null>(null)
  const [reason, setReason] = useState('')
  const [robotId, setRobotId] = useState('')
  const [techId, setTechId] = useState('')
  const [slot, setSlot] = useState('')

  const close = () => {
    setAsking(null)
    setReason('')
    setRobotId('')
    setTechId('')
    setSlot('')
  }
  const run = async (job: JobFn) => {
    setBusy(true)
    setErr('')
    try {
      await job()
      close()
      onChanged()
    } catch (e) {
      setErr(orderErrorKey(e))
    } finally {
      setBusy(false)
    }
  }
  const when = (iso: string) => new Date(iso).toLocaleString(locale, { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })

  return (
    <>
      {err && <p className="lg-error" role="alert">{errText(t, err)}</p>}
      <ul className="wk-jobs">
        {jobs.map((j) => (
          <li key={j.id} className="wk-job">
            <span className="wk-job-main">
              <span>
                <b>{j.orderCode}</b> · {j.robotCode} · {j.technicianName}{j.isRewrite ? ` · ${t('wk.rewrite')}` : ''}
                <br />
                <span className="sd-sub">{when(j.slotStart)} → {when(j.slotEnd)} · {t(`js.${j.status}`)}</span>
              </span>
              {j.status === 'SCHEDULED' && !asking && (
                <span className="wk-inline">
                  <button className="vh-link" onClick={() => setAsking({ id: j.id, kind: 'move' })}>{t('wk.move')}</button>
                  <button className="vh-link" onClick={() => setAsking({ id: j.id, kind: 'remove' })}>{t('wk.unschedule')}</button>
                </span>
              )}
            </span>
            {asking?.id === j.id && (
              <div className="wk-form">
                {asking.kind === 'move' && (
                  <>
                    <label className="vh-label">
                      {t('wk.robot')}
                      <select className="vh-select" value={robotId} onChange={(e) => setRobotId(e.target.value)}>
                        <option value="">{t('wk.keep')}</option>
                        {(robots.data ?? []).map((r) => <option key={r.id} value={r.id} disabled={r.status === 'MAINTENANCE' || r.status === 'BROKEN'}>{r.code} · {t(`rs.${r.status}`)}</option>)}
                      </select>
                    </label>
                    <label className="vh-label">
                      {t('wk.technician')}
                      <select className="vh-select" value={techId} onChange={(e) => setTechId(e.target.value)}>
                        <option value="">{t('wk.keep')}</option>
                        {(techs.data ?? []).map((x) => <option key={x.id} value={x.id}>{x.fullName}</option>)}
                      </select>
                    </label>
                    <label className="vh-label">
                      {t('wk.slot')}
                      <input className="vh-input" type="datetime-local" value={slot} onChange={(e) => setSlot(e.target.value)} />
                    </label>
                  </>
                )}
                <label className="vh-label wk-grow">
                  {t('wk.unscheduleReason')}
                  <input className="vh-input" value={reason} maxLength={1000} onChange={(e) => setReason(e.target.value)} />
                </label>
                <button className="vh-btn vh-btn--ghost vh-btn--sm" onClick={close}>{t('ov.back')}</button>
                <button
                  className="vh-btn vh-btn--primary vh-btn--sm"
                  disabled={busy || !reason.trim() || (asking.kind === 'move' && !robotId && !techId && !slot)}
                  onClick={() => void run(() => (asking.kind === 'remove'
                    ? unscheduleJob(j.id, reason.trim())
                    : rescheduleJob(j.id, {
                      ...(robotId ? { robot_id: Number(robotId) } : {}),
                      ...(techId ? { technician_id: Number(techId) } : {}),
                      ...(slot ? { slot_start: new Date(slot).toISOString() } : {}),
                      reason: reason.trim(),
                    })))}
                >
                  {t(asking.kind === 'remove' ? 'wk.unschedule' : 'wk.move')}
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </>
  )
}

function OrderJobs({ id, version, onChanged }: { id: number; version: number; onChanged: () => void }) {
  const t = useT()
  const jobs = useAsync(() => orderJobs(id), [id, version])
  const active = (jobs.data ?? []).filter((j) => !['CANCELLED', 'DONE'].includes(j.status))
  return (
    <>
      <Link to={`/staff/review/${id}`} className="vh-link wk-self">{t('wk.openOrder')}</Link>
      {!!active.length && (
        <section className="wk-block">
          <h3>{t('wk.jobs')}</h3>
          <JobList jobs={active} onChanged={onChanged} />
        </section>
      )}
    </>
  )
}
