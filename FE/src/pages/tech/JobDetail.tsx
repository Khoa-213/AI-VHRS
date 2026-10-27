import { useEffect, useRef, useState } from 'react'
import Shell from '../../components/ws/Shell'
import { useAsync } from '../../hooks/useAsync'
import { useLocale, useT, useTn } from '../../i18n'
import { Link } from '../../router/router'
import { getTechJob, jobTone } from '../../services/technician'
import { useUser } from '../../store/store'
import JobFeedback from './JobFeedback'
import JobWorkflow from './JobWorkflow'
import './tech.css'

/** Backend-driven production workflow for the authenticated technician's assigned job. */
export default function JobDetail({ id }: { id: number }) {
  const t = useT()
  const tn = useTn()
  const locale = useLocale()
  const user = useUser()
  // While the robot writes, progress moves every few seconds; otherwise a slow refresh is enough.
  const q = useAsync(() => getTechJob(id), [id, user?.id], (j) => (j && ['WRITING', 'PAUSED'].includes(j.status) ? 5000 : 30000))
  const job = q.data
  const progressRef = useRef<HTMLElement>(null)
  const [pinned, setPinned] = useState(false)
  // A job that has not started writing has no progress yet: it reads as 0%.
  const hasJob = !!job
  // Once the progress panel has scrolled under the sticky header, the same bar is shown along the header's bottom.
  useEffect(() => {
    const el = progressRef.current
    if (!el || !hasJob) return
    const header = document.querySelector<HTMLElement>('.ws .hd')?.offsetHeight ?? 0
    const io = new IntersectionObserver(([e]) => setPinned(!e.isIntersecting && header + 1 > e.boundingClientRect.top), { rootMargin: `-${header}px 0px 0px 0px` })
    io.observe(el)
    return () => { io.disconnect(); setPinned(false) }
  }, [hasJob])
  const pct = Math.max(0, Math.min(100, job?.progress ?? 0))
  const stamp = (value: string | null) => value ? new Date(value).toLocaleString(locale, { timeZone: 'Asia/Ho_Chi_Minh' }) : t('td.api.unavailable')
  const outcome = (value: boolean | null) => t(value === null ? 'td.api.notRecorded' : value ? 'td.api.passed' : 'td.api.notPassed')
  return <Shell area="tech" active={job?.status === 'WRITTEN' ? 'qc' : 'preview'}
    title={job ? t('td.api.detailTitle', { code: job.orderCode || job.orderId }) : t('td.api.view')}
    lede={job ? t('td.api.jobId', { id: job.id }) : undefined}
    pinned={pinned && <div className="tech-pinned-progress" role="progressbar" aria-label={t('td.api.progress')} aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
      <div className="bar"><i style={{ width: `${pct}%` }} /></div><span className="mono">{pct}%</span></div>}
    tools={<div className="wk-actions"><Link to={job?.status === 'WRITTEN' ? '/tech/qc' : '/tech/preview'} className="sd-btn">{t('td.api.back')}</Link>
      <button type="button" className="sd-btn" onClick={() => void q.reload()}>{t('td.api.reload')}</button></div>}>
    <JobFeedback loading={q.loading && !job} error={q.error} retry={q.reload} />
    {job && <>
      <div className="wk-order-head"><div><h2>{job.orderCode || job.orderId}</h2><p className="sub">{t(`ot.${job.orderType}`)} / {t('po.pieces')}: {job.quantity}{job.isRewrite ? ` / ${t('wk.rewrite')}` : ''}</p></div>
        <span className={`chip ${jobTone(job.status)}`}>{t(`js.${job.status}`)}</span></div>
      <div className="flex">
        <section className="panel tech-detail-panel" aria-labelledby="tech-job-info">
          <div className="ph"><h2 id="tech-job-info">{t('td.api.assignment')}</h2></div>
          <dl className="wk-rows">
            <div><dt>{t('po.robot')}</dt><dd>{job.robotCode || job.robotId}</dd></div>
            <div><dt>{t('td.technician')}</dt><dd>{job.technicianName || user?.name}</dd></div>
            <div><dt>{t('td.api.slotStart')}</dt><dd>{stamp(job.slotStart)}</dd></div>
            <div><dt>{t('td.api.slotEnd')}</dt><dd>{stamp(job.slotEnd)}</dd></div>
            <div><dt>{t('po.time')}</dt><dd>{t('td.min', { n: job.durationMin })}</dd></div>
          </dl>
        </section>
        <section className="panel tech-detail-panel" aria-labelledby="tech-job-materials">
          <div className="ph"><h2 id="tech-job-materials">{t('td.api.materials')}</h2></div>
          <dl className="wk-rows">
            <div><dt>{t('po.paper')}</dt><dd>{job.paper ? tn(job.paper) : t('td.api.unavailable')}</dd></div>
            <div><dt>{t('po.pen')}</dt><dd>{job.pen ? tn(job.pen) : t('td.api.unavailable')}</dd></div>
            <div><dt>{t('po.ink')}</dt><dd>{job.ink ? tn(job.ink) : t('td.api.unavailable')}</dd></div>
            <div><dt>{t('po.pieces')}</dt><dd>{job.quantity}</dd></div>
          </dl>
          {job.note && <p className="wk-text">{job.note}</p>}
        </section>
      </div>
      <section ref={progressRef} className="panel" aria-labelledby="tech-job-progress">
        <div className="ph"><h2 id="tech-job-progress">{t('td.api.progress')}</h2></div>
        <div role="progressbar" aria-label={t('td.api.progress')} aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
          <div className="bar"><i style={{ width: `${pct}%` }} /></div><span className="sub">{pct}%</span>
        </div>
        <dl className="wk-rows">
          <div><dt>{t('td.api.downloaded')}</dt><dd>{stamp(job.downloadedAt)}</dd></div>
          <div><dt>{t('td.api.calibration')}</dt><dd>{outcome(job.calibration?.is_valid ?? null)}</dd></div>
          <div><dt>{t('td.api.simulation')}</dt><dd>{outcome(job.simulationPassed)}</dd></div>
          <div><dt>{t('td.api.started')}</dt><dd>{stamp(job.startedAt)}</dd></div>
          <div><dt>{t('td.api.finished')}</dt><dd>{stamp(job.finishedAt)}</dd></div>
        </dl>
      </section>
      <JobWorkflow key={job.id} job={job} refresh={q.reload} stale={!!q.error || q.loading} />
    </>}
  </Shell>
}
