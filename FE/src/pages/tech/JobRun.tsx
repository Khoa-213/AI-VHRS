import { useState } from 'react'
import Shell from '../../components/ws/Shell'
import { ApiError } from '../../services/api'
import { useAsync } from '../../hooks/useAsync'
import { useLocale, useT } from '../../i18n'
import { Link } from '../../router/router'
import { errText, orderErrorKey } from '../../services/orders'
import type { Job, Run } from '../../services/async'
import {
  INCIDENT_TYPES, fetchVerifiedTrajectory, finishJob, getMyJob, getPackage, prepareJob, reportEvent, reportIncident,
  saveCalibration, saveSimulation, startJob,
  type IncidentType, type JobPackage, type ReportedEvent, type TechJobDetail,
} from '../../services/technician'
import '../staff/dashboard.css'
import '../staff/staff.css'
import '../staff/polish.css'
import './tech.css'

const PROBLEMS: ReportedEvent[] = ['ESTOP', 'OVER_FORCE', 'STROKE_LOST', 'SENSOR_LOST']
const CHECKS = ['frame_mounted', 'paper_clamped', 'pen_installed', 'force_zeroed'] as const
const num = (v: string) => (v.trim() === '' ? NaN : Number(v))

/**
 * One job from "scheduled" to "written": download and verify the package, prepare, calibrate, record the simulation,
 * start, report progress and finish. The backend guards the order of the steps; this page shows the one that is next.
 */
