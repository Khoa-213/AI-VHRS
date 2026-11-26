import { useState } from 'react'
import { useAsync } from '../../hooks/useAsync'
import { useT } from '../../i18n'
import { Link } from '../../router/router'
import { ApiError } from '../../services/api'
import { errText, orderErrorKey } from '../../services/orders'
import { assignRobot, listRobots, listTechnicians, unassignRobot, type Robot } from '../../services/workshop'
import { Panel } from './managerKit'

interface Task { (): Promise<unknown> }

/** Jobs that keep a robot with its technician (`409 ROBOT_HAS_ACTIVE_JOBS`, `details.job_ids`). */
function blockingJobs(e: unknown): number[] | null {
  if (!(e instanceof ApiError) || e.code !== 'ROBOT_HAS_ACTIVE_JOBS') return null
  const ids = (e.details as { job_ids?: unknown } | null)?.job_ids
  return Array.isArray(ids) ? ids.filter((x): x is number => typeof x === 'number') : []
}

/**
 * Manager gives each robot to one technician for good (migration 0032): `PUT` / `DELETE /manager/robots/{id}/technician`.
 * A technician may hold several robots and picks one of theirs for each job; the schedule books the technician.
 */
export default function RobotAssignments() {
  const t = useT()
  const robots = useAsync(listRobots, [])
  const techs = useAsync(listTechnicians, [])
  const [pick, setPick] = useState<Record<number, string>>({})
  const [busy, setBusy] = useState<number | null>(null)
  const [err, setErr] = useState('')
  const [jobs, setJobs] = useState<number[] | null>(null)
  const [done, setDone] = useState('')

  const run = async (r: Robot, task: Task, ok: string) => {
    if (busy) return
    setBusy(r.id); setErr(''); setJobs(null); setDone('')
    try {
      await task()
      setPick((p) => ({ ...p, [r.id]: '' }))
      setDone(ok)
    } catch (e) {
      const held = blockingJobs(e)
      if (held) { setErr(t('mgr.as.hasJobs', { name: r.technicianName ?? '' })); setJobs(held) }
      else setErr(errText(t, orderErrorKey(e)))
    } finally {
      setBusy(null)
      await Promise.all([robots.reload(), techs.reload()])
    }
  }

  const give = (r: Robot) => {
    const id = Number(pick[r.id])
    if (!id) return
    void run(r, () => assignRobot(r.id, id), t('mgr.as.saved', { code: r.code }))
  }
  const take = (r: Robot) => {
    if (!window.confirm(t('mgr.as.confirmTake', { code: r.code, name: r.technicianName ?? '' }))) return
    void run(r, () => unassignRobot(r.id), t('mgr.as.taken', { code: r.code }))
  }
  const holds = (id: number) => (techs.data ?? []).find((x) => x.id === id)?.robots.length ?? 0
  const failed = robots.error ?? techs.error

  return (
    <Panel title={t('mgr.as.title')} sub={t('mgr.as.sub')}>
      {!!failed && <p className="lg-error" role="alert">{errText(t, orderErrorKey(failed))}</p>}
      {robots.loading && !robots.data && <p className="sub" role="status">{t('co.loading')}</p>}
      {err && (
        <div className="lg-error" role="alert">
          <p>{err}</p>
          {jobs && jobs.length > 0 && (
            <p>{jobs.map((id) => `#${id}`).join(', ')} · <Link to="/staff/schedule">{t('mgr.as.toSchedule')}</Link></p>
          )}
        </div>
      )}
      {done && <p className="note-ok" role="status">{done}</p>}
      {robots.data && !robots.data.length && <p className="sub">{t('wk.noRobots')}</p>}
      {!!robots.data?.length && (
        <table className="mgr-table mgr-assign">
          <thead>
            <tr><th scope="col">{t('wk.robot')}</th><th scope="col">{t('mgr.as.owner')}</th><th scope="col">{t('mgr.as.change')}</th></tr>
          </thead>
          <tbody>
            {robots.data.map((r) => (
              <tr key={r.id}>
                <th scope="row"><b>{r.code}</b><br /><span className="sub">{r.station ?? ''} · {t(`rs.${r.status}`)}</span></th>
                <td>{r.technicianName ?? <span className="sub">{t('mgr.as.nobody')}</span>}</td>
                <td>
                  <div className="mgr-assign-row">
                    <select className="vh-select" aria-label={t('mgr.as.pick', { code: r.code })} value={pick[r.id] ?? ''}
                      disabled={busy !== null} onChange={(e) => setPick((p) => ({ ...p, [r.id]: e.target.value }))}>
                      <option value="">{t('mgr.as.choose')}</option>
                      {(techs.data ?? []).filter((x) => x.id !== r.technicianId).map((x) => (
                        <option key={x.id} value={x.id}>{x.fullName} · {t('mgr.as.holds', { n: holds(x.id) })}</option>
                      ))}
                    </select>
                    <button type="button" className="vh-btn vh-btn--primary vh-btn--sm" disabled={busy !== null || !pick[r.id]} onClick={() => give(r)}>
                      {t('mgr.as.give')}
                    </button>
                    {r.technicianId !== null && (
                      <button type="button" className="vh-btn vh-btn--ghost vh-btn--sm" disabled={busy !== null} onClick={() => take(r)}>
                        {t('mgr.as.take')}
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  )
}
