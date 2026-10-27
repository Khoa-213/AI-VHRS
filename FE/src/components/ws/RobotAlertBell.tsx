import { Bell, BellRinging } from '@phosphor-icons/react'
import { useEffect, useRef, useState } from 'react'
import { useLocale, useT } from '../../i18n'
import { ackAlert, resolveAlert, type RobotAlert } from '../../services/robot'
import { reloadRobotStatus, useRobotStatus } from '../../store/robotStatus'
import { flowError } from '../../pages/tech/flow'
import './robot-bell.css'

/**
 * Technician header: the open robot alerts (`GET /technician/robot-status`) behind a bell next to the language button.
 * The pill turns red while any alert is open. Levels 1 to 3 can be acknowledged and closed with a note here; a red (level 4)
 * alert only by a Manager.
 */
export default function RobotAlertBell() {
  const t = useT()
  const locale = useLocale()
  const status = useRobotStatus()
  const [open, setOpen] = useState(false)
  const [notes, setNotes] = useState<Record<number, string>>({})
  const [busy, setBusy] = useState<number | null>(null)
  const [error, setError] = useState('')
  const root = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)

  const robots = (status.data ?? []).filter((r) => r.alerts.length)
  const count = robots.reduce((n, r) => n + r.alerts.length, 0)
  const red = robots.some((r) => r.alerts.some((a) => a.level >= 4))

  useEffect(() => {
    if (!open) return
    const onDown = (e: PointerEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(false) }
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      setOpen(false)
      trigger.current?.focus()
    }
    document.addEventListener('pointerdown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const act = async (a: RobotAlert, resolve: boolean) => {
    setBusy(a.id); setError('')
    try {
      if (resolve) await resolveAlert(a.id, (notes[a.id] ?? '').trim())
      else await ackAlert(a.id)
      setNotes((n) => ({ ...n, [a.id]: '' }))
    } catch (e) {
      setError(flowError(e, t))
    } finally {
      setBusy(null)
      await reloadRobotStatus()
    }
  }

  const when = (iso: string) => new Date(iso).toLocaleString(locale, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })

  return (
    <div className={`rbell${count ? ' on' : ''}${red ? ' red' : ''}`} ref={root}>
      <button
        ref={trigger}
        type="button"
        className="rbell-btn"
        aria-label={count ? t('rb.bellCount', { n: count }) : t('rb.bell')}
        title={t('rb.bell')}
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        {count ? <BellRinging size={20} weight="fill" aria-hidden /> : <Bell size={20} aria-hidden />}
        {count > 0 && <span className="rbell-count">{count > 99 ? '99+' : count}</span>}
      </button>
      {open && (
        <div className="rbell-pop" role="dialog" aria-label={t('rb.alerts')}>
          <div className="rbell-h"><b>{t('rb.alerts')}</b>{count > 0 && <span className="sub">{count}</span>}</div>
          {error && <p className="lg-error" role="alert">{error}</p>}
          {!!status.error && !status.data && <p className="lg-error" role="alert">{flowError(status.error, t)}</p>}
          {status.data && !count && <p className="sub rbell-empty">{t('rb.noAlerts')}</p>}
          {robots.map((r) => (
            <section key={r.robotId} className="rbell-robot">
              <h3>{r.robotCode}<span className="sub">{r.headline}</span></h3>
              <ul>
                {r.alerts.map((a) => (
                  <li key={a.id} className={`lv${a.level}`}>
                    <b>{a.title}</b>
                    <span className="sub">{a.action}</span>
                    <span className="sub mono">{a.code} / {t('rb.level', { n: a.level })}{a.occurrences > 1 ? ` / ×${a.occurrences}` : ''} / {when(a.raisedAt)}</span>
                    <div className="rbell-act">
                      {!a.acknowledgedAt && <button type="button" className="sd-btn" disabled={busy === a.id} onClick={() => void act(a, false)}>{t('rb.ack')}</button>}
                      {a.level < 4 ? <>
                        <input className="vh-input" value={notes[a.id] ?? ''} placeholder={t('rb.resolveNote')} aria-label={t('rb.resolveNote')}
                          onChange={(e) => setNotes((n) => ({ ...n, [a.id]: e.target.value }))} />
                        <button type="button" className="sd-btn" disabled={busy === a.id || (notes[a.id] ?? '').trim().length < 3} onClick={() => void act(a, true)}>{t('rb.resolve')}</button>
                      </> : <span className="sub">{t('rb.redManagerOnly')}</span>}
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </div>
  )
}
