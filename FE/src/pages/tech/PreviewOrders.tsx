import { useAsync } from '../../hooks/useAsync'
import { useLocale, useT } from '../../i18n'
import Shell from '../../components/ws/Shell'
import { Link } from '../../router/router'
import { errText, orderErrorKey } from '../../services/orders'
import { listMyJobs, type JobStatus, type TechJob } from '../../services/technician'
import '../staff/dashboard.css'
import '../staff/polish.css'
import './tech.css'
import { jobTone } from './jobs'

type Mode = 'preview' | 'qc'

/** Which jobs each tab lists. Photo and QC opens once the job is WRITTEN; every earlier step happens on the run page. */
const STATUSES: Record<Mode, JobStatus[]> = {
  preview: ['SCHEDULED', 'PREPARING', 'WRITING', 'PAUSED'],
  qc: ['WRITTEN'],
}

/** First step of the Preview and QC tabs: pick which of your jobs to open. */
export default function PreviewOrders({ mode = 'preview' }: { mode?: Mode }) {
  const t = useT()
  const locale = useLocale()
  const jobs = useAsync(async () => (await listMyJobs({ status: STATUSES[mode] })).items, [mode], 30000)
  const open = [...(jobs.data ?? [])].sort((a, b) => a.slotStart.localeCompare(b.slotStart))
  const when = (iso: string) => new Date(iso).toLocaleString(locale, { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
  const to = (j: TechJob) => `/tech/${mode === 'qc' ? 'qc' : 'preview'}/${j.id}`

  return (
    <Shell area="tech" active={mode} title={t(mode === 'qc' ? 'po.titleQc' : 'po.title')} lede={t(mode === 'qc' ? 'po.bodyQc' : 'po.body')}>
      {jobs.error ? <p className="lg-error" role="alert">{errText(t, orderErrorKey(jobs.error))}</p> : null}
      {jobs.loading && !jobs.data ? <p className="sd-sub" role="status">{t('co.loading')}</p> : null}
      {open.length ? (
        <ul className="po-grid" aria-label={t('po.aria')}>
          {open.map((j, i) => (
            <li key={j.id}>
              <Link to={to(j)} className={`po-card${j.status === 'WRITING' ? ' po-card--live' : ''}`}>
                <span className="po-top">
                  <span className="vh-mono po-id">{j.orderCode}</span>
                  <span className="vh-chip" style={{ color: jobTone(j.status) }}>{t(`js.${j.status}`)}</span>
                </span>
                <dl className="po-facts">
                  <div><dt>{t('po.robot')}</dt><dd>{j.robotCode}</dd></div>
                  <div><dt>{t('po.time')}</dt><dd>{t('po.timeVal', { n: j.durationMin })}</dd></div>
                  <div><dt>{t('po.slot')}</dt><dd>{when(j.slotStart)}</dd></div>
                  {j.progressPct !== null && j.status !== 'WRITTEN' ? <div><dt>{t('rp.tele.progress')}</dt><dd>{Math.round(j.progressPct)}%</dd></div> : null}
                </dl>
                {j.isRewrite ? <span className="sd-sub">{t('po.rewrite')}</span> : null}
                <span className="vh-btn vh-btn--md vh-btn--primary po-cta">
                  {i === 0 ? t('po.nextUp', { cta: t(mode === 'qc' ? 'po.qc.cta' : 'po.job.cta') }) : t(mode === 'qc' ? 'po.qc.cta' : 'po.job.cta')}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      ) : jobs.data ? (
        <section className="sd-card" aria-labelledby="po-empty-h">
          <div className="sd-empty">
            <b id="po-empty-h">{t(mode === 'qc' ? 'po.emptyQc' : 'po.empty')}</b>
            <span>{mode === 'qc' ? t('po.emptyQcBody') : t('po.emptyBody', { link: t('po.dashboard') })}</span>
          </div>
        </section>
      ) : null}
    </Shell>
  )
}
