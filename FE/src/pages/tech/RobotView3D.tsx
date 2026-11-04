import { useEffect, useState } from 'react'
import { useT } from '../../i18n'
import { viewTicket } from '../../services/robot'
import { flowError } from './flow'

/**
 * The robot's live 3D view, always on while the job is active: the backend's read-only page `/viewer/robot.html` in an
 * iframe, opened with a view ticket (`POST /technician/robots/{id}/view-ticket`). A ticket lasts an hour; a new one is
 * asked for a minute before it ends, so the frame never goes blank.
 */
export default function RobotView3D({ robotId, robotCode }: { robotId: number; robotCode: string }) {
  const t = useT()
  const [view, setView] = useState<{ url: string; expiresIn: number } | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let alive = true
    let timer = 0
    const open = () => viewTicket(robotId).then((v) => {
      if (!alive) return
      setView(v)
      setError(null)
      timer = window.setTimeout(() => void open(), Math.max(60, v.expiresIn - 60) * 1000)
    }, (e: unknown) => { if (alive) setError(e) })
    void open()
    return () => { alive = false; window.clearTimeout(timer) }
  }, [robotId, attempt])

  const frame = view
    ? <iframe className="rb-frame" src={view.url} title={t('rb.view3d')} />
    : error
      ? <div className="rb-frame rb-frame--msg" role="alert"><p>{flowError(error, t)}</p>
        <button type="button" className="sd-btn" onClick={() => setAttempt((n) => n + 1)}>{t('td.api.reload')}</button></div>
      : <div className="rb-frame rb-frame--msg" role="status"><p>{t('co.loading')}</p></div>
  return <section className="panel rb-view" aria-labelledby="rb-view-h">
    <div className="ph"><h2 id="rb-view-h">{t('rb.view3d')}</h2><span className="sub">{robotCode || robotId}</span></div>
    {frame}
  </section>
}
