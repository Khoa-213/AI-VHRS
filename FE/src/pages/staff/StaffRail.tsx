import { ClipboardText, House, SignOut, SquaresFour, Truck } from '@phosphor-icons/react'
import { useT } from '../../i18n'
import { stageOf } from '../../services/ghn'
import { Link } from '../../router/router'
import { signOut, useAllStaffOrders } from '../../store/store'

type Tab = 'dashboard' | 'review' | 'shipping'

/** Icon rail shared by the staff dashboard and the shipping desk. */
export default function StaffRail({ active }: { active: Tab }) {
  const t = useT()
  const orders = useAllStaffOrders()
  const pending = orders.filter((o) => o.status === 'Pending').length
  const toPack = orders.filter((o) => o.status === 'Shipped' && ['pack', 'book'].includes(stageOf(o))).length

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
      {item('review', '/staff/review', t('rail.review'), <ClipboardText size={22} />, pending)}
      {item('shipping', '/staff/shipping', t('rail.shipping'), <Truck size={22} />, toPack)}
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
