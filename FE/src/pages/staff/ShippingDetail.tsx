import { ArrowLeft, ArrowUpRight, ArrowsClockwise, FastForward } from '@phosphor-icons/react'
import { useState } from 'react'
import SkipLink from '../../components/ui/SkipLink'
import ShipmentTimeline from '../../components/ui/ShipmentTimeline'
import ThemeToggle from '../../components/ui/ThemeToggle'
import { useShipmentSync } from '../../hooks/useShipmentSync'
import {
  GHN_LIVE, PACK_STEPS, bookShipment, isFinal, lastLog, packed, shipmentOf, stageChip, stageOf, trackingUrl,
} from '../../services/ghn'
import { Link } from '../../router/router'
import {
  advanceCourier, saveBooking, setParcelWeight, togglePackStep, useAllStaffOrders, usePrototypeMode,
} from '../../store/store'
import { fmt } from '../../utils/format'
import StaffRail from './StaffRail'
import './dashboard.css'
import './polish.css'
import './shipping.css'

const when = (iso?: string) =>
  iso ? new Date(iso).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : 'Not set'

export default function ShippingDetail({ id }: { id: string }) {
  const order = useAllStaffOrders().find((o) => o.id === id)
  const sync = useShipmentSync(order ?? null)
  const proto = usePrototypeMode()
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const shell = (children: React.ReactNode) => (
    <div className="sd">
      <SkipLink />
      <StaffRail active="shipping" />
      <main className="sd-body" id="main">{children}</main>
    </div>
  )

  if (!order || !['Shipped', 'Delivered'].includes(order.status)) {
    return shell(
      <div className="sp-body">
        <div className="sd-empty">
          <b>{order ? 'This order is not ready to ship' : 'Order not found'}</b>
          <span>
            {order
              ? `${order.id} is ${order.status}. Shipping opens after the customer pays the final amount.`
              : `There is no order ${id}.`}
          </span>
          <Link to="/staff/shipping" className="sd-btn sp-self-start">Back to shipping</Link>
        </div>
      </div>,
    )
  }

  const s = shipmentOf(order)
  const stage = stageOf(order)
  const chip = stageChip(order)
  const last = lastLog(s)
  const booked = !!s.ghnCode
  const ready = packed(s)
  const finished = !!last && isFinal(last.status)
  const to = order.shipTo
  const address = [to?.street, to?.ward, to?.city].filter(Boolean).join(', ') || order.address || 'No address recorded'

  const book = async () => {
    if (busy || !ready || booked) return
    setBusy(true)
    setErr(null)
    try {
      const b = await bookShipment(order, s.weightG)
      saveBooking(order.id, b)
      if (!GHN_LIVE) advanceCourier(order.id)
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Could not book GHN. Try again.')
    } finally {
      setBusy(false)
    }
  }

  return shell(
    <>
      <header className="sd-top">
        <div>
          <Link to="/staff/shipping" className="sp-back"><ArrowLeft size={16} aria-hidden /> Shipping</Link>
          <h1>{order.title}</h1>
          <p>{order.id} · {to?.name || order.name || 'Customer'} · {to?.phone || order.phone || 'No phone'}</p>
        </div>
        <div className="sd-top-right">
          <span className="vh-chip" style={{ color: chip.color }}>{chip.label}</span>
          <ThemeToggle className="vh-icon-btn" />
        </div>
      </header>

      <div className="sp-body sp-two">
        <div className="sp-col">
          <section className="sd-card" aria-labelledby="sp-pack">
            <div className="sd-card-head">
              <h2 id="sp-pack">Packing</h2>
              <span className="sd-tag">{s.pack.length} of {PACK_STEPS.length} done</span>
            </div>
            <ul className="sp-checks">
              {PACK_STEPS.map((p) => {
                const done = s.pack.some((m) => m.id === p.id)
                return (
                  <li key={p.id}>
                    <label className={done ? 'done' : ''}>
                      <input
                        type="checkbox"
                        checked={done}
                        disabled={booked || order.status === 'Delivered'}
                        onChange={() => togglePackStep(order.id, p.id)}
                      />
                      <span>{p.label}</span>
                    </label>
                  </li>
                )
              })}
            </ul>
          </section>

          <section className="sd-card" aria-labelledby="sp-courier">
            <div className="sd-card-head">
              <h2 id="sp-courier">GHN courier</h2>
              {booked && <span className="sd-tag vh-mono">{s.ghnCode}</span>}
            </div>

            <dl className="sp-facts">
              <div><dt>Deliver to</dt><dd>{to?.name || order.name || 'Customer'}</dd></div>
              <div><dt>Address</dt><dd>{address}</dd></div>
              {to?.note && <div><dt>Courier note</dt><dd>{to.note}</dd></div>}
              <div><dt>Cash on delivery</dt><dd className="vh-mono">{fmt(s.codAmount)}</dd></div>
              {booked && <div><dt>GHN fee</dt><dd className="vh-mono">{fmt(s.fee ?? 0)}</dd></div>}
              {booked && <div><dt>Booked</dt><dd>{when(s.bookedAt)}</dd></div>}
              {booked && <div><dt>Expected</dt><dd>{when(s.expectedAt)}</dd></div>}
            </dl>

            <div className="sp-weight">
              <label htmlFor="sp-w">Parcel weight (g)</label>
              <input
                id="sp-w"
                className="vh-input"
                type="number"
                inputMode="numeric"
                min={1}
                value={s.weightG}
                disabled={booked}
                onChange={(e) => setParcelWeight(order.id, Number(e.target.value))}
              />
            </div>

            {!booked && order.status === 'Shipped' && (
              <>
                <button type="button" className="sd-btn sp-primary" disabled={!ready || busy} onClick={book}>
                  {busy ? 'Booking with GHN' : 'Book GHN courier'}
                </button>
                {!ready && <p className="sd-note">Finish the packing steps first.</p>}
                {err && <p className="sp-error" role="alert">{err}</p>}
              </>
            )}

            {booked && (
              <a className="sd-btn sp-self-start" href={trackingUrl(s.ghnCode!)} target="_blank" rel="noreferrer">
                Open on GHN <ArrowUpRight size={16} aria-hidden />
              </a>
            )}
          </section>
        </div>

        <section className="sd-card" aria-labelledby="sp-log">
          <div className="sd-card-head">
            <h2 id="sp-log">Activity</h2>
            {GHN_LIVE ? (
              <button type="button" className="sp-ghost" onClick={() => void sync.refresh()} disabled={!booked || sync.busy}>
                <ArrowsClockwise size={16} aria-hidden /> {sync.busy ? 'Refreshing' : 'Refresh'}
              </button>
            ) : (
              <span className="sd-tag">Simulated courier</span>
            )}
          </div>

          <ShipmentTimeline shipment={s} audience="staff" />

          {GHN_LIVE && sync.syncedAt && <p className="sd-note">Last sync {sync.syncedAt.toLocaleTimeString('en-GB')}.</p>}
          {sync.error && <p className="sp-error" role="alert">{sync.error}. Showing the last known status.</p>}

          {!GHN_LIVE && proto && booked && order.status === 'Shipped' && (
            <div className="sp-sim">
              <button type="button" className="sp-ghost" disabled={finished} onClick={() => advanceCourier(order.id)}>
                <FastForward size={16} aria-hidden /> Simulate next GHN scan
              </button>
              <span className="sd-note">Prototype only. In production GHN pushes these scans to the backend by webhook.</span>
            </div>
          )}
          {stage === 'problem' && (
            <p className="sd-note">Contact the customer. The tracking page already tells them the studio will be in touch.</p>
          )}
        </section>
      </div>
    </>,
  )
}
