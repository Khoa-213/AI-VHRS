import { CheckCircle, Eye, ListChecks, WarningOctagon, XCircle } from '@phosphor-icons/react'
import { useState } from 'react'
import Shell from '../../components/ws/Shell'
import { useAsync } from '../../hooks/useAsync'
import { useLocale, useT } from '../../i18n'
import { Link } from '../../router/router'
import type { Job } from '../../services/async'
import {
  ackManagerAlert, alertCatalog, jobCompliance, managerAlerts, managerIncidents, managerJob, managerJobEvents, managerJobQuality,
  managerRobotStatus, managerRuns, patchAlertCatalog, resolveIncident, resolveManagerAlert, robotHealth,
  type AlertCatalogEntry, type ManagerAlert,
} from '../../services/managerOps'
import { errText, orderErrorKey } from '../../services/orders'
import { Chip, LevelChip, Panel, Period, StateChip, type Tone } from './managerKit'

const HEALTH_DAYS = [7, 30, 90] as const
const ROLES = ['TECHNICAL_STAFF', 'MANAGER', 'STAFF'] as const
const RUN_TONE: Record<string, Tone> = { DONE: 'good', DRY_RUN_DONE: 'good', STOPPED: 'warn', REFUSED: 'warn', FAULT: 'bad', UNKNOWN: 'mute' }
const STEP_TONE: Record<string, Tone> = { PASS: 'good', FAIL: 'bad', PENDING: 'mute', NOT_APPLICABLE: 'mute' }
const VERDICT_TONE: Record<string, Tone> = { PASS: 'good', NEEDS_REVIEW: 'warn', FAIL: 'bad' }
type Patch = Parameters<typeof patchAlertCatalog>[1]

const stepIcon = (status: string) => {
  if (status === 'PASS') return <CheckCircle size={15} weight="fill" aria-hidden />
  if (status === 'FAIL') return <XCircle size={15} weight="fill" aria-hidden />
  return <ListChecks size={15} aria-hidden />
}

/** A job chosen from the dashboard (`?job=`) opens its detail here. */
const jobFromUrl = () => {
  const n = Number(new URLSearchParams(window.location.search).get('job'))
  return Number.isInteger(n) && n > 0 ? n : null
}

/**
 * Manager robot desk in the Staff frame: every robot's state (`GET /manager/robot-status`), its health over N days, the open
 * alerts with acknowledge and close (Managers may close red ones), incidents, the agent's runs, and for a chosen job its detail,
 * process check, events and quality results; then the alert catalogue. Alert, step and quality sentences come from the backend in
 * Vietnamese and are shown as received. Scheduling stays on the Schedule screen.
 */
