import { useT, useLocale } from '../../i18n'
import Shell from '../../components/ws/Shell'
import { useAsync } from '../../hooks/useAsync'
import { Link } from '../../router/router'
import { allTechJobs, jobPath, PREVIEW_JOB_STATUSES } from '../../services/technician'
import { useUser } from '../../store/store'
import JobFeedback from './JobFeedback'
import '../staff/dashboard.css'
import '../staff/polish.css'
import './tech.css'

type Mode = 'preview' | 'qc'

export default function PreviewOrders({ mode = 'preview' }: { mode?: Mode }) {
  const t = useT()
  const locale = useLocale()
  const user = useUser()
  const q = useAsync(allTechJobs, [user?.id], 30000)
  const jobs = (q.data ?? []).filter((j) => mode === 'qc' ? j.status === 'WRITTEN' : PREVIEW_JOB_STATUSES.includes(j.status))
  return <Shell area="tech" active={mode} title={t(mode === 'qc' ? 'td.api.qcTitle' : 'td.api.listTitle')}
    lede={t(mode === 'qc' ? 'td.api.qcBody' : 'td.api.listBody')}
    tools={<button type="button" className="sd-btn" onClick={() => void q.reload()}>{t('td.api.reload')}</button>}>
    <JobFeedback loading={q.loading && !q.data} error={q.error} retry={q.reload} />
    {jobs.length > 0 && <ul className="po-grid" aria-label={t('td.api.myJobs')}>
      {jobs.map((j) => {
        const phase = j.status === 'WRITTEN' ? 'qc' : ['WRITING', 'PAUSED'].includes(j.status) ? 'live' : 'ready'
        return <li key={j.id}><Link to={jobPath(j.id)} className={`po-card po-card--${phase}`}>
          <span className="po-top"><span className="vh-mono po-id">{j.orderCode || j.orderId}</span><span className="vh-chip">{t(`js.${j.status}`)}</span></span>
          <span className="po-title">{t('td.api.jobId', { id: j.id })}</span>
          {j.isRewrite && <span className="sd-sub">{t('wk.rewrite')}</span>}
          <dl className="po-facts">
            <div><dt>{t('po.robot')}</dt><dd>{j.robotCode || j.robotId}</dd></div>
            <div><dt>{t('po.time')}</dt><dd>{t('td.min', { n: j.durationMin })}</dd></div>
            <div><dt>{t('td.api.slotStart')}</dt><dd>{new Date(j.slotStart).toLocaleString(locale, { timeZone: 'Asia/Ho_Chi_Minh' })}</dd></div>
            <div><dt>{t('td.api.slotEnd')}</dt><dd>{new Date(j.slotEnd).toLocaleString(locale, { timeZone: 'Asia/Ho_Chi_Minh' })}</dd></div>
            {j.progress !== null && <div><dt>{t('td.api.progress')}</dt><dd>{j.progress}%</dd></div>}
          </dl>
          <span className="vh-btn vh-btn--md vh-btn--primary po-cta">{t('td.api.view')}</span>
        </Link></li>
      })}
    </ul>}
    {q.data && !q.error && !jobs.length && <section className="panel"><div className="sd-empty"><b>{t(mode === 'qc' ? 'po.emptyQc' : 'po.empty')}</b><span>{t(mode === 'qc' ? 'td.api.emptyQc' : 'td.api.emptyPreview')}</span></div></section>}
  </Shell>
}
