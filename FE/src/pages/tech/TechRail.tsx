import { ClipboardText, House, PlayCircle, SignOut, SquaresFour } from '@phosphor-icons/react'
import { Link } from '../../router/router'
import { signOut, useAllStaffOrders, useUser } from '../../store/store'
import { phaseOf, useNow } from './phase'

type Tab = 'dashboard' | 'preview' | 'qc'

/** Icon rail for the technician pages. Same shape as the staff rail. */
export default function TechRail({ active }: { active: Tab }) {
  const user = useUser()
  const orders = useAllStaffOrders()
  const now = useNow(1000)
  const waiting = orders.filter((o) => o.assignment?.techId === user?.techId && phaseOf(o, now) === 'qc').length

  const item = (tab: Tab, to: string, label: string, icon: React.ReactNode, count = 0) => (
    <Link to={to} className={`sd-nav${active === tab ? ' on' : ''}`} aria-current={active === tab ? 'page' : undefined}>
      {icon}
      <span>{label}</span>
      {count > 0 && <b className="sd-count">{count}</b>}
    </Link>
  )

  return (
    <nav className="sd-rail" aria-label="Technician navigation">
      <Link to="/tech" className="sd-mark" aria-label="AI-VHRS technician desk">AV</Link>
      {item('dashboard', '/tech', 'Dashboard', <SquaresFour size={22} />)}
      {item('preview', '/tech/preview', 'Preview', <PlayCircle size={22} />)}
      {item('qc', '/tech/qc', 'QC', <ClipboardText size={22} />, waiting)}
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