export default function Robots() {
  const t = useT()
  const locale = useLocale()
  const status = useAsync(managerRobotStatus, [], 15000)
  const [picked, setPicked] = useState<number | null>(null)
  const robotId = picked ?? status.data?.[0]?.robotId ?? null
  const robot = status.data?.find((r) => r.robotId === robotId) ?? null
  const [days, setDays] = useState<(typeof HEALTH_DAYS)[number]>(30)
  const health = useAsync(async () => (robotId ? robotHealth(robotId, days) : null), [robotId, days])
  const [showClosed, setShowClosed] = useState(false)
  const alerts = useAsync(() => managerAlerts({ open: !showClosed, pageSize: 50 }), [showClosed], 15000)
  const incidents = useAsync(() => managerIncidents({ resolved: false }), [], 30000)
  const [runPage, setRunPage] = useState(1)
  const runs = useAsync(async () => (robotId ? managerRuns({ robotId, page: runPage, pageSize: 10 }) : null), [robotId, runPage], 30000)
  const [jobId, setJobId] = useState<number | null>(jobFromUrl)
  const job = useAsync(async () => (jobId ? managerJob(jobId) : null), [jobId])
  const compliance = useAsync(async () => (jobId ? jobCompliance(jobId) : null), [jobId])
  const events = useAsync(async () => (jobId ? managerJobEvents(jobId) : null), [jobId])
  const quality = useAsync(async () => (jobId ? managerJobQuality(jobId) : null), [jobId])
  const catalog = useAsync(alertCatalog, [])

  const [notes, setNotes] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState<string | null>(null)
  const [err, setErr] = useState('')
  const [done, setDone] = useState('')

  const act = async (key: string, task: Job, after: Job, ok: string) => {
    if (busy) return
    setBusy(key); setErr(''); setDone('')
    try {
      await task()
      setNotes((n) => ({ ...n, [key]: '' }))
      setDone(ok)
    } catch (e) {
      setErr(errText(t, orderErrorKey(e)))
    } finally {
      setBusy(null)
      await after()
    }
  }

  const resolveAlert = (a: ManagerAlert) => {
    const note = (notes[`a${a.id}`] ?? '').trim()
    if (a.level >= 4 && !window.confirm(t('mgr.al.confirmRed', { code: a.robotCode }))) return
    void act(`a${a.id}`, () => resolveManagerAlert(a.id, note), async () => { await alerts.reload(); await status.reload() }, t('mgr.al.closed'))
  }

  const toggleCatalog = (c: AlertCatalogEntry, patch: Patch) =>
    void act(`c${c.code}`, () => patchAlertCatalog(c.code, patch), catalog.reload, t('mgr.cat.saved'))

  const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString(locale, { dateStyle: 'medium', timeStyle: 'short' }) : '–')
  const age = (min: number | null) => {
    if (min === null) return t('mgr.rb.never')
    if (min < 60) return t('mgr.rb.minutes', { n: Math.round(min) })
    if (min < 60 * 48) return t('mgr.rb.hours', { n: Math.round(min / 60) })
    return t('mgr.rb.days', { n: Math.round(min / 1440) })
  }
  const seen = (s: number | null) => (s === null ? t('mgr.rb.never') : age(s / 60))
  const redOpen = (a: ManagerAlert) => a.level >= 4 && !a.resolvedAt
  const reds = (alerts.data?.items ?? []).filter(redOpen)
  const moreAlerts = !!alerts.data && alerts.data.total > alerts.data.items.length
  const h = health.data
  const runTotal = h ? Object.values(h.runsByResult).reduce((a, n) => a + n, 0) : 0
  const runPages = runs.data ? Math.max(1, Math.ceil(runs.data.total / runs.data.pageSize)) : 1
  const j = job.data
  const moreEvents = !!events.data && events.data.total > events.data.items.length

  return (
    <Shell area="manager" active="robots" title={t('mgr.nav.robots')}>
      {err && <p className="lg-error" role="alert">{err}</p>}
      {done && <p className="note-ok" role="status">{done}</p>}

      {reds.length > 0 && (
        <p className="mgr-estop" role="alert"><WarningOctagon size={24} weight="fill" aria-hidden />{t('mgr.al.redBanner', { n: reds.length })}</p>
      )}

      <Panel title={t('mgr.rb.title')} sub={t('mgr.rb.sub')}>
        {!!status.error && <p className="lg-error" role="alert">{errText(t, orderErrorKey(status.error))}</p>}
        {status.loading && !status.data && <p className="sub" role="status">{t('co.loading')}</p>}
        {status.data && !status.data.length && <p className="sub">{t('wk.noRobots')}</p>}
        <div className="mgr-robots">
          {(status.data ?? []).map((r) => (
            <button key={r.robotId} type="button" className={`mgr-robot${r.robotId === robotId ? ' on' : ''}`} aria-pressed={r.robotId === robotId} onClick={() => { setPicked(r.robotId); setRunPage(1) }}>
              <span className="mgr-robot-top"><b>{r.robotCode}</b><StateChip state={r.state} /></span>
              {r.alerts.length > 0 && <span className="mgr-robot-top"><LevelChip level={r.level} /><span className="sub">{t('mgr.robots.alerts', { n: r.alerts.length })}</span></span>}
              <dl>
                <dt>{t('mgr.rb.mode')}</dt><dd>{r.mode ? t(`rb.mode.${r.mode}`) : '–'}</dd>
                <dt>{t('mgr.rb.link')}</dt><dd>{r.connection === 'ONLINE' ? t('rb.online') : t('rb.offline')}</dd>
                <dt>{t('mgr.rb.seen')}</dt><dd>{seen(r.secondsSinceSeen)}</dd>
                <dt>{t('mgr.rb.job')}</dt><dd>{r.jobId ? `#${r.jobId} · ${r.jobStatus ? t(`js.${r.jobStatus}`) : ''}` : t('mgr.rb.noJob')}</dd>
                {r.openRun && <><dt>{t('mgr.rb.progress')}</dt><dd>{t('mgr.rb.strokes', { n: r.openRun.completedStrokes, total: r.openRun.totalStrokes })}</dd></>}
                <dt>{t('mgr.rb.calibration')}</dt><dd>{age(r.calibrationAgeMin)}</dd>
                {r.agentVersion && <><dt>{t('mgr.rb.agent')}</dt><dd className="mono">{r.agentVersion}</dd></>}
              </dl>
            </button>
          ))}
        </div>
      </Panel>

      {robot && (
        <Panel
          title={t('mgr.hl.title', { code: robot.robotCode })}
          sub={robot.headline}
          aside={<Period options={HEALTH_DAYS} value={days} onChange={setDays} label={t('staff.ui.period')} text={(n) => t('staff.ui.days', { n })} />}
        >
          {!!health.error && <p className="lg-error" role="alert">{errText(t, orderErrorKey(health.error))}</p>}
          {health.loading && !h && <p className="sub" role="status">{t('co.loading')}</p>}
          {h && (
            <>
              <div className="mgr-health">
                <div><b>{runTotal}</b><span>{t('mgr.hl.runs')}</span></div>
                <div><b>{t('mgr.hl.hoursValue', { n: (h.runSeconds / 3600).toLocaleString(locale, { maximumFractionDigits: 1 }) })}</b><span>{t('mgr.hl.time')}</span></div>
                <div><b>{h.safetyStops}</b><span>{t('mgr.hl.stops')}</span></div>
                <div><b>{h.unresolvedRed}</b><span>{t('mgr.hl.red')}</span></div>
                <div><b>{h.openIncidents}</b><span>{t('mgr.hl.incidents')}</span></div>
                <div><b>{h.inBandPctAvg === null ? '–' : `${h.inBandPctAvg.toLocaleString(locale, { maximumFractionDigits: 1 })}%`}</b><span>{t('mgr.hl.band')}</span></div>
              </div>
              <div className="mgr-grid2">
                <div className="mgr-table-wrap">
                  <table className="mgr-table">
                    <caption className="staff-sr">{t('mgr.hl.byResult')}</caption>
                    <thead><tr><th scope="col">{t('mgr.hl.byResult')}</th><th scope="col" className="num">{t('mgr.count')}</th></tr></thead>
                    <tbody>
                      {Object.entries(h.runsByResult).map(([k, n]) => <tr key={k}><th scope="row"><Chip tone={RUN_TONE[k] ?? 'mute'}>{t(`mgr.run.${k}`)}</Chip></th><td className="num">{n}</td></tr>)}
                      {!runTotal && <tr><td colSpan={2}>{t('mgr.hl.noRuns')}</td></tr>}
                    </tbody>
                  </table>
                </div>
                <div className="mgr-table-wrap">
                  <table className="mgr-table">
                    <caption className="staff-sr">{t('mgr.hl.byLevel')}</caption>
                    <thead><tr><th scope="col">{t('mgr.hl.byLevel')}</th><th scope="col" className="num">{t('mgr.count')}</th></tr></thead>
                    <tbody>
                      {[4, 3, 2, 1].map((lv) => <tr key={lv}><th scope="row"><LevelChip level={lv} /></th><td className="num">{h.alertsByLevel[String(lv)] ?? 0}</td></tr>)}
                    </tbody>
                  </table>
                </div>
              </div>
              <p className="sub">{t('mgr.hl.since', { when: when(h.since) })}</p>
            </>
          )}
        </Panel>
      )}

      <Panel
        title={t('mgr.al.title')}
        sub={t('mgr.al.sub')}
        aside={<Period options={[false, true] as const} value={showClosed} onChange={setShowClosed} label={t('mgr.al.title')} text={(v) => t(v ? 'mgr.al.all' : 'mgr.al.open')} />}
      >
        {!!alerts.error && <p className="lg-error" role="alert">{errText(t, orderErrorKey(alerts.error))}</p>}
        {alerts.loading && !alerts.data && <p className="sub" role="status">{t('co.loading')}</p>}
        {alerts.data && !alerts.data.items.length && <div className="mgr-empty"><b>{t('rb.noAlerts')}</b></div>}
        <div className="mgr-alerts">
          {(alerts.data?.items ?? []).map((a) => {
            const key = `a${a.id}`
            const note = notes[key] ?? ''
            const closed = !!a.resolvedAt
            return (
              <article key={a.id} className={`mgr-alert${redOpen(a) ? ' red' : ''}`} aria-label={`${a.robotCode} ${a.code}`}>
                <div className="mgr-alert-head">
                  <LevelChip level={a.level} />
                  <b>{a.robotCode}</b>
                  <span className="mono sub">{a.code}</span>
                  {closed
                    ? <Chip tone="good">{t('mgr.al.isClosed')}</Chip>
                    : a.acknowledgedAt ? <Chip tone="mute">{t('mgr.al.seen')}</Chip> : <Chip tone="warn">{t('mgr.al.new')}</Chip>}
                </div>
                {redOpen(a) && <p className="mgr-estop"><WarningOctagon size={18} weight="fill" aria-hidden />{t('mgr.al.estop')}</p>}
                <p className="title">{a.title}</p>
                <p>{a.action}</p>
                <p className="sub">
                  {t('mgr.al.meta', { when: when(a.raisedAt), n: a.occurrences })}
                  {a.jobId ? ` · ${t('mgr.al.job', { id: a.jobId })}` : ''}
                </p>
                {closed && a.resolutionNote && <p className="sub">{t('mgr.al.note', { note: a.resolutionNote, when: when(a.resolvedAt) })}</p>}
                {!closed && (
                  <div className="mgr-actions">
                    {!a.acknowledgedAt && (
                      <button type="button" className="btn ghost sm" disabled={!!busy} onClick={() => void act(key, () => ackManagerAlert(a.id), alerts.reload, t('mgr.al.acked'))}>
                        <Eye size={16} aria-hidden />{t('rb.ack')}
                      </button>
                    )}
                    <label className="vh-label">
                      {t('rb.resolveNote')}
                      <input className="vh-input" value={note} maxLength={500} placeholder={t('mgr.al.notePh')} onChange={(e) => setNotes({ ...notes, [key]: e.target.value })} />
                    </label>
                    <button type="button" className={`btn sm ${a.level >= 4 ? 'danger' : 'acc'}`} disabled={!!busy || note.trim().length < 3} onClick={() => resolveAlert(a)}>
                      <CheckCircle size={16} aria-hidden />{t(busy === key ? 'mgr.working' : 'rb.resolve')}
                    </button>
                  </div>
                )}
              </article>
            )
          })}
        </div>
        {moreAlerts && <p className="sub">{t('mgr.al.more', { n: alerts.data?.items.length ?? 0, total: alerts.data?.total ?? 0 })}</p>}
      </Panel>

      <Panel title={t('mgr.in.title')} sub={t('mgr.in.sub')}>
        {!!incidents.error && <p className="lg-error" role="alert">{errText(t, orderErrorKey(incidents.error))}</p>}
        {incidents.loading && !incidents.data && <p className="sub" role="status">{t('co.loading')}</p>}
        {incidents.data && !incidents.data.items.length && <p className="sub">{t('mgr.in.none')}</p>}
        <div className="mgr-alerts">
          {(incidents.data?.items ?? []).map((i) => {
            const key = `i${i.id}`
            const note = notes[key] ?? ''
            const code = status.data?.find((r) => r.robotId === i.robotId)?.robotCode
            return (
              <article key={i.id} className="mgr-alert">
                <div className="mgr-alert-head">
                  <Chip tone="warn">{t(`td.flow.incident.${i.type}`)}</Chip>
                  {code && <b>{code}</b>}
                  {i.jobId && <button type="button" className="vh-link" onClick={() => setJobId(i.jobId)}>{t('mgr.al.job', { id: i.jobId })}</button>}
                  <span className="sub">{when(i.createdAt)}</span>
                </div>
                <p>{i.description}</p>
                {i.robotStatusAfter && <p className="sub">{t('mgr.in.after', { status: t(`rs.${i.robotStatusAfter}`) })}</p>}
                <div className="mgr-actions">
                  <label className="vh-label">
                    {t('mgr.in.note')}
                    <input className="vh-input" value={note} maxLength={1000} onChange={(e) => setNotes({ ...notes, [key]: e.target.value })} />
                  </label>
                  <button type="button" className="btn acc sm" disabled={!!busy || !note.trim()} onClick={() => void act(key, () => resolveIncident(i.id, note.trim()), incidents.reload, t('mgr.in.closed'))}>
                    <CheckCircle size={16} aria-hidden />{t(busy === key ? 'mgr.working' : 'mgr.in.close')}
                  </button>
                </div>
              </article>
            )
          })}
        </div>
      </Panel>

      {robot && (
        <Panel title={t('mgr.run.title', { code: robot.robotCode })}>
          {!!runs.error && <p className="lg-error" role="alert">{errText(t, orderErrorKey(runs.error))}</p>}
          {runs.loading && !runs.data && <p className="sub" role="status">{t('co.loading')}</p>}
          {runs.data && !runs.data.items.length && <p className="sub">{t('mgr.hl.noRuns')}</p>}
          {runs.data && runs.data.items.length > 0 && (
            <>
              <div className="mgr-table-wrap">
                <table className="mgr-table">
                  <thead>
                    <tr>
                      <th scope="col">{t('mgr.run.started')}</th>
                      <th scope="col">{t('mgr.rb.job')}</th>
                      <th scope="col">{t('mgr.run.result')}</th>
                      <th scope="col" className="num">{t('mgr.run.strokes')}</th>
                      <th scope="col"><span className="staff-sr">{t('mgr.run.check')}</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {runs.data.items.map((x) => (
                      <tr key={x.id} className={x.jobId === jobId ? 'on' : undefined}>
                        <td>{when(x.startedAt)}{x.dryRun ? ` · ${t('mgr.run.dry')}` : ''}</td>
                        <td>#{x.jobId}</td>
                        <td>{x.result ? <Chip tone={RUN_TONE[x.result] ?? 'mute'}>{t(`mgr.run.${x.result}`)}</Chip> : <Chip tone="navy">{t('mgr.run.running')}</Chip>}</td>
                        <td className="num">{x.completedStrokes}/{x.totalStrokes}</td>
                        <td><button type="button" className="vh-link" onClick={() => setJobId(x.jobId)}>{t('mgr.run.check')}</button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {runPages > 1 && (
                <div className="mgr-pager">
                  <span>{t('mgr.pager', { page: runPage, pages: runPages })}</span>
                  <div>
                    <button type="button" className="btn ghost sm" disabled={runPage <= 1} onClick={() => setRunPage(runPage - 1)}>{t('mgr.prev')}</button>
                    <button type="button" className="btn ghost sm" disabled={runPage >= runPages} onClick={() => setRunPage(runPage + 1)}>{t('mgr.next')}</button>
                  </div>
                </div>
              )}
            </>
          )}
        </Panel>
      )}

      <Panel
        title={jobId ? t('mgr.job.title', { id: jobId }) : t('mgr.cp.title')}
        sub={jobId ? undefined : t('mgr.cp.pick')}
        aside={jobId ? <button type="button" className="vh-link" onClick={() => setJobId(null)}>{t('mgr.job.close')}</button> : undefined}
      >
        {jobId && (
          <>
            {!!job.error && <p className="lg-error" role="alert">{errText(t, orderErrorKey(job.error))}</p>}
            {job.loading && !j && <p className="sub" role="status">{t('co.loading')}</p>}
            {j && (
              <dl className="kv">
                <div><dt>{t('mgr.rp.order')}</dt><dd><Link to={`/staff/review/${j.orderId}`} className="vh-link">{j.orderCode}</Link></dd></div>
                <div><dt>{t('mgr.rp.robot')}</dt><dd>{j.robotCode}</dd></div>
                <div><dt>{t('mgr.job.tech')}</dt><dd>{j.technicianName || '–'}</dd></div>
                <div><dt>{t('mgr.job.status')}</dt><dd><Chip tone={j.status === 'FAILED' ? 'bad' : j.status === 'DONE' ? 'good' : 'navy'}>{t(`js.${j.status}`)}</Chip>{j.isRewrite ? ` ${t('mgr.rewrite')}` : ''}</dd></div>
                <div><dt>{t('mgr.job.slot')}</dt><dd>{when(j.slotStart)} · {t('mgr.job.minutes', { n: j.estimatedMin })}</dd></div>
                <div><dt>{t('mgr.rb.progress')}</dt><dd>{j.progressPct === null ? '–' : `${Math.round(j.progressPct)}%`}</dd></div>
                <div><dt>{t('mgr.job.simulation')}</dt><dd>{j.simulationPassed === null ? '–' : t(j.simulationPassed ? 'mgr.cp.PASS' : 'mgr.cp.FAIL')}</dd></div>
              </dl>
            )}

            <h3 className="mgr-h3">{t('mgr.cp.title')}</h3>
            {!!compliance.error && <p className="lg-error" role="alert">{errText(t, orderErrorKey(compliance.error))}</p>}
            {compliance.loading && !compliance.data && <p className="sub" role="status">{t('co.loading')}</p>}
            {compliance.data && (
              <>
                {compliance.data.followedProcess ? <Chip tone="good">{t('mgr.cp.ok')}</Chip> : <Chip tone="bad">{t('mgr.cp.bad')}</Chip>}
                <ul className="mgr-steps">
                  {compliance.data.steps.map((s) => (
                    <li key={s.key}>
                      <span>{stepIcon(s.status)}<span>{s.label}{s.detail && <span className="sub"> · {s.detail}</span>}</span></span>
                      <Chip tone={STEP_TONE[s.status]}>{t(`mgr.cp.${s.status}`)}</Chip>
                    </li>
                  ))}
                </ul>
                {compliance.data.exceptions.map((x) => <p key={x} className="mgr-callout">{x}</p>)}
              </>
            )}

            <div className="mgr-grid2">
              <div>
                <h3 className="mgr-h3">{t('mgr.job.events')}</h3>
                {!!events.error && <p className="lg-error" role="alert">{errText(t, orderErrorKey(events.error))}</p>}
                {events.data && !events.data.items.length && <p className="sub">{t('mgr.job.noEvents')}</p>}
                <ul className="mgr-steps">
                  {(events.data?.items ?? []).map((e) => (
                    <li key={e.id}>
                      <span>{t(`td.flow.event.${e.type}`)}{e.strokeIndex !== null ? <span className="sub"> · {t('mgr.job.stroke', { n: e.strokeIndex })}</span> : null}</span>
                      <span className="sub">{when(e.at)}</span>
                    </li>
                  ))}
                </ul>
                {moreEvents && <p className="sub">{t('mgr.al.more', { n: events.data?.items.length ?? 0, total: events.data?.total ?? 0 })}</p>}
              </div>
              <div>
                <h3 className="mgr-h3">{t('mgr.q.title')}</h3>
                {!!quality.error && <p className="lg-error" role="alert">{errText(t, orderErrorKey(quality.error))}</p>}
                {quality.data && !quality.data.length && <p className="sub">{t('mgr.q.none')}</p>}
                <div className="mgr-alerts">
                  {(quality.data ?? []).map((q) => (
                    <article key={q.id} className="mgr-alert">
                      <div className="mgr-alert-head">
                        <Chip tone={VERDICT_TONE[q.verdict] ?? 'mute'}>{t(`mgr.q.${q.verdict}`)}</Chip>
                        <span className="sub">{t('mgr.q.photo', { id: q.photoId, page: q.page })} · {when(q.createdAt)}</span>
                      </div>
                      <p>{q.advisory}</p>
                      {q.overlayUrl && <a href={q.overlayUrl} target="_blank" rel="noreferrer" className="vh-link">{t('mgr.q.overlay')}</a>}
                    </article>
                  ))}
                </div>
                {quality.data && quality.data.length > 0 && <p className="sub">{t('mgr.q.note')}</p>}
              </div>
            </div>
          </>
        )}
      </Panel>

      <Panel title={t('mgr.cat.title')} sub={t('mgr.cat.sub')}>
        <details className="mgr-more">
          <summary>{t('mgr.cat.show', { n: catalog.data?.length ?? 0 })}</summary>
          {!!catalog.error && <p className="lg-error" role="alert">{errText(t, orderErrorKey(catalog.error))}</p>}
          <div className="mgr-table-wrap" style={{ marginTop: 14 }}>
            <table className="mgr-table">
              <thead>
                <tr>
                  <th scope="col">{t('mgr.cat.code')}</th>
                  <th scope="col">{t('mgr.cat.level')}</th>
                  <th scope="col">{t('mgr.cat.text')}</th>
                  <th scope="col">{t('mgr.cat.roles')}</th>
                  <th scope="col">{t('mgr.cat.email')}</th>
                  <th scope="col">{t('mgr.cat.active')}</th>
                </tr>
              </thead>
              <tbody>
                {(catalog.data ?? []).map((c) => {
                  const red = c.level >= 4
                  const off = !!busy
                  return (
                    <tr key={c.code}>
                      <th scope="row" className="mono">{c.code}</th>
                      <td><LevelChip level={c.level} /></td>
                      <td><b>{c.title}</b><br /><span className="sub">{c.action}</span></td>
                      <td>
                        <div className="mgr-checks">
                          {ROLES.map((role) => (
                            <label key={role} className="mgr-check">
                              <input
                                type="checkbox"
                                checked={c.notifyRoles.includes(role)}
                                disabled={off || (red && role === 'TECHNICAL_STAFF')}
                                onChange={(e) => toggleCatalog(c, { notifyRoles: e.target.checked ? [...c.notifyRoles, role] : c.notifyRoles.filter((x) => x !== role) })}
                              />
                              {t(`mgr.role.${role}`)}
                            </label>
                          ))}
                        </div>
                      </td>
                      <td>
                        <label className="mgr-check">
                          <input type="checkbox" checked={c.sendEmail} disabled={off || red} onChange={(e) => toggleCatalog(c, { sendEmail: e.target.checked })} />
                          <span className="staff-sr">{t('mgr.cat.email')} {c.code}</span>
                        </label>
                      </td>
                      <td>
                        <label className="mgr-check">
                          <input type="checkbox" checked={c.isActive} disabled={off || red} onChange={(e) => toggleCatalog(c, { isActive: e.target.checked })} />
                          <span className="staff-sr">{t('mgr.cat.active')} {c.code}</span>
                        </label>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <p className="sub">{t('mgr.cat.redRule')}</p>
        </details>
      </Panel>
    </Shell>
  )
}
