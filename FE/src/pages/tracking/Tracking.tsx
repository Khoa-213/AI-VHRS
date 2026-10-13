import { ArrowUpRight, CheckCircle, Circle, Copy } from '@phosphor-icons/react'
import { useEffect, useRef, useState } from 'react'
import Page from '../../components/layout/Page'
import { NoOrder, OrderTimeline, SpecRows } from '../../components/ui/OrderParts'
import ShipmentTimeline from '../../components/ui/ShipmentTimeline'
import { useShipmentSync } from '../../hooks/useShipmentSync'
import { PACK_STEPS, PHASES, lastLog, phaseOf, shipmentOf, stageOf, trackingUrl } from '../../services/ghn'
import { Link, orderPath } from '../../router/router'
import { useOrder } from '../../store/store'
import './tracking.css'

const day = (iso?: string) =>
  iso ? new Date(iso).toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' }) : 'To be confirmed'

export default function Tracking({ id }: { id: string | null }) {
  const order = useOrder(id)
  const sync = useShipmentSync(order)
  const [copied, setCopied] = useState(false)
  const timer = useRef<number | undefined>(undefined)
  useEffect(() => () => window.clearTimeout(timer.current), [])

  if (!order) return <NoOrder label="Tracking" />

  if (!['Shipped', 'Delivered'].includes(order.status)) {
    return (
      <Page label="Tracking" width={720}>
        <div className="vh-panel" style={{ alignItems: 'flex-start' }}>
          <span className="vh-eyebrow">Order {order.id}</span>
          <h1 className="vh-h1">Tracking starts after payment.</h1>
          <p className="vh-lede">Once you approve the photos and pay the remaining amount, we pack the piece and you can follow it here.</p>
          <Link to={orderPath(order.id, 'result')} className="vh-btn vh-btn--primary">Back to your order</Link>
        </div>
      </Page>
    )
  }

  const s = shipmentOf(order)
  const stage = stageOf(order)
  const phase = phaseOf(order)
  const last = lastLog(s)
  const packedCount = s.pack.length

  const title =
    stage === 'done' ? 'Delivered.'
    : stage === 'problem' ? 'There is a delivery problem.'
    : stage === 'courier' ? ['Packing your piece.', 'Waiting for GHN pickup.', 'On the road.', 'Out for delivery.'][phase] ?? 'On the road.'
    : 'Packing your piece.'
  const sub =
    stage === 'pack' || stage === 'book'
      ? `${packedCount} of ${PACK_STEPS.length} packing steps done.`
      : stage === 'problem'
        ? 'The studio has been told and will contact you.'
        : stage === 'done'
          ? 'Thank you for ordering with AI-VHRS.'
          : `Expected ${day(s.expectedAt)}.`

  const copy = () => {
    if (!s.ghnCode) return
    void navigator.clipboard?.writeText(s.ghnCode).then(
      () => {
        setCopied(true)
        window.clearTimeout(timer.current)
        timer.current = window.setTimeout(() => setCopied(false), 1600)
      },
      () => {},
    )
  }

  const to = order.shipTo
  const rows = [
    { k: 'Carrier', v: 'Giao Hàng Nhanh (GHN)' },
    { k: 'Expected', v: day(s.expectedAt) },
    { k: 'Deliver to', v: to?.name || order.name || 'You' },
    { k: 'Address', v: [to?.street, to?.ward, to?.city].filter(Boolean).join(', ') || order.address || 'Not recorded' },
    { k: 'Due on delivery', v: 'Nothing, paid in full' },
  ]

  return (
    <Page label="Tracking" width={1200}>
      <div className="vh-head">
        <div className="vh-head-text">
          <span className="vh-eyebrow">Order {order.id}</span>
          <h1 className="vh-h1">{title}</h1>
          <p className="vh-lede" role="status">{sub}</p>
        </div>
        <OrderTimeline labels={[...PHASES]} idx={stage === 'done' ? PHASES.length : phase} />
      </div>

      <div className="vh-cols">
        <section className="vh-col" aria-labelledby="tk-updates">
          {(stage === 'pack' || stage === 'book') && (
            <div className="vh-panel vh-panel--md">
              <h2 className="vh-h2 vh-h2--sm">Packing</h2>
              <ul className="tk-pack">
                {PACK_STEPS.map((p) => {
                  const done = s.pack.some((m) => m.id === p.id)
                  return (
                    <li key={p.id} className={done ? 'done' : ''}>
                      {done ? <CheckCircle size={22} weight="fill" aria-hidden /> : <Circle size={22} aria-hidden />}
                      <span>{p.label}</span>
                      <span className="tk-sr">{done ? 'Done' : 'Not yet'}</span>
                    </li>
                  )
                })}
              </ul>
            </div>
          )}

          <div className="vh-panel vh-panel--md">
            <h2 id="tk-updates" className="vh-h2 vh-h2--sm">Updates</h2>
            <ShipmentTimeline shipment={s} audience="customer" />
            {!s.logs.length && s.ghnCode && <p className="vh-fine">GHN has not scanned the parcel yet.</p>}
            {sync.error && <p className="vh-fine" role="alert">Could not refresh from GHN. Showing the last known status.</p>}
          </div>
        </section>

        <aside className="vh-aside" aria-label="Shipment details">
          {s.ghnCode ? (
            <div className="tk-code">
              <span>GHN tracking code</span>
              <div>
                <b className="vh-mono">{s.ghnCode}</b>
                <button type="button" className="tk-copy" onClick={copy} aria-label="Copy tracking code">
                  <Copy size={18} aria-hidden />
                  {copied ? 'Copied' : 'Copy'}
                </button>
              </div>
            </div>
          ) : (
            <div className="tk-code">
              <span>GHN tracking code</span>
              <b className="tk-wait">Added when the courier is booked</b>
            </div>
          )}

          <SpecRows rows={rows} />

          {last && stage !== 'done' && (
            <p className="vh-fine" style={{ textAlign: 'left' }}>
              Last scan {new Date(last.at).toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}
              {last.place ? ` at ${last.place}` : ''}.
            </p>
          )}

          {s.ghnCode && (
            <a className="vh-btn vh-btn--ghost vh-btn--md" href={trackingUrl(s.ghnCode)} target="_blank" rel="noreferrer">
              Open on GHN <ArrowUpRight size={18} aria-hidden />
            </a>
          )}
          <Link to={orderPath(order.id, 'result')} className="vh-btn vh-btn--ghost vh-btn--md">View order photos</Link>
        </aside>
      </div>
    </Page>
  )
}
