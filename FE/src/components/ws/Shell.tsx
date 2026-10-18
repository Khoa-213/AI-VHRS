import { CalendarCheck, ClipboardText, House, Package, PlayCircle, Receipt, Scroll, SealCheck, SignOut, SquaresFour, Users } from '@phosphor-icons/react'
import type { ReactNode } from 'react'
import { useAsync } from '../../hooks/useAsync'
import { useT } from '../../i18n'
import { Link } from '../../router/router'
import { listWork, pendingApprovals, scheduleQueue } from '../../services/workshop'
import { phaseOf, useNow } from '../../pages/tech/phase'
import { signOut, useAllStaffOrders, useUser } from '../../store/store'
import LanguageToggle from '../ui/LanguageToggle'
import SkipLink from '../ui/SkipLink'
import './ws.css'
import './workshop.css'

export type Area = 'staff' | 'manager' | 'tech' | 'admin'
export type RailKey = 'dashboard' | 'review' | 'approvals' | 'schedule' | 'catalog' | 'pricing' | 'preview' | 'qc' | 'accounts' | 'audit'

interface Item {
  key: RailKey
  to: string
  label: string
  icon: ReactNode
  count?: number
}

const initials = (name: string) => name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase() || '?'

/** Counts that wait for this person, from the API for the workshop and from the local store for technicians. */
function useCounts(area: Area, techId?: string) {
  const orders = useAllStaffOrders()
  const now = useNow(1000)
  const api = useAsync(
    async () => (area === 'tech' || area === 'admin'
      ? null
      : {
        intake: (await listWork({ status: 'SUBMITTED', pageSize: 1 })).total,
        approvals: area === 'manager' ? (await pendingApprovals()).total : 0,
        schedule: area === 'manager' ? (await scheduleQueue()).total : 0,
      }),
    [area],
    area === 'tech' || area === 'admin' ? undefined : 60000,
  )
  const qc = orders.filter((o) => o.assignment?.techId === techId && phaseOf(o, now) === 'qc').length
  return { ...(api.data ?? { intake: 0, approvals: 0, schedule: 0 }), qc }
}

/**
 * Frame of every workshop screen: the icon pill on the left and the page header. Staff, Manager and Technician share it;
 * the pill shows what that role can open. Counts on the icons are what waits for the person.
 */
export default function Shell({
  area, active, title, lede, tools, children,
}: {
  area: Area
  active: RailKey
  title: string
  lede?: string
  tools?: ReactNode
  children: ReactNode
}) {
  const t = useT()
  const user = useUser()
  const c = useCounts(area, user?.techId)
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
      : [
        { key: 'dashboard', to: '/staff', label: t('rail.dashboard'), icon: icon(SquaresFour) },
        { key: 'review', to: '/staff/review', label: t('rail.review'), icon: icon(ClipboardText), count: c.intake },
        ...(area === 'manager'
          ? ([
            'gap',
            { key: 'approvals', to: '/staff/approvals', label: t('rail.approvals'), icon: icon(SealCheck), count: c.approvals },
            { key: 'schedule', to: '/staff/schedule', label: t('rail.schedule'), icon: icon(CalendarCheck), count: c.schedule },
            { key: 'catalog', to: '/staff/catalog', label: t('rail.catalog'), icon: icon(Package) },
            { key: 'pricing', to: '/staff/pricing', label: t('rail.pricing'), icon: icon(Receipt) },
          ] as (Item | 'gap')[])
          : []),
      ]

  const name = user?.name ?? ''
  const role = area === 'manager' ? t('wk.roleManager') : area === 'tech' ? t('role.technician') : area === 'admin' ? t('role.admin') : t('wk.roleStaff')

  return (
    <div className="ws">
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
              <LanguageToggle className="ibtn" />
              <div className="me2"><span className="avatar">{initials(name)}</span><div>{name}<small>{role}</small></div></div>
            </div>
          </header>
          {children}
        </main>
      </div>
    </div>
  )
}
