import { ClipboardText, PlayCircle, Timer } from '@phosphor-icons/react'
import { useState } from 'react'
import { Kpi } from '../../components/ws/parts'
import Shell from '../../components/ws/Shell'
import { useAsync } from '../../hooks/useAsync'
import { useLocale, useT } from '../../i18n'
import { Link } from '../../router/router'
import { ACTIVE_JOB_STATUSES, allTechJobs, jobPath, jobTone, type TechJob, type JobStatus } from '../../services/technician'
import { useUser } from '../../store/store'
import JobFeedback from './JobFeedback'
import './tech.css'

const GROUPS: { key: string; statuses: JobStatus[] }[] = [
  { key: 'qc', statuses: ['WRITTEN'] },
  { key: 'live', statuses: ['WRITING', 'PAUSED'] },
  { key: 'ready', statuses: ['SCHEDULED', 'PREPARING'] },
  { key: 'attention', statuses: ['FAILED', 'REWRITE_REQUIRED'] },
  { key: 'history', statuses: ['PHOTO_UPLOADED', 'DONE', 'CANCELLED'] },
]

export default function TechDashboard() {
  const t = useT()
  const locale = useLocale()
  const user = useUser()
  const [openedAt] = useState(() => new Date())
  const q = useAsync(allTechJobs, [user?.id], 30000)
  const mine = q.data ?? []
  const inStatus = (statuses: JobStatus[]) => mine.filter((j) => statuses.includes(j.status))
  const qc = inStatus(['WRITTEN']).length
  const live = inStatus(['WRITING', 'PAUSED']).length
  const ready = inStatus(['SCHEDULED', 'PREPARING']).length
  const open = inStatus(ACTIVE_JOB_STATUSES)
  const queued = inStatus(['SCHEDULED', 'PREPARING'])
  const queueMinutes = queued.reduce((total, job) => total + job.durationMin, 0)
  const maxMin = Math.max(1, ...queued.map((j) => j.durationMin))
  const robots = [...new Map(open.map((j) => [j.robotId, { id: j.robotId, code: j.robotCode }])).values()]
  const stamp = (s: string) => new Date(s).toLocaleString(locale, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Ho_Chi_Minh' })
  const today = openedAt.toLocaleDateString(locale, { weekday: 'long', day: 'numeric', month: 'long' })
  const count = (n: number) => q.data ? n : '...'

  return <Shell area="tech" active="dashboard" title={t('wk.hello', { name: user?.name ?? t('td.technician') })} lede={today}
    tools={<button type="button" className="sd-btn" onClick={() => void q.reload()}>{t('td.api.reload')}</button>}>
    <JobFeedback loading={q.loading && !q.data} error={q.error} retry={q.reload} />
    <div className="row3">
      <Kpi icon={<ClipboardText size={20} aria-hidden />} tone="a" title={t('td.kpi.qc')} value={count(qc)} note={t('td.kpi.qcHint')} to="/tech/qc" />
      <Kpi icon={<PlayCircle size={20} aria-hidden />} tone="p" title={t('td.api.live')} value={count(live)} note={t('td.api.liveHint')} to="/tech/preview" />
      <Kpi icon={<Timer size={20} aria-hidden />} tone="b" title={t('td.api.ready')} value={count(ready)} note={t('td.api.readyHint')} to="/tech/preview" />
    </div>
    <div className="flex">
      <section className="panel" style={{ flex: '2 1 560px' }} aria-labelledby="td-orders-h">
        <div className="ph"><h2 id="td-orders-h">{t('td.api.myJobs')}</h2>{q.data && <span className="sub">{t('td.assigned', { n: mine.length })}</span>}</div>
        {GROUPS.map((g) => {
          const rows = inStatus(g.statuses)
          return rows.length ? <div key={g.key} className="list">
            <div className="ph"><b>{t(`td.api.group.${g.key}`)}</b><span className="sub">{rows.length}</span></div>
            {rows.map((j) => <JobRow key={j.id} job={j} />)}
          </div> : null
        })}
        {q.data && !q.error && !mine.length && <div className="sd-empty"><b>{t('td.none')}</b><span>{t('td.api.noneBody')}</span></div>}
      </section>
      <section className="panel" style={{ flex: '1 1 340px' }} aria-labelledby="td-robots-h">
        <div className="ph"><h2 id="td-robots-h">{t('td.api.assignedRobots')}</h2></div>
        <div className="list">{robots.map((r) => <div key={r.id} className="item tech-job-row">
          <div className="t"><b>{r.code || r.id}</b>{open.filter((j) => j.robotId === r.id).map((j) => <Link key={j.id} to={jobPath(j.id)}>{j.orderCode || j.orderId} / {t(`js.${j.status}`)}</Link>)}</div>
        </div>)}</div>
        {q.data && !q.error && !robots.length && <p className="sub">{t('td.noRobots')}</p>}
        <p className="sub">{t('td.api.robotNote')}</p>
      </section>
    </div>
    <div className="flex">
      <section className="panel" style={{ flex: '1 1 440px' }} aria-labelledby="td-queue-h">
        <div className="ph"><h2 id="td-queue-h">{t('td.queueTitle')}</h2></div>
        <div className="list">{queued.map((j) => <Link key={j.id} to={jobPath(j.id)} className="item tech-job-row">
          <div className="t"><b>{j.orderCode || j.orderId}</b><span>{stamp(j.slotStart)}</span></div>
          <div className="tech-time-bar"><div className="bar"><i style={{ width: `${j.durationMin / maxMin * 100}%` }} /></div></div>
          <b className="mono">{t('td.min', { n: j.durationMin })}</b>
        </Link>)}</div>
        {q.data && !q.error && !queued.length && <p className="sub">{t('td.api.noQueued')}</p>}
        <p className="sub">{t('td.api.queueNote')}</p>
      </section>
      <section className="panel" style={{ flex: '1 1 440px' }} aria-labelledby="td-load-h">
        <div className="ph"><h2 id="td-load-h">{t('td.workload')}</h2></div>
        <div className="flex">
          <div className="k tech-workload"><div className="num"><b>{count(open.length)}</b></div><span className="sub">{t('td.api.activeJobs')}</span></div>
          <div className="k tech-workload"><div className="num"><b>{count(queueMinutes)}</b></div><span className="sub">{t('td.api.queuedMinutes')}</span></div>
        </div>
      </section>
    </div>
  </Shell>
}

function JobRow({ job: j }: { job: TechJob }) {
  const t = useT()
  return <Link to={jobPath(j.id)} className="item tech-job-row">
    <div className="t"><b>{j.orderCode || j.orderId}</b><span>{t('td.api.jobId', { id: j.id })}{j.isRewrite ? ` / ${t('wk.rewrite')}` : ''}</span></div>
    <span className={`chip ${jobTone(j.status)}`}>{t(`js.${j.status}`)}</span>
    <span className="mono sub">{j.robotCode || j.robotId} / {t('td.min', { n: j.durationMin })}</span>
  </Link>
}
