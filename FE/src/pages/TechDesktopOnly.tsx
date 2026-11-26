import { Desktop } from '@phosphor-icons/react'
import LanguageToggle from '../components/ui/LanguageToggle'
import { useAsync } from '../hooks/useAsync'
import { useLocale, useT } from '../i18n'
import { navigate } from '../router/router'
import { api } from '../services/api'
import { errText, orderErrorKey } from '../services/orders'
import { signOut } from '../store/store'

interface Row { id: number; order_code: string; robot_id: number | null; robot_code: string; status: string; slot_start: string }
interface Page { items: Row[] }

async function myJobs(): Promise<Row[]> {
  const page: Page = await api('/technician/jobs?page_size=50')
  return page.items
}

/**
 * Technicians do not work on the web (owner decision 2026-11-26, `BE/docs/FE_TECH_WORKSPACE_HANDOFF.md` section 3): everything is
 * on the workstation screen the Robot Agent serves (`http://<workstation>:8765/`). A technician signed in here, or an old
 * `/tech...` link from a notification or e-mail, lands on this notice with their jobs listed read only (no actions).
 */
export default function TechDesktopOnly() {
  const t = useT()
  const locale = useLocale()
  const jobs = useAsync(myJobs, [], 60000)
  const when = (iso: string) => new Date(iso).toLocaleString(locale, { dateStyle: 'short', timeStyle: 'short' })
  return (
    <main className="vh-panel" style={{ alignItems: 'flex-start', maxWidth: 720, margin: '10vh auto', padding: 24, gap: 16 }}>
      <div style={{ display: 'flex', width: '100%', justifyContent: 'space-between', alignItems: 'center' }}>
        <Desktop size={40} aria-hidden />
        <LanguageToggle />
      </div>
      <h1 className="vh-h1">{t('tdo.title')}</h1>
      <p className="vh-lede">{t('tdo.body')}</p>
      <code style={{ fontSize: 18, fontWeight: 700 }}>{t('tdo.address')}</code>
      <section style={{ width: '100%' }} aria-labelledby="tdo-jobs">
        <h2 id="tdo-jobs" style={{ fontSize: 17, margin: '8px 0' }}>{t('tdo.jobs')}</h2>
        {!!jobs.error && <p className="lg-error" role="alert">{errText(t, orderErrorKey(jobs.error))}</p>}
        {jobs.data && !jobs.data.length && <p className="sub">{t('tdo.none')}</p>}
        {!!jobs.data?.length && (
          <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'grid', gap: 8 }}>
            {jobs.data.map((j) => (
              <li key={j.id} style={{ border: '1px solid var(--line, #ddd)', borderRadius: 10, padding: '10px 12px' }}>
                <b>{j.order_code}</b> · {t(`js.${j.status}`)}
                <br />
                <span className="sub">{when(j.slot_start)} · {j.robot_id === null ? t('tdo.noRobot') : t('tdo.robot', { code: j.robot_code })}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
      <button type="button" className="vh-btn vh-btn--primary" onClick={() => { signOut(); navigate('/') }}>{t('acct.signOut')}</button>
    </main>
  )
}
