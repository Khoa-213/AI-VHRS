import SkipLink from '../../components/ui/SkipLink'
import ThemeToggle from '../../components/ui/ThemeToggle'
import { GHN_LIVE, lastLog, shipmentOf, stageChip, stageOf, type Stage } from '../../services/ghn'
import { Link } from '../../router/router'
import { useAllStaffOrders } from '../../store/store'
import type { Order } from '../../types'
import StaffRail from './StaffRail'
import './dashboard.css'
import './polish.css'
import './shipping.css'

const GROUPS: { id: string; label: string; note: string; stages: Stage[] }[] = [
  { id: 'problem', label: 'Needs attention', note: 'Failed, returned or lost', stages: ['problem'] },
  { id: 'pack', label: 'To pack and book', note: 'Paid, waiting for the studio', stages: ['pack', 'book'] },
  { id: 'courier', label: 'With GHN', note: 'Booked, on the way', stages: ['courier'] },
  { id: 'done', label: 'Delivered', note: 'Closed', stages: ['done'] },
]

export default function ShippingBoard() {
  const orders = useAllStaffOrders().filter((o) => o.status === 'Shipped' || o.status === 'Delivered')
  const withStage = orders.map((o) => ({ o, stage: stageOf(o) }))
  const count = (...s: Stage[]) => withStage.filter((x) => s.includes(x.stage)).length
  const outForDelivery = orders.filter((o) => lastLog(shipmentOf(o))?.status === 'delivering').length

  return (
    <div className="sd">
      <SkipLink />
      <StaffRail active="shipping" />
      <main className="sd-body" id="main">
        <header className="sd-top">
          <div>
            <h1>Shipping</h1>
            <p>Pack paid orders, book GHN, and follow every parcel to the door.</p>
          </div>
          <div className="sd-top-right">
            <span className="sd-state">{GHN_LIVE ? 'GHN live' : 'GHN simulated'}</span>
            <ThemeToggle className="vh-icon-btn" />
          </div>
        </header>

        <div className="sp-body">
          <div className="sd-kpis">
            <Kpi label="To pack or book" value={count('pack', 'book')} tone="accent" />
            <Kpi label="With GHN" value={count('courier')} />
            <Kpi label="Out for delivery" value={outForDelivery} />
            <Kpi label="Needs attention" value={count('problem')} />
          </div>

          {GROUPS.map((g) => {
            const rows = withStage.filter((x) => g.stages.includes(x.stage))
            if (g.id === 'problem' && !rows.length) return null
            return (
              <section key={g.id} className="sd-card" aria-labelledby={`sp-${g.id}`}>
                <div className="sd-card-head">
                  <h2 id={`sp-${g.id}`}>{g.label}</h2>
                  <span className="sd-tag">{g.note}</span>
                </div>
                {rows.length ? (
                  <ul className="sp-list">
                    {rows.map(({ o }) => <Row key={o.id} order={o} />)}
                  </ul>
                ) : (
                  <div className="sd-empty">
                    <b>Nothing here</b>
                    <span>
                      {g.id === 'pack'
                        ? 'Orders appear here after the customer approves the photos and pays.'
                        : g.id === 'courier'
                          ? 'Parcels you book with GHN show up here until they are delivered.'
                          : 'Delivered parcels are listed here.'}
                    </span>
                  </div>
                )}
              </section>
            )
          })}
        </div>
      </main>
    </div>
  )
}

function Kpi({ label, value, tone }: { label: string; value: number; tone?: 'accent' }) {
  return (
    <div className={`sd-kpi${tone ? ' ' + tone : ''}`}>
      <span className="sd-label">{label}</span>
      <b className="vh-mono">{value}</b>
    </div>
  )
}

function Row({ order: o }: { order: Order }) {
  const chip = stageChip(o)
  const s = shipmentOf(o)
  return (
    <li>
      <Link to={`/staff/shipping/${encodeURIComponent(o.id)}`} className="sd-row">
        <span className="sd-row-main">
          <span className="sd-row-title">{o.title}</span>
          <span className="sd-row-meta">{o.id} · {o.shipTo?.name || o.name || 'Customer'}{s.ghnCode ? ` · ${s.ghnCode}` : ''}</span>
        </span>
        <span className="sd-row-side">
          <span className="vh-chip" style={{ color: chip.color }}>{chip.label}</span>
          {o.shipTo?.city && <span className="sd-row-meta">{o.shipTo.city}</span>}
        </span>
      </Link>
    </li>
  )
}
