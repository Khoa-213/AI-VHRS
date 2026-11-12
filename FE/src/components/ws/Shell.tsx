import { ArrowLeft, ChartBar, ChatCircleText, List, X, Money, Truck, CalendarCheck, ClipboardText, House, Package, PlayCircle, Receipt, Robot, Scroll, SealCheck, SignOut, SquaresFour, Users } from '@phosphor-icons/react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useAsync } from '../../hooks/useAsync'
import { useT } from '../../i18n'
import { Link } from '../../router/router'
import { listWork, pendingApprovals, scheduleQueue } from '../../services/workshop'
import { workshopRefunds } from '../../services/refunds'
import { managerAlerts } from '../../services/managerOps'

import { listTechJobs } from '../../services/technician'

import { signOut, useUser } from '../../store/store'
import ChatDock from '../ui/ChatDock'
import LanguageToggle from '../ui/LanguageToggle'
import NotificationBell from '../ui/NotificationBell'
import SkipLink from '../ui/SkipLink'
import RobotAlertBell from './RobotAlertBell'
import BrandLogo from '../ui/BrandLogo'
import AppearanceSwitch from '../ui/AppearanceSwitch'
import './ws.css'
import './workshop.css'
import './staff-ui.css'
import './staff-theme.css'
import './staff-depth.css'
import './manager-ui.css'

export type Area = 'staff' | 'manager' | 'tech' | 'admin'
export type RailKey = 'dashboard' | 'fulfillment' | 'review' | 'approvals' | 'schedule' | 'catalog' | 'pricing' | 'preview' | 'qc' | 'accounts' | 'audit' | 'refunds' | 'reports' | 'robots' | 'reviews'

interface Item {
  key: RailKey
  to: string
  label: string
  icon: ReactNode
  count?: number
}

const initials = (name: string) => name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase() || '?'


/** Refunds to transfer plus money flagged for a refund; 0 when the list cannot be read. */
const pendingRefundCount = async () => {
  try {
    const r = await workshopRefunds('PENDING')
    return r.refunds.length + r.orphans.length
  } catch {
    return 0
  }
}

/** Open robot alerts for a Manager; 0 when they cannot be read. */
const openAlertCount = async () => {
  try {
    return (await managerAlerts({ pageSize: 1 })).total
  } catch {
    return 0
  }
}

/** Counts that wait for this person, all from the API: the workshop queues, or a technician's written jobs. */
function useCounts(area: Area) {
  const api = useAsync(
    async () => (area === 'admin'
      ? null
      : area === 'tech'
        ? { intake: 0, approvals: 0, schedule: 0, refunds: 0, alerts: 0, qc: (await listTechJobs({ status: ['WRITTEN'], pageSize: 1 })).total }
        : {
          intake: (await listWork({ status: 'SUBMITTED', pageSize: 1 })).total,
          approvals: area === 'manager' ? (await pendingApprovals()).total : 0,
          schedule: area === 'manager' ? (await scheduleQueue()).total : 0,
          refunds: await pendingRefundCount(),
          alerts: area === 'manager' ? await openAlertCount() : 0,
          qc: 0,
        }),
    [area],
    area === 'admin' ? undefined : 60000,
  )
  return api.data ?? { intake: 0, approvals: 0, schedule: 0, refunds: 0, alerts: 0, qc: 0 }

}

/**
 * Frame of every workshop screen: the icon pill on the left and the page header. Staff, Manager and Technician share it;
 * the pill shows what that role can open. Counts on the icons are what waits for the person.
 */
