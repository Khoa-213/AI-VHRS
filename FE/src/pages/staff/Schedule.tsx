import { useState } from 'react'
import type { Job as JobFn } from '../../services/async'
import SkipLink from '../../components/ui/SkipLink'
import ThemeToggle from '../../components/ui/ThemeToggle'
import LanguageToggle from '../../components/ui/LanguageToggle'
import { useAsync } from '../../hooks/useAsync'
import { useLocale, useT } from '../../i18n'
import { Link, navigate } from '../../router/router'
import { orderErrorKey, errText } from '../../services/orders'
import {
  listJobs, listRobots, listTechnicians, orderJobs, rescheduleJob, scheduleOrder, scheduleQueue, scheduleSuggestion, unscheduleJob, type Job,
} from '../../services/workshop'
import StaffRail from './StaffRail'
import './dashboard.css'
import './polish.css'
import './workshop.css'

/** Manager only: paid orders waiting for a robot, a technician and a time slot (FR-40 to FR-42). This only writes the schedule; nothing contacts a robot. */
export default function Schedule({ id }: { id?: number }) {
  const t = useT()
  const queue = useAsync(() => scheduleQueue(), [], 30000)
  const rows = queue.data?.items ?? []
  return (
    <div className="sd">
      <SkipLink />
      <StaffRail active="schedule" />
      <main className="sd-body" id="main">
        <header className="sd-top">
          <div>
            <h1>{t('wk.scheduleTitle')}</h1>
            <p>{t('wk.scheduleLede')}</p>
          </div>
          <div className="sd-top-right">
            <ThemeToggle className="vh-icon-btn" />
            <LanguageToggle className="vh-icon-btn" />
          </div>
        </header>
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
                    </span>
                    <span className="wk-item-side">
                      <span className="vh-chip">{t(`ps.${r.production}`)}</span>
                      {r.durationMin !== null && <span className="vh-mono">{t('wk.minutes', { n: r.durationMin })}</span>}
                    </span>
                  </Link>
                </li>
              ))}
              {queue.data && !rows.length && <li className="sd-none">{t('wk.scheduleNone')}</li>}
            </ul>
          </aside>
          <section className="wk-detail">
            {id ? <ScheduleOrder key={id} id={id} onChanged={() => void queue.reload()} /> : <UpcomingJobs />}
          </section>
        </div>
      </main>
    </div>
  )
}

