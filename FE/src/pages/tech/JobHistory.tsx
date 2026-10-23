import { useState } from 'react'
import { useAsync } from '../../hooks/useAsync'
import { useLocale, useT } from '../../i18n'
import { jobEvents, type TechJobDetail } from '../../services/technician'
import JobFeedback from './JobFeedback'

export default function JobHistory({ job, revision }: { job: TechJobDetail; revision: number }) {
  const t = useT()
  const locale = useLocale()
  const [page, setPage] = useState(1)
  const q = useAsync(() => jobEvents(job.id, page), [job.id, page, revision], 30000)
  return <>
    <section className="panel">
      <div className="ph"><h2>{t('td.flow.history')}</h2><button type="button" className="sd-btn" onClick={() => void q.reload()}>{t('td.api.reload')}</button></div>
      <JobFeedback loading={q.loading} error={q.error} retry={q.reload} />
      {!q.loading && <ol className="tech-event-list">{q.data?.items.map((event) => <li key={event.id}>
        <div className="ph"><b>{t(`td.flow.event.${event.event_type}`)}</b><time dateTime={event.occurred_at}>{new Date(event.occurred_at).toLocaleString(locale, { timeZone: 'Asia/Ho_Chi_Minh' })}</time></div>
        {event.stroke_index !== null && <p className="sub">{t('td.flow.strokeIndex')}: {event.stroke_index}</p>}
        {(event.payload || event.force_summary) && <details><summary>{t('td.flow.eventData')}</summary><pre className="tech-json">{JSON.stringify({ payload: event.payload, force_summary: event.force_summary }, null, 2)}</pre></details>}
      </li>)}</ol>}
      {q.data && !q.loading && !q.error && !q.data.items.length && <p className="sub">{t('td.flow.noEvents')}</p>}
      <div className="wk-actions">
        <button type="button" className="sd-btn" disabled={page <= 1 || q.loading} onClick={() => setPage(page - 1)}>{t('td.flow.previous')}</button><span>{page}</span>
        <button type="button" className="sd-btn" disabled={q.loading || !q.data || page * q.data.page_size >= q.data.total} onClick={() => setPage(page + 1)}>{t('td.flow.next')}</button>
      </div>
    </section>
    {!!job.incidents.length && <section className="panel"><h2>{t('td.flow.incidents')}</h2><ul className="tech-event-list">{job.incidents.map((incident) => <li key={incident.id}>
      <b>{t(`td.flow.incident.${incident.type}`)}</b><p className="wk-text">{incident.description}</p>
      <span className="sub">{new Date(incident.created_at).toLocaleString(locale, { timeZone: 'Asia/Ho_Chi_Minh' })} / {t(incident.resolved_at ? 'td.flow.resolved' : 'td.flow.unresolved')}</span>
    </li>)}</ul></section>}
  </>
}
