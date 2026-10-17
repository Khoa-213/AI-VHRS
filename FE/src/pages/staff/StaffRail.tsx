import { CalendarCheck, ClipboardText, House, Package, SealCheck, SignOut, SquaresFour } from '@phosphor-icons/react'
import { useAsync } from '../../hooks/useAsync'
import { useT } from '../../i18n'
import { Link } from '../../router/router'
import { signOut, useUser } from '../../store/store'
import { listWork, pendingApprovals, scheduleQueue } from '../../services/workshop'
import { isManagerRole } from './RequireStaff'

type Tab = 'dashboard' | 'review' | 'approvals' | 'schedule' | 'catalog'

/** Icon rail of the workshop screens. The counts are what waits for this person. */
export default function StaffRail({ active }: { active: Tab }) {
  const t = useT()
  const user = useUser()
  const manager = isManagerRole(user?.apiRole)
  const counts = useAsync(
    async () => ({
      intake: (await listWork({ status: 'SUBMITTED', pageSize: 1 })).total,
      approvals: manager ? (await pendingApprovals()).total : 0,
      schedule: manager ? (await scheduleQueue()).total : 0,
    }),
    [manager],
    60000,
  )
  const c = counts.data

  const item = (tab: Tab, to: string, label: string, icon: React.ReactNode, count = 0) => (
    <Link to={to} className={`sd-nav${active === tab ? ' on' : ''}`} aria-current={active === tab ? 'page' : undefined}>
      {icon}
      <span>{label}</span>
      {count > 0 && <b className="sd-count">{count}</b>}
    </Link>
  )

  return (
    <nav className="sd-rail" aria-label={t('rail.staff')}>
      <Link to="/staff" className="sd-mark" aria-label={t('rail.staffMark')}>AV</Link>
      {item('dashboard', '/staff', t('rail.dashboard'), <SquaresFour size={22} />)}
      {item('review', '/staff/review', t('rail.review'), <ClipboardText size={22} />, c?.intake)}
      {manager && item('approvals', '/staff/approvals', t('rail.approvals'), <SealCheck size={22} />, c?.approvals)}
      {manager && item('schedule', '/staff/schedule', t('rail.schedule'), <CalendarCheck size={22} />, c?.schedule)}
      {manager && item('catalog', '/staff/catalog', t('rail.catalog'), <Package size={22} />)}
      <div className="sd-rail-end">
        <Link to="/" className="sd-nav">
          <House size={22} />
          <span>{t('rail.site')}</span>
        </Link>
        <button type="button" className="sd-nav" onClick={() => signOut()}>
          <SignOut size={22} />
          <span>{t('rail.signOut')}</span>
        </button>
      </div>
    </nav>
  )
}
