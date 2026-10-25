import { useRef, useState } from 'react'
import { useT } from '../../i18n'
import type { Job } from '../../services/async'
import { downloadJobPackage, finishJob, jobPermissions, prepareJob, startJob, type TechJobDetail, type VerifiedPackage } from '../../services/technician'
import { flowError, type TechRun } from './flow'
import JobPreparation from './JobPreparation'
import JobEvents from './JobEvents'
import JobPhotos from './JobPhotos'
import JobHistory from './JobHistory'

export default function JobWorkflow({ job, refresh, stale }: { job: TechJobDetail; refresh: Job; stale: boolean }) {
  const t = useT()
  const lock = useRef(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [verified, setVerified] = useState<VerifiedPackage | null>(null)
  const [revision, setRevision] = useState(0)
  const [page, setPage] = useState(0)
  const gates = jobPermissions(job, verified?.hash)
  const disabled = busy || stale
  const run: TechRun = async (action, confirmation) => {
    if (lock.current || stale) return false
    if (confirmation && !window.confirm(confirmation)) return false
    lock.current = true
    setBusy(true); setError(''); setNotice('')
    let ok = false
    try {
      await action()
      ok = true
      setNotice(t('td.flow.saved'))
    } catch (e) {
      if (e instanceof Error && (e.message === 'td.flow.hashMismatch' || ('code' in e && e.code === 'JOB_HASH_MISMATCH'))) setVerified(null)
      setError(flowError(e, t))
    } finally {
      // Also refetch on a failed/racing request; a network failure may occur after the server committed it.
      await refresh()
      setRevision((n) => n + 1)
      lock.current = false
      setBusy(false)
    }
    return ok
  }
  const download = () => run(async () => {
    setVerified(null)
    const pack = await downloadJobPackage(job.id)
    setVerified(pack); setPage(0)
  })
  const saveFile = () => {
    if (!verified) return
    const url = URL.createObjectURL(new Blob([verified.bytes], { type: 'application/json' }))
    const a = document.createElement('a'); a.href = url; a.download = `job-${job.id}-trajectory.json`; a.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  const current = verified?.hash === job.packageHash ? verified : null
  return <div className="tech-workflow" aria-busy={busy}>
    <p className="wk-warn">{t('td.flow.scope')}</p>
    {error && <p className="lg-error tech-error" role="alert">{error}</p>}
    {notice && <p className="sub" role="status">{notice}</p>}
    {busy && <p role="status" className="sub">{t('td.flow.working')}</p>}
    {gates.download && <section className="panel">
      <div className="ph"><h2>{t('td.flow.package')}</h2><span className={`chip ${current ? 'good' : 'warn'}`}>{t(current ? 'td.flow.verified' : 'td.flow.verifyRequired')}</span></div>
      <p className="sub">{t('td.flow.packageHelp')}</p>
      <div className="wk-actions">
        <button type="button" className="sd-btn" disabled={disabled} onClick={() => void download()}>{t('td.flow.download')}</button>
        {current && <button type="button" className="sd-btn" disabled={disabled} onClick={saveFile}>{t('td.flow.saveFile')}</button>}
      </div>
      {current && <>
        <code className="tech-hash">{current.hash}</code>
        {current.info.pen && <dl className="wk-rows">
          <div><dt>{t('td.flow.forceBand')}</dt><dd>{current.info.pen.f_min_n} / {current.info.pen.f_target_n} / {current.info.pen.f_max_n} N</dd></div>
          <div><dt>{t('td.flow.forceHard')}</dt><dd>{current.info.pen.f_hard_n} N</dd></div>
          <div><dt>{t('td.flow.speed')}</dt><dd>{current.info.pen.v_max_mm_s} mm/s</dd></div>
        </dl>}
        <label className="vh-label">{t('td.flow.page')}<select className="vh-select" value={page} onChange={(e) => setPage(Number(e.target.value))}>{current.pages.map((_, i) => <option key={i} value={i}>{i + 1}</option>)}</select></label>
        <div className="tech-trajectory">
          <svg viewBox={`0 0 ${current.pages[page].paper.width_mm} ${current.pages[page].paper.height_mm}`} role="img" aria-label={t('td.flow.trajectory')}>
            {current.pages[page].strokes.map((s, i) => <path key={i} d={s.points.map((p, j) => `${j ? 'L' : 'M'}${p[0]} ${p[1]}`).join(' ')} />)}
          </svg>
        </div>
        <p className="sub">{t('td.flow.previewOnly')}</p>
      </>}
    </section>}
    {job.status === 'SCHEDULED' && <section className="panel"><h2>{t('td.flow.prepare')}</h2><p className="sub">{t('td.flow.prepareHelp')}</p>
      <button type="button" className="sd-btn" disabled={disabled || !gates.prepare} onClick={() => void run(() => prepareJob(job.id))}>{t('td.flow.prepare')}</button>
    </section>}
    {job.status === 'PREPARING' && <JobPreparation job={job} disabled={disabled} gates={gates} run={run} />}
    {job.status === 'PREPARING' && <section className="panel"><h2>{t('td.flow.start')}</h2>
      <ul className="tech-gates">
        {[['td.flow.verified', !!current], ['td.api.calibration', !!job.calibration?.is_valid], ['td.api.simulation', job.simulationPassed === true]].map(([key, ok]) => <li key={String(key)}><span className={`chip ${ok ? 'good' : 'warn'}`}>{t(ok ? 'td.api.passed' : 'td.api.notRecorded')}</span>{t(String(key))}</li>)}
      </ul>
      <button type="button" className="sd-btn" disabled={disabled || !gates.start} onClick={() => void run(() => startJob(job.id), t('td.flow.confirmStart'))}>{t('td.flow.start')}</button>
    </section>}
    <JobEvents job={job} disabled={disabled} run={run} />
    {gates.finish && <section className="panel"><h2>{t('td.flow.finish')}</h2><p className="sub">{t('td.flow.finishHelp')}</p>
      <button type="button" className="sd-btn" disabled={disabled} onClick={() => void run(() => finishJob(job.id), t('td.flow.confirmFinish'))}>{t('td.flow.finish')}</button>
    </section>}
    {['WRITTEN', 'PHOTO_UPLOADED', 'DONE', 'REWRITE_REQUIRED'].includes(job.status) && <JobPhotos job={job} disabled={disabled} run={run} revision={revision} />}
    <JobHistory job={job} revision={revision} />
  </div>
}