export default function Shell({
  area, active, title, lede, tools, pinned, children,
}: {
  area: Area
  active: RailKey
  title: string
  lede?: string
  tools?: ReactNode
  /** Shown along the bottom of the header, which stays at the top of the page while scrolling (for example a job's progress). */
  pinned?: ReactNode
  children: ReactNode
}) {
  const t = useT()
  const user = useUser()

  const [sidebarOpen, setSidebarOpen] = useState(false)
  const sidebar = useRef<HTMLElement>(null)
  const menuButton = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (!sidebarOpen || (area !== 'staff' && area !== 'manager')) return
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    sidebar.current?.querySelector<HTMLElement>('a, button')?.focus()
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setSidebarOpen(false)
      if (event.key === 'Tab') {
        const nodes = [...(sidebar.current?.querySelectorAll<HTMLElement>('a[href], button:not(:disabled), input:not(:disabled)') ?? [])].filter((node) => node.getClientRects().length)
        const first = nodes[0], last = nodes[nodes.length - 1]
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
        if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
      }
    }
    document.addEventListener('keydown', key)
    return () => { document.body.style.overflow = previousOverflow; document.removeEventListener('keydown', key); menuButton.current?.focus() }
  }, [sidebarOpen, area])

  const c = useCounts(area)

  const icon = (I: typeof SquaresFour) => <I size={22} weight="regular" aria-hidden />

  const items: (Item | 'gap')[] =
    area === 'admin'
      ? [
        { key: 'dashboard', to: '/admin', label: t('rail.dashboard'), icon: icon(SquaresFour) },
        { key: 'accounts', to: '/admin/accounts', label: t('rail.accounts'), icon: icon(Users) },
        { key: 'audit', to: '/admin/audit', label: t('rail.audit'), icon: icon(Scroll) },
      ]
      : area === 'tech'
      ? [
        { key: 'dashboard', to: '/tech', label: t('rail.dashboard'), icon: icon(SquaresFour) },
        { key: 'preview', to: '/tech/preview', label: t('rail.preview'), icon: icon(PlayCircle) },
        { key: 'qc', to: '/tech/qc', label: t('rail.qc'), icon: icon(ClipboardText), count: c.qc },
      ]
      : area === 'manager'
      ? [
        { key: 'dashboard', to: '/staff', label: t('rail.dashboard'), icon: icon(SquaresFour) },
        { key: 'reports', to: '/staff/reports', label: t('mgr.nav.reports'), icon: icon(ChartBar) },
        { key: 'review', to: '/staff/review', label: t('rail.review'), icon: icon(ClipboardText), count: c.intake },
        { key: 'approvals', to: '/staff/approvals', label: t('rail.approvals'), icon: icon(SealCheck), count: c.approvals },
        { key: 'fulfillment', to: '/staff/fulfillment', label: t('sp.title'), icon: icon(Truck) },
        { key: 'refunds', to: '/staff/refunds', label: t('rf.pageTitle'), icon: icon(Money), count: c.refunds },
        { key: 'schedule', to: '/staff/schedule', label: t('rail.schedule'), icon: icon(CalendarCheck), count: c.schedule },
        { key: 'robots', to: '/staff/robots', label: t('mgr.nav.robots'), icon: icon(Robot), count: c.alerts },
        { key: 'reviews', to: '/staff/reviews', label: t('mgr.nav.reviews'), icon: icon(ChatCircleText) },
        { key: 'catalog', to: '/staff/catalog', label: t('rail.catalog'), icon: icon(Package) },
        { key: 'pricing', to: '/staff/pricing', label: t('rail.pricing'), icon: icon(Receipt) },
      ]
      : [
        { key: 'dashboard', to: '/staff', label: t('rail.dashboard'), icon: icon(SquaresFour) },
        { key: 'review', to: '/staff/review', label: t('rail.review'), icon: icon(ClipboardText), count: c.intake },
        { key: 'fulfillment', to: '/staff/fulfillment', label: t('sp.title'), icon: icon(Truck) },
        { key: 'refunds', to: '/staff/refunds', label: t('rf.pageTitle'), icon: icon(Money), count: c.refunds },
      ]

  const name = user?.name ?? ''
  const role = area === 'manager' ? t('wk.roleManager') : area === 'tech' ? t('role.technician') : area === 'admin' ? t('role.admin') : t('wk.roleStaff')

  // Staff and Manager share the Staff frame (header, sidebar, drawer, light/dark); the Manager has its own destinations.
  const navLabel = t(area === 'manager' ? 'mgr.navAria' : 'rail.staff')
  if (area === 'staff' || area === 'manager') return (
    <div className={`ws ws-staff${area === 'manager' ? ' ws-manager' : ''}${sidebarOpen ? ' staff-sidebar-open' : ''}${active === 'fulfillment' ? ' ws-fulfillment' : ''}`}>
      <SkipLink />
      <header className="staff-header">
        <div className="staff-header-brand">
          <button ref={menuButton} type="button" className="staff-sidebar-menu" aria-label={t('adm.menuOpen')} aria-expanded={sidebarOpen} aria-controls="staff-sidebar" onClick={() => setSidebarOpen(true)}><List size={22} aria-hidden /></button>
          <Link to="/staff" className="staff-brand" aria-label={t('rail.staffMark')}><BrandLogo /></Link>
        </div>
        <div className="staff-header-tools">
          <NotificationBell variant="ws" />
          <AppearanceSwitch className="staff-theme" />
          <LanguageToggle />
          <div className="staff-user">
            <Link to="/account/profile" className="staff-user-button" aria-label={t('acct.nav.profile')} title={t('acct.nav.profile')}>
              <span className="avatar">{initials(name)}</span><span className="staff-user-name">{name}<small>{role}</small></span>
            </Link>
          </div>
        </div>
      </header>
      <aside ref={sidebar} className="staff-sidebar" id="staff-sidebar" aria-label={navLabel}>
        <div className="staff-sidebar-head">
          <button type="button" className="staff-sidebar-close" aria-label={t('adm.menuClose')} onClick={() => setSidebarOpen(false)}><X size={20} aria-hidden /></button>
        </div>
        <nav className="staff-nav" aria-label={navLabel}>
          {items.filter((it): it is Item => it !== 'gap').map((it) => (
            <Link key={it.key} to={it.to} className={active === it.key ? 'on' : undefined} aria-current={active === it.key ? 'page' : undefined} onClick={() => setSidebarOpen(false)}>
              {it.icon}<span className="staff-nav-label">{it.label}</span>{!!it.count && <span className="staff-nav-count">{it.count}</span>}
            </Link>
          ))}
        </nav>
        <div className="staff-sidebar-footer">
          <button type="button" className="staff-sidebar-signout" onClick={() => signOut()}><SignOut size={18} aria-hidden />{t('rail.signOut')}</button>
        </div>
      </aside>
      <button type="button" className="staff-sidebar-scrim" aria-label={t('adm.menuClose')} onClick={() => setSidebarOpen(false)} />
      <div className="app2">
        <main className="main2" id="main">
          <header className="hd">
            <div className="t">
              {active !== 'dashboard' && <Link to="/staff" className="staff-back"><ArrowLeft size={15} aria-hidden />{t('adm.backOverview')}</Link>}
              <h1>{title}</h1>
            </div>
            {tools && <div className="staff-page-actions">{tools}</div>}
            {pinned && <div className="hd-pinned">{pinned}</div>}
          </header>
          {children}
        </main>
      </div>
      <ChatDock side="workshop" />
    </div>
  )

  return (
    <div className={`ws${area === 'tech' ? ' ws-tech' : ''}${active === 'fulfillment' ? ' ws-fulfillment' : ''}`}>
      <SkipLink />
      <div className="app2">
        <div className="rail-col">
          <Link to={area === 'tech' ? '/tech' : area === 'admin' ? '/admin' : '/staff'} className="logo" aria-label={t(area === 'tech' ? 'rail.techMark' : area === 'admin' ? 'rail.adminMark' : 'rail.staffMark')}>AV</Link>
          <nav className="rail" aria-label={t(area === 'tech' ? 'rail.tech' : area === 'admin' ? 'rail.admin' : 'rail.staff')}>
            {items.map((it, i) =>
              it === 'gap' ? (
                <span key={`g${i}`} className="gap" />
              ) : (
                <Link
                  key={it.key}
                  to={it.to}
                  className={active === it.key ? 'on' : undefined}
                  aria-current={active === it.key ? 'page' : undefined}
                  aria-label={it.count ? `${it.label}, ${it.count}` : it.label}
                  title={it.label}
                >
                  {it.icon}
                  {!!it.count && <span className="badge-dot">{it.count}</span>}
                </Link>
              ),
            )}
          </nav>
          <div className="rail-foot">
            <Link to="/" className="ibtn" style={{ width: 48, height: 48 }} aria-label={t('rail.site')} title={t('rail.site')}><House size={20} aria-hidden /></Link>
            <button type="button" className="ibtn" style={{ width: 48, height: 48 }} aria-label={t('rail.signOut')} title={t('rail.signOut')} onClick={() => signOut()}><SignOut size={20} aria-hidden /></button>
          </div>
        </div>

        <main className="main2" id="main">
          <header className="hd">
            <div className="t">
              <h1>{title}</h1>
              {lede && <p>{lede}</p>}
            </div>
            <div className="tools">
              {tools}
              {area === 'tech' && <RobotAlertBell />}
              <NotificationBell variant="ws" />
              <LanguageToggle />
              <div className="me2"><span className="avatar">{initials(name)}</span><div>{name}<small>{role}</small></div></div>
            </div>
            {pinned && <div className="hd-pinned">{pinned}</div>}
          </header>
          {children}
        </main>
      </div>
    </div>
  )
}
