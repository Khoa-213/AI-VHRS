import { ArrowLeft, Gear, List, Scroll, SignOut, SquaresFour, Users, X } from '@phosphor-icons/react'
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
import '../ws/ws.css'
import '../ws/workshop.css'
import '../ws/staff-ui.css'
import '../ws/staff-theme.css'
import '../ws/staff-depth.css'
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

  const items: { key: AdminKey; to: string; icon: ReactNode; count?: number }[] = [
    { key: 'overview', to: '/admin', icon: <SquaresFour size={22} aria-hidden /> },
    { key: 'accounts', to: '/admin/accounts', icon: <Users size={22} aria-hidden />, count: locked.data ?? 0 },
    { key: 'audit', to: '/admin/audit', icon: <Scroll size={22} aria-hidden /> },
    { key: 'settings', to: '/admin/settings', icon: <Gear size={22} aria-hidden /> },
  ]

  const name = user?.name ?? t('role.admin')
  const close = () => setOpen(false)
  return (
    <div className={`ws ws-staff adm adm-app${open ? ' staff-sidebar-open' : ''}`}>
      <SkipLink />
      <header className="staff-header">
        <div className="staff-header-brand">
          <button type="button" className="staff-sidebar-menu" aria-label={t('adm.menuOpen')} aria-expanded={open} aria-controls="staff-sidebar" onClick={() => setOpen(true)}><List size={22} aria-hidden /></button>
          <Link to="/admin" className="staff-brand" aria-label={t('rail.adminMark')}><BrandLogo /></Link>
        </div>
        <div className="staff-header-tools">
          <NotificationBell variant="ws" />
          <AppearanceSwitch className="staff-theme adm-theme" />
          <LanguageToggle />
          <div className="staff-user">
            <Link to="/account/profile" className="staff-user-button" aria-label={t('acct.nav.profile')} title={t('acct.nav.profile')}>
              <span className="avatar">{initials(name)}</span><span className="staff-user-name">{name}<small>{t('role.admin')}</small></span>
            </Link>
          </div>
        </div>
      </header>
      <aside className="staff-sidebar" id="staff-sidebar" aria-label={t('adm.navAria')}>
        <div className="staff-sidebar-head">
          <button type="button" className="staff-sidebar-close" aria-label={t('adm.menuClose')} onClick={close}><X size={20} aria-hidden /></button>
        </div>
        <nav className="staff-nav" aria-label={t('adm.navAria')}>
          {items.map((it) => (
            <Link key={it.key} to={it.to} className={active === it.key ? 'on' : undefined} aria-current={active === it.key ? 'page' : undefined} onClick={close}>
              {it.icon}<span className="staff-nav-label">{t(`adm.nav.${it.key}`)}</span>
              {!!it.count && <span className="staff-nav-count" aria-label={t('adm.nav.lockedCount', { n: it.count })}>{it.count}</span>}
            </Link>
          ))}
        </nav>
        <div className="staff-sidebar-footer">
          <button type="button" className="staff-sidebar-signout" onClick={() => { signOut(); navigate('/') }}><SignOut size={18} aria-hidden />{t('rail.signOut')}</button>
        </div>
      </aside>
      <button type="button" className="staff-sidebar-scrim" aria-label={t('adm.menuClose')} onClick={close} />
      <div className="app2">
        <main className="main2" id="main" data-screen-label="Admin">
          <header className="hd">
            <div className="t">
              {active !== 'overview' && <Link to="/admin" className="staff-back adm-back"><ArrowLeft size={15} aria-hidden />{t('adm.backOverview')}</Link>}
              <h1 className="adm-h1">{title}</h1>
            </div>
            {actions && <div className="staff-page-actions">{actions}</div>}
          </header>
          {children}
        </main>
      </div>
    </div>
  )
}