export default function JobRun({ id }: { id: number }) {
  const t = useT()
  const locale = useLocale()
  const q = useAsync(() => getMyJob(id), [id], 20000)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [pkg, setPkg] = useState<{ data: JobPackage; ok: boolean; hash: string } | null>(null)
  const job = q.data

  const run = async (work: Job) => {
    if (busy) return
    setBusy(true)
    setErr('')
    try {
      await work()
      await q.reload()
    } catch (e) {
      setErr(orderErrorKey(e))
    } finally {
      setBusy(false)
    }
  }

  const shell = (body: React.ReactNode, title = t('jr.titleShort'), lede?: string) => (
    <Shell area="tech" active="preview" title={title} lede={lede} tools={<Link to="/tech/preview" className="sd-btn">{t('rp.another')}</Link>}>
      {body}
    </Shell>
  )

  if (!job) {
    const missing = q.error instanceof ApiError && q.error.status === 404
    return shell(
      q.loading
        ? <p className="sd-sub" role="status">{t('co.loading')}</p>
        : <section className="sd-card"><div className="sd-empty"><b>{t('jr.notFound')}</b><span>{missing ? t('jr.notFoundBody') : errText(t, orderErrorKey(q.error))}</span></div></section>,
    )
  }

  const when = (iso: string) => new Date(iso).toLocaleString(locale, { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
  const s = job.status
  const active = s === 'PREPARING' || s === 'WRITING' || s === 'PAUSED'

  return shell(
    <div className="tp-grid">
      <div className="tp-main qc-main">
        {err && <p className="lg-error" role="alert">{errText(t, err)}</p>}

        {s === 'SCHEDULED' && <PackageStep job={job} pkg={pkg} busy={busy} run={run} onPkg={setPkg} />}
        {s === 'PREPARING' && (
          <>
            <CalibrationStep job={job} busy={busy} run={run} when={when} />
            <SimulationStep job={job} busy={busy} run={run} />
            <section className="wk-block" aria-label={t('jr.start')}>
              <h3>{t('jr.start')}</h3>
              <p className="sd-sub">{t(job.canStart ? 'jr.startBody' : 'jr.startNeed', { robot: job.robotCode, n: job.durationMin })}</p>
              <div className="wk-actions">
                <button className="vh-btn vh-btn--primary vh-btn--md" disabled={busy || !job.canStart} onClick={() => void run(() => startJob(job.id))}>{t('jr.start')}</button>
              </div>
            </section>
          </>
        )}
        {(s === 'WRITING' || s === 'PAUSED') && <WritingStep job={job} busy={busy} run={run} />}
        {s === 'WRITTEN' && (
          <section className="wk-block" aria-label={t('jr.written')}>
            <h3>{t('jr.written')}</h3>
            <p className="sd-sub">{t('jr.writtenBody')}</p>
            <div className="wk-actions"><Link to={`/tech/qc/${job.id}`} className="vh-btn vh-btn--primary vh-btn--md">{t('rp.goQc')}</Link></div>
          </section>
        )}
        {!active && s !== 'SCHEDULED' && s !== 'WRITTEN' && (
          <section className="sd-card"><div className="sd-empty"><b>{t(`js.${s}`)}</b><span>{t('jr.closed', { status: t(`js.${s}`) })}</span></div></section>
        )}

        {active && <IncidentStep job={job} busy={busy} run={run} />}
        {job.incidents.length > 0 && (
          <section className="wk-block" aria-label={t('jr.incidents')}>
            <h3>{t('jr.incidents')}</h3>
            <ul className="wk-jobs">
              {job.incidents.map((i) => <li key={i.id}><span><b>{t(`jr.it.${i.type}`)}</b> · {i.description}</span><span className="sd-sub">{when(i.createdAt)}</span></li>)}
            </ul>
          </section>
        )}
      </div>

      <aside className="tp-side" aria-label={t('jr.details')}>
        <section>
          <h2 className="tp-h">{t('jr.details')}</h2>
          <dl className="tp-opts">
            <div><dt>{t('po.robot')}</dt><dd>{job.robotCode}</dd></div>
            <div><dt>{t('po.slot')}</dt><dd>{when(job.slotStart)}</dd></div>
            <div><dt>{t('po.time')}</dt><dd>{t('po.timeVal', { n: job.durationMin })}</dd></div>
            <div><dt>{t('po.pieces')}</dt><dd>{job.quantity}</dd></div>
            {job.paperName && <div><dt>{t('po.paper')}</dt><dd>{job.paperName}</dd></div>}
            {job.penName && <div><dt>{t('po.pen')}</dt><dd>{job.penName}</dd></div>}
            {job.inkName && <div><dt>{t('po.ink')}</dt><dd>{job.inkName}</dd></div>}
            {job.progressPct !== null && <div><dt>{t('rp.tele.progress')}</dt><dd>{Math.round(job.progressPct)}%</dd></div>}
          </dl>
          {job.approachNote && <p className="sd-sub">{t('jr.approach')}: {job.approachNote}</p>}
          {job.isRewrite && <p className="sd-sub">{t('po.rewrite')}</p>}
        </section>
      </aside>
    </div>,
    t('jr.title', { code: job.orderCode }),
    `${t(`js.${s}`)} · ${job.robotCode}`,
  )
}

interface StepProps { job: TechJobDetail; busy: boolean; run: Run }

function PackageStep({ job, pkg, busy, run, onPkg }: StepProps & { pkg: { data: JobPackage; ok: boolean; hash: string } | null; onPkg: (p: { data: JobPackage; ok: boolean; hash: string }) => void }) {
  const t = useT()
  const download = () => run(async () => {
    const data = await getPackage(job.id)
    const { ok, hash } = await fetchVerifiedTrajectory(data)
    onPkg({ data, ok, hash })
  })
  const short = (h: string) => `${h.slice(0, 10)}…`
  const ready = !!job.downloadedAt && pkg?.ok !== false
  return (
    <section className="wk-block" aria-label={t('jr.pkg')}>
      <h3>{t('jr.pkg')}</h3>
      <p className="sd-sub">{t('jr.pkgBody')}</p>
      <div className="wk-actions">
        <button className="vh-btn vh-btn--ghost vh-btn--md" disabled={busy} onClick={() => void download()}>{t(busy ? 'jr.downloading' : 'jr.download')}</button>
      </div>
      {pkg && (
        <>
          <p className={pkg.ok ? 'sd-sub' : 'wk-warn'} role={pkg.ok ? 'status' : 'alert'}>{t(pkg.ok ? 'jr.hashOk' : 'jr.hashBad', { hash: short(pkg.hash) })}</p>
          <dl className="wk-rows">
            <div><dt>{t('jr.pages')}</dt><dd>{pkg.data.pages}</dd></div>
            {pkg.data.paper && <div><dt>{t('po.paper')}</dt><dd>{pkg.data.paper.name} · {pkg.data.paper.size}</dd></div>}
            {pkg.data.pen && <div><dt>{t('po.pen')}</dt><dd>{pkg.data.pen.name}</dd></div>}
            {pkg.data.pen && <div><dt>{t('jr.force')}</dt><dd>{t('jr.forceVal', { target: pkg.data.pen.fTargetN, min: pkg.data.pen.fMinN, max: pkg.data.pen.fMaxN })}</dd></div>}
            {pkg.data.pen && <div><dt>{t('jr.speed')}</dt><dd>{t('jr.speedVal', { n: pkg.data.pen.vMaxMmS })}</dd></div>}
          </dl>
          {pkg.data.previewUrl && <div className="wk-previews"><img src={pkg.data.previewUrl} alt={t('opv.sketch', { n: 1 })} /></div>}
        </>
      )}
      <div className="wk-actions">
        <button className="vh-btn vh-btn--primary vh-btn--md" disabled={busy || !ready} onClick={() => void run(() => prepareJob(job.id))}>{t('jr.prepare')}</button>
        {!job.downloadedAt && <span className="sd-sub">{t('jr.prepareNeed')}</span>}
      </div>
    </section>
  )
}

function CalibrationStep({ job, busy, run, when }: StepProps & { when: (iso: string) => string }) {
  const t = useT()
  const [checks, setChecks] = useState<Record<(typeof CHECKS)[number], boolean>>({ frame_mounted: false, paper_clamped: false, pen_installed: false, force_zeroed: false })
  const [offset, setOffset] = useState('')
  const [pts, setPts] = useState<[string, string, string][]>([['', '', ''], ['', '', ''], ['', '', '']])
  const nums = pts.map((p) => p.map(num))
  const complete = Object.values(checks).every(Boolean) && Number.isFinite(num(offset)) && nums.every((p) => p.every(Number.isFinite))
  const setPt = (i: number, k: number, v: string) => setPts((ps) => ps.map((p, j) => (j === i ? (p.map((x, m) => (m === k ? v : x)) as [string, string, string]) : p)))
  const cal = job.calibration
  return (
    <section className="wk-block" aria-label={t('jr.cal')}>
      <h3>{t('jr.cal')}</h3>
      <p className="sd-sub">{cal?.isValid ? t('jr.calValid', { when: when(cal.createdAt) }) : t('jr.calBody')}</p>
      <div className="qc-items">
        {CHECKS.map((c) => (
          <label key={c} className={`qc-item${checks[c] ? ' on' : ''}`}>
            <input type="checkbox" checked={checks[c]} onChange={(e) => setChecks((x) => ({ ...x, [c]: e.target.checked }))} />
            <span className="qc-box" aria-hidden="true">{checks[c] ? '✓' : ''}</span>
            <span className="qc-text"><b>{t(`jr.cal.${c}`)}</b></span>
          </label>
        ))}
      </div>
      <div className="wk-form">
        <label className="vh-label">
          {t('jr.zeroOffset')}
          <input className="vh-input" inputMode="decimal" value={offset} onChange={(e) => setOffset(e.target.value)} />
        </label>
      </div>
      <b className="sd-sub">{t('jr.probes')}</b>
      {pts.map((p, i) => (
        <div key={i} className="wk-form">
          <span className="vh-mono">{t('jr.probeN', { n: i + 1 })}</span>
          {(['x', 'y', 'z'] as const).map((axis, k) => (
            <input key={axis} className="vh-input" style={{ width: 96 }} inputMode="decimal" aria-label={t('jr.axis', { n: i + 1, axis })} value={p[k]} onChange={(e) => setPt(i, k, e.target.value)} />
          ))}
        </div>
      ))}
      <div className="wk-actions">
        <button className="vh-btn vh-btn--ghost vh-btn--sm" disabled={busy} onClick={() => setPts((ps) => [...ps, ['', '', '']])}>{t('jr.addProbe')}</button>
        <button
          className="vh-btn vh-btn--primary vh-btn--md"
          disabled={busy || !complete}
          onClick={() => void run(() => saveCalibration(job.id, {
            checklist: { frame_mounted: true, paper_clamped: true, pen_installed: true, force_zeroed: true },
            force_zero_offset: num(offset),
            probe_points: nums.map(([x, y, z]) => ({ x, y, z })),
          }))}
        >
          {t('jr.saveCal')}
        </button>
      </div>
      {cal?.isValid && <p className="sd-sub">{t('jr.calRedo')}</p>}
    </section>
  )
}

function SimulationStep({ job, busy, run }: StepProps) {
  const t = useT()
  const [errors, setErrors] = useState('')
  const calibrated = !!job.calibration?.isValid
  return (
    <section className="wk-block" aria-label={t('jr.sim')}>
      <h3>{t('jr.sim')}</h3>
      <p className="sd-sub">
        {!calibrated ? t('jr.simNeedCal') : job.simulationPassed === true ? t('jr.simPassed') : job.simulationPassed === false ? t('jr.simFailed') : t('jr.simBody')}
      </p>
      {calibrated && (
        <>
          <label className="vh-label">
            {t('jr.simErrors')}
            <textarea className="vh-textarea" rows={2} value={errors} onChange={(e) => setErrors(e.target.value)} />
          </label>
          <div className="wk-actions">
            <button className="vh-btn vh-btn--primary vh-btn--md" disabled={busy || !!errors.trim()} onClick={() => void run(() => saveSimulation(job.id, { passed: true }))}>{t('jr.simPass')}</button>
            <button
              className="vh-btn vh-btn--ghost vh-btn--md"
              disabled={busy || !errors.trim()}
              onClick={() => void run(() => saveSimulation(job.id, { passed: false, errors: errors.split('\n').map((l) => l.trim()).filter(Boolean) }))}
            >
              {t('jr.simFail')}
            </button>
          </div>
        </>
      )}
    </section>
  )
}

function WritingStep({ job, busy, run }: StepProps) {
  const t = useT()
  const current = Math.round(job.progressPct ?? 0)
  const [pct, setPct] = useState(String(current))
  const [problem, setProblem] = useState<ReportedEvent>('ESTOP')
  const paused = job.status === 'PAUSED'
  const value = num(pct)
  const valid = Number.isFinite(value) && current <= value && value <= 100
  return (
    <section className="wk-block" aria-label={t('jr.run')}>
      <h3>{t(paused ? 'js.PAUSED' : 'jr.run')}</h3>
      <div className="qc-progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={current} aria-label={t('rp.tele.progress')}>
        <p>{t('rp.tele.progress')}: <b>{current}%</b></p>
        <div className="bar"><i style={{ width: `${current}%` }} /></div>
      </div>
      <div className="wk-form">
        <label className="vh-label">
          {t('rp.tele.progress')} (%)
          <input className="vh-input" inputMode="numeric" value={pct} onChange={(e) => setPct(e.target.value)} />
        </label>
        <button
          className="vh-btn vh-btn--ghost vh-btn--md"
          disabled={busy || paused || !valid}
          onClick={() => void run(() => reportEvent(job.id, { event_type: 'PROGRESS', progress_pct: value }))}
        >
          {t('jr.reportProgress')}
        </button>
        {paused
          ? <button className="vh-btn vh-btn--primary vh-btn--md" disabled={busy} onClick={() => void run(() => reportEvent(job.id, { event_type: 'RESUME' }))}>{t('jr.resume')}</button>
          : <button className="vh-btn vh-btn--ghost vh-btn--md" disabled={busy} onClick={() => void run(() => reportEvent(job.id, { event_type: 'PAUSE' }))}>{t('rp.pause')}</button>}
      </div>
      {!paused && (
        <div className="wk-form">
          <label className="vh-label">
            {t('jr.problem')}
            <select className="vh-select" value={problem} onChange={(e) => setProblem(e.target.value as ReportedEvent)}>
              {PROBLEMS.map((p) => <option key={p} value={p}>{t(`jr.problem.${p}`)}</option>)}
            </select>
          </label>
          <button className="vh-btn vh-btn--ghost vh-btn--md" disabled={busy} onClick={() => void run(() => reportEvent(job.id, { event_type: problem }))}>{t('jr.report')}</button>
        </div>
      )}
      <div className="wk-actions">
        <button className="vh-btn vh-btn--primary vh-btn--md" disabled={busy || paused} onClick={() => void run(() => finishJob(job.id))}>{t('jr.finish')}</button>
        <span className="sd-sub">{t('jr.finishBody')}</span>
      </div>
    </section>
  )
}

function IncidentStep({ job, busy, run }: StepProps) {
  const t = useT()
  const [type, setType] = useState<IncidentType>('ROBOT')
  const [text, setText] = useState('')
  const [after, setAfter] = useState<'' | 'MAINTENANCE' | 'BROKEN'>('')
  return (
    <details className="wk-lines">
      <summary>{t('jr.incident')}</summary>
      <section className="wk-block" aria-label={t('jr.incident')}>
        <p className="sd-sub">{t('jr.incidentBody')}</p>
        <div className="wk-form">
          <label className="vh-label">
            {t('jr.incidentType')}
            <select className="vh-select" value={type} onChange={(e) => setType(e.target.value as IncidentType)}>
              {INCIDENT_TYPES.map((i) => <option key={i} value={i}>{t(`jr.it.${i}`)}</option>)}
            </select>
          </label>
          <label className="vh-label">
            {t('jr.robotAfter')}
            <select className="vh-select" value={after} onChange={(e) => setAfter(e.target.value as typeof after)}>
              <option value="">{t('jr.robotAfter.none')}</option>
              <option value="MAINTENANCE">{t('jr.robotAfter.MAINTENANCE')}</option>
              <option value="BROKEN">{t('jr.robotAfter.BROKEN')}</option>
            </select>
          </label>
        </div>
        <label className="vh-label">
          {t('jr.incidentDesc')}
          <textarea className="vh-textarea" rows={3} value={text} onChange={(e) => setText(e.target.value)} />
        </label>
        <div className="wk-actions">
          <button
            className="vh-btn vh-btn--md qc-danger"
            disabled={busy || text.trim().length < 3}
            onClick={() => void run(() => reportIncident(job.id, { type, description: text.trim(), ...(after ? { robot_status_after: after } : {}) }))}
          >
            {t('jr.sendIncident')}
          </button>
        </div>
      </section>
    </details>
  )
}