function UpcomingJobs() {
  const t = useT()
  const jobs = useAsync(() => listJobs({ status: ['SCHEDULED', 'PREPARING', 'WRITING', 'PAUSED'] }), [], 30000)
  return (
    <div className="wk-order">
      <section className="wk-block">
        <h3>{t('wk.upcoming')}</h3>
        {jobs.data && !jobs.data.items.length && <p className="sd-sub">{t('wk.noJobs')}</p>}
        <JobList jobs={jobs.data?.items ?? []} onChanged={() => void jobs.reload()} />
      </section>
    </div>
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

function ScheduleOrder({ id, onChanged }: { id: number; onChanged: () => void }) {
  const t = useT()
  const locale = useLocale()
  const sug = useAsync(() => scheduleSuggestion(id), [id])
  const jobs = useAsync(() => orderJobs(id), [id])
  const robots = useAsync(listRobots, [])
  const techs = useAsync(listTechnicians, [])
  const [robotId, setRobotId] = useState('')
  const [techId, setTechId] = useState('')
  const [slot, setSlot] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const active = (jobs.data ?? []).filter((j) => !['CANCELLED', 'DONE'].includes(j.status))

  const book = async (body: { robot_id: number; technician_id: number; slot_start: string; note?: string }) => {
    if (busy) return
    setBusy(true)
    setErr('')
    try {
      await scheduleOrder(id, body)
      await Promise.all([jobs.reload(), sug.reload()])
      onChanged()
      if (!active.length) navigate('/staff/schedule')
    } catch (e) {
      setErr(orderErrorKey(e))
    } finally {
      setBusy(false)
    }
  }

  const when = (iso: string) => new Date(iso).toLocaleString(locale, { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
  const s = sug.data

  return (
    <div className="wk-order">
      <header className="wk-order-head">
        <div>
          <h2>{t('wk.orderN', { id })}</h2>
          <Link to={`/staff/review/${id}`} className="vh-link">{t('wk.openOrder')}</Link>
        </div>
      </header>
      {err && <p className="lg-error" role="alert">{errText(t, err)}</p>}

      {!!active.length && (
        <section className="wk-block">
          <h3>{t('wk.jobs')}</h3>
          <JobList jobs={active} onChanged={() => { void jobs.reload(); void sug.reload(); onChanged() }} />
        </section>
      )}

      <section className="wk-block">
        <h3>{t('wk.suggestions')}</h3>
        {sug.loading && !s && <p className="sd-sub" role="status">{t('co.loading')}</p>}
        {!!sug.error && <p className="lg-error" role="alert">{errText(t, orderErrorKey(sug.error))}</p>}
        {s && (
          <>
            <p className="sd-sub">{t('wk.durationNote', { min: s.durationMin, qty: s.quantity })}</p>
            {s.stockWarnings.map((w) => <p key={w} className="wk-warn">{w}</p>)}
            {!s.suggestions.length && <p className="sd-sub">{t('wk.noSuggestions')}</p>}
            <ul className="wk-jobs">
              {s.suggestions.map((x) => (
                <li key={`${x.robotId}-${x.slotStart}`}>
                  <span>
                    <b>{x.robotCode}</b>{x.isSimulated ? ` · ${t('wk.simulated')}` : ''} · {x.technicianName}
                    <br />
                    <span className="sd-sub">{when(x.slotStart)} → {when(x.slotEnd)}{x.etaRisk ? ` · ${t('wk.etaRisk')}` : ''}</span>
                  </span>
                  <button className="vh-btn vh-btn--primary vh-btn--sm" disabled={busy} onClick={() => void book({ robot_id: x.robotId, technician_id: x.technicianId, slot_start: x.slotStart })}>{t('wk.bookThis')}</button>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      <section className="wk-block">
        <h3>{t('wk.manual')}</h3>
        <div className="wk-form">
          <label className="vh-label">
            {t('wk.robot')}
            <select className="vh-select" value={robotId} onChange={(e) => setRobotId(e.target.value)}>
              <option value="">{t('wk.choose')}</option>
              {(robots.data ?? []).map((r) => <option key={r.id} value={r.id} disabled={r.status === 'MAINTENANCE' || r.status === 'BROKEN'}>{r.code} · {t(`rs.${r.status}`)}</option>)}
            </select>
          </label>
          <label className="vh-label">
            {t('wk.technician')}
            <select className="vh-select" value={techId} onChange={(e) => setTechId(e.target.value)}>
              <option value="">{t('wk.choose')}</option>
              {(techs.data ?? []).map((x) => <option key={x.id} value={x.id}>{x.fullName} · {t('wk.activeJobs', { n: x.activeJobs })}</option>)}
            </select>
          </label>
          <label className="vh-label">
            {t('wk.slot')}
            <input className="vh-input" type="datetime-local" value={slot} onChange={(e) => setSlot(e.target.value)} />
          </label>
          <label className="vh-label wk-grow">
            {t('co.sum.note')}
            <input className="vh-input" value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} />
          </label>
          <button
            className="vh-btn vh-btn--primary vh-btn--md"
            disabled={busy || !robotId || !techId || !slot}
            onClick={() => void book({ robot_id: Number(robotId), technician_id: Number(techId), slot_start: new Date(slot).toISOString(), ...(note.trim() ? { note: note.trim() } : {}) })}
          >
            {t('wk.book')}
          </button>
        </div>
        <p className="sd-sub">{t('wk.slotHint')}</p>
      </section>
    </div>
  )
}
