import { ClipboardText, House, SignOut, SquaresFour, Truck } from '@phosphor-icons/react'
import { stageOf } from '../../services/ghn'
import { Link } from '../../router/router'
import { signOut, useAllStaffOrders } from '../../store/store'

type Tab = 'dashboard' | 'review' | 'shipping'

/** Icon rail shared by the staff dashboard and the shipping desk. */
export default function StaffRail({ active }: { active: Tab }) {
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
    <nav className="sd-rail" aria-label="Staff navigation">
      <Link to="/staff" className="sd-mark" aria-label="AI-VHRS studio">AV</Link>
      {item('dashboard', '/staff', 'Dashboard', <SquaresFour size={22} />)}
      {item('review', '/staff/review', 'Review', <ClipboardText size={22} />, pending)}
      {item('shipping', '/staff/shipping', 'Shipping', <Truck size={22} />, toPack)}
      <div className="sd-rail-end">
        <Link to="/" className="sd-nav">
          <House size={22} />
          <span>Site</span>
        </Link>
        <button type="button" className="sd-nav" onClick={() => signOut()}>
          <SignOut size={22} />
          <span>Sign out</span>
        </button>
      </div>
    </nav>
  )
}
