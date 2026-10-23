import { ClipboardText, PlayCircle, Timer } from '@phosphor-icons/react'
import { useState } from 'react'
import { Kpi } from '../../components/ws/parts'
import Shell from '../../components/ws/Shell'
import { useAsync } from '../../hooks/useAsync'
import { useLocale, useT } from '../../i18n'
import { Link } from '../../router/router'

import { errText, orderErrorKey } from '../../services/orders'
import { OPEN_STATUSES, listMyJobs, type JobStatus, type TechJob } from '../../services/technician'
import { useUser } from '../../store/store'
import { jobChip, jobLink } from './jobs'

/** Statuses of each dashboard group, in the order the work happens. */
const GROUPS: { id: 'qc' | 'live' | 'ready'; statuses: JobStatus[] }[] = [
  { id: 'qc', statuses: ['WRITTEN'] },
  { id: 'live', statuses: ['WRITING', 'PAUSED'] },
  { id: 'ready', statuses: ['SCHEDULED', 'PREPARING'] },
]

/** The technician's day: the jobs the Manager scheduled for you. */

export default function TechDashboard() {
  const t = useT()
  const locale = useLocale()
  const user = useUser()

  const jobs = useAsync(async () => (await listMyJobs({ status: OPEN_STATUSES })).items, [], 30000)
  const mine = [...(jobs.data ?? [])].sort((a, b) => a.slotStart.localeCompare(b.slotStart))
  const inGroup = (g: (typeof GROUPS)[number]) => mine.filter((j) => g.statuses.includes(j.status))
  const count = (id: (typeof GROUPS)[number]['id']) => inGroup(GROUPS.find((g) => g.id === id)!).length
  const queueMinutes = mine.reduce((a, j) => a + j.durationMin, 0)
  const maxMin = Math.max(1, ...mine.map((j) => j.durationMin))
  const today = new Date().toLocaleDateString(locale, { weekday: 'long', day: 'numeric', month: 'long' })
  const when = (iso: string) => new Date(iso).toLocaleString(locale, { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })

  return (
    <Shell area="tech" active="dashboard" title={t('wk.hello', { name: user?.name ?? t('td.technician') })} lede={today}>
      <div className="row3">
        <Kpi icon={<ClipboardText size={20} aria-hidden />} tone="a" title={t('td.kpi.qc')} value={count('qc')} note={t('td.kpi.qcHint')} to="/tech/qc" />
        <Kpi icon={<PlayCircle size={20} aria-hidden />} tone="p" title={t('td.kpi.live')} value={count('live')} note={t('td.kpi.liveHint')} to="/tech/preview" />
        <Kpi icon={<Timer size={20} aria-hidden />} tone="b" title={t('td.kpi.ready')} value={count('ready')} note={t('td.kpi.readyHint')} to="/tech/preview" />
      </div>
      {jobs.error ? <p className="lg-error" role="alert">{errText(t, orderErrorKey(jobs.error))}</p> : null}

      <div className="flex">
        <section className="panel" style={{ flex: '2 1 560px' }} aria-labelledby="td-orders-h">
          <div className="ph"><h2 id="td-orders-h">{t('td.myJobs')}</h2><span className="sub">{t('td.assigned', { n: mine.length })} · {t('td.queueTime')} {t('td.min', { n: queueMinutes })}</span></div>
          {GROUPS.map((g) => {
            const rows = inGroup(g)
            if (!rows.length) return null
            return (
              <div key={g.id} className="list">
                <div className="ph" style={{ padding: '6px 2px' }}><b>{t(`td.group.${g.id}`)}</b><span className="sub">{t(`td.group.${g.id}.note`)}</span></div>
                {rows.map((j) => <JobRow key={j.id} job={j} when={when(j.slotStart)} />)}
              </div>
            )
          })}
          {jobs.data && !mine.length && (
            <div className="sd-empty">
              <b>{t('td.none')}</b>
              <span>{t('td.noneBody')}</span>
            </div>
          )}
        </section>

        <section className="panel" style={{ flex: '1 1 340px' }} aria-labelledby="td-queue-h">
          <div className="ph"><h2 id="td-queue-h">{t('td.queueTitle')}</h2></div>
          {mine.length ? (
            <div className="list">
              {mine.map((j) => (
                <div key={j.id} className="item">
                  <div className="t"><b>{j.orderCode}</b></div>
                  <div style={{ width: 160 }}><div className="bar"><i style={{ width: `${(j.durationMin / maxMin) * 100}%` }} /></div></div>
                  <b className="mono">{j.durationMin}m</b>
                </div>
              ))}
            </div>
          ) : (
            <p className="sub">{t('td.noOpen')}</p>
          )}
          <p className="sub">{t('td.queueNote')}</p>
        </section>
      </div>
    </Shell>
  )
}

function JobRow({ job: j, when }: { job: TechJob; when: string }) {
  const t = useT()
  return (
    <Link to={jobLink(j.id, j.status)} className="item">
      <div className="t"><b>{j.orderCode}</b><span>{when}{j.isRewrite ? ` · ${t('po.rewrite')}` : ''}</span></div>
      <span className={`chip ${jobChip(j.status)}`}>{t(`js.${j.status}`)}</span>
      <span className="mono sub">{j.robotCode} · {t('td.min', { n: j.durationMin })}</span>
    </Link>
  )

}
