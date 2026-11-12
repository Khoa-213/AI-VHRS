import { ArrowLeft, Gear, House, List, Scroll, SignOut, SquaresFour, Users, X } from '@phosphor-icons/react'
import { useEffect, useState, type ReactNode } from 'react'
import { useAsync } from '../../hooks/useAsync'
import { useT } from '../../i18n'
import { Link, navigate } from '../../router/router'
import { listAccounts } from '../../services/admin'
import { signOut, useUser } from '../../store/store'
import AppearanceSwitch from '../ui/AppearanceSwitch'
import BrandLogo from '../ui/BrandLogo'
import LanguageToggle from '../ui/LanguageToggle'
import NotificationBell from '../ui/NotificationBell'
import SkipLink from '../ui/SkipLink'
import '../ui/language.css'
import './admin-shell.css'
import './admin-ui.css'

export type AdminKey = 'overview' | 'accounts' | 'audit' | 'settings'

const initials = (name: string) => name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase() || '?'

/** Shared admin navigation and theme-aware workspace, with a drawer on small screens. */
export default function AdminFrame({
  active, title, actions, children,
}: {
  active: AdminKey
  title: string
  /** The one or two actions of the screen, shown at the top right of the page. */
  actions?: ReactNode
  children: ReactNode
}) {
  const t = useT()
  const user = useUser()
  const [open, setOpen] = useState(false)
  // Locked accounts are the thing an Admin has to look at, so they get a count on the menu.
  const locked = useAsync(async () => (await listAccounts({ status: 'LOCKED', pageSize: 1 })).total, [], 120000)

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open])

  const items: { key: AdminKey; group: string; to: string; icon: ReactNode; count?: number }[] = [
    { key: 'overview', group: 'adm.group.overview', to: '/admin', icon: <SquaresFour size={22} aria-hidden /> },
    { key: 'accounts', group: 'adm.group.manage', to: '/admin/accounts', icon: <Users size={22} aria-hidden />, count: locked.data ?? 0 },
    { key: 'audit', group: 'adm.group.manage', to: '/admin/audit', icon: <Scroll size={22} aria-hidden /> },
    { key: 'settings', group: 'adm.group.system', to: '/admin/settings', icon: <Gear size={22} aria-hidden /> },
  ]

  const name = user?.name ?? t('role.admin')
  let lastGroup = ''
  return (
    <div className={`adm adm-app${open ? ' open' : ''}`}>
      <SkipLink />
      <aside className="adm-side" id="adm-side" aria-label={t('adm.navAria')}>
        <Link to="/admin" className="adm-brand" onClick={() => setOpen(false)}>
          <BrandLogo />
          <span>{t('adm.eyebrow')}</span>
        </Link>
        <nav aria-label={t('adm.navAria')}>
          {items.map((it) => {
            const head = it.group !== lastGroup ? <span key={`g-${it.group}`} className="adm-group">{t(it.group)}</span> : null
            lastGroup = it.group
            return (
              <div key={it.key}>
                {head}
                <Link to={it.to} className={`adm-link-item${active === it.key ? ' on' : ''}`} aria-current={active === it.key ? 'page' : undefined} onClick={() => setOpen(false)}>
                  {it.icon}
                  <span className="adm-link-text">{t(`adm.nav.${it.key}`)}</span>
                  {!!it.count && <span className="adm-count" aria-label={t('adm.nav.lockedCount', { n: it.count })}>{it.count}</span>}
                </Link>
              </div>
            )
          })}
        </nav>
        <div className="adm-side-foot">
          <div className="adm-side-btns">
            <Link to="/" className="adm-side-btn"><House size={16} aria-hidden />{t('rail.site')}</Link>
            <button type="button" className="adm-side-btn" onClick={() => { signOut(); navigate('/') }}><SignOut size={16} aria-hidden />{t('rail.signOut')}</button>
          </div>
        </div>
      </aside>
      <button type="button" className="adm-scrim" aria-label={t('adm.menuClose')} onClick={() => setOpen(false)} />

      <div className="adm-main">
        <div className="adm-top">
          <button type="button" className="adm-menu-btn" aria-label={t(open ? 'adm.menuClose' : 'adm.menuOpen')} aria-expanded={open} aria-controls="adm-side" onClick={() => setOpen(!open)}>
            {open ? <X size={22} aria-hidden /> : <List size={22} aria-hidden />}
          </button>
          <div className="adm-tools">
            <AppearanceSwitch className="adm-theme" />
            <NotificationBell variant="adm" />
            <LanguageToggle />
            <div className="adm-me">
              <span className="adm-me-av" aria-hidden>{initials(name)}</span>
              <span className="adm-me-text"><b>{name}</b><span>{t('role.admin')}</span></span>
            </div>
          </div>
        </div>

        <main className="adm-page" id="main" data-screen-label="Admin">
          <header className="adm-head">
            <div className="adm-head-text">
              {active !== 'overview' && <Link to="/admin" className="adm-back"><ArrowLeft size={16} aria-hidden />{t('adm.backOverview')}</Link>}
              <h1 className="adm-h1">{title}</h1>
            </div>
            {actions && <div className="adm-head-actions">{actions}</div>}
          </header>
          {children}
        </main>
      </div>
    </div>
  )
}
