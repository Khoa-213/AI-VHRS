import { useEffect, useRef, useState } from 'react'
import Page from '../../components/layout/Page'
import { NoOrder } from '../../components/ui/OrderParts'
import PaperSheet from '../../components/ui/PaperSheet'
import PaymentMethods, { EMPTY_CARD, methodReady, type CardFields } from '../../components/ui/PaymentMethods'
import { PAY_METHODS } from '../../constants/catalog'
import { Link, orderPath } from '../../router/router'
import { setStatus, useOrder } from '../../store/store'
import { depositOf, fmt } from '../../utils/format'
import './order.css'

export default function Deposit({ id }: { id: string | null }) {
  const order = useOrder(id)
  const [method, setMethod] = useState<string | null>(null)
  const [card, setCard] = useState<CardFields>(EMPTY_CARD)
  const [busy, setBusy] = useState(false)
  const timer = useRef<number | undefined>(undefined)
  useEffect(() => () => window.clearTimeout(timer.current), [])

  if (!order) return <NoOrder label="Deposit" />

  const paid = !['Accepted', 'Pending', 'Sketching'].includes(order.status)
  const deposit = depositOf(order.total)
  const m = PAY_METHODS.find((x) => x.id === (paid ? order.depositMethod : method))
  const ready = methodReady(method, card)

  const pay = () => {
    if (!ready || busy) return
    setBusy(true)
    timer.current = window.setTimeout(() => {
      setStatus(order.id, 'Queued', { depositMethod: method ?? undefined })
      setBusy(false)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    }, 1400)
  }

  const payLabel = busy
    ? 'Processing…'
    : !m ? 'Select a method'
    : m.kind === 'qr' ? `I’ve transferred ${fmt(deposit)}`
    : `Pay ${fmt(deposit)}${m.kind === 'wallet' ? ` with ${m.name}` : ''}`

  return (
    <Page label="Deposit" width={1200}>
      <div className="ov">
      <div className="vh-head-text">
        <span className="vh-eyebrow">Order {order.id} · Accepted by staff</span>
        <h1 className="vh-h1">{paid ? 'You’re in the queue.' : 'Pay your deposit.'}</h1>
      </div>

      <div className="vh-cols">
        <section className="vh-col vh-panel" style={{ flex: '999 1 520px' }}>
          {!paid ? (
            <>
              <div className="vh-stack">
                <h2 className="vh-h2">Choose a payment method</h2>
                <p className="vh-lede">Pay 30% now to lock your slot in the robot queue. The rest is due on delivery.</p>
              </div>
              <PaymentMethods
                method={method}
                onPick={setMethod}
                card={card}
                onCard={setCard}
                orderId={order.id}
                noteSuffix="COC"
                amountLabel={fmt(deposit)}
              />
              <button className="vh-btn vh-btn--primary" disabled={!ready || busy} onClick={pay}>{payLabel}</button>
              <span className="vh-fine">Deposit is fully refundable until writing starts.</span>
            </>
          ) : (
            <div className="pay-done">
              <span className="pay-done-icon">
                <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M20 6 9 17l-5-5" />
                </svg>
              </span>
              <h2>Deposit received.</h2>
              <p>
                {fmt(deposit)} paid via {m?.name ?? 'your chosen method'}. Order {order.id} is now queued for the FR3. We’ll notify you when writing starts.
              </p>
              <div className="pay-done-actions">
                <Link to={orderPath(order.id, 'review')} className="vh-btn vh-btn--white vh-btn--md">View order</Link>
                <Link to="/" className="vh-btn vh-btn--ghost vh-btn--md">Back to home</Link>
              </div>
            </div>
          )}
        </section>

        <aside className="vh-aside" style={{ flex: '1 1 320px' }}>
          <div className="pay-preview">
            <PaperSheet spec={order.spec} height={order.spec.land ? '50%' : '86%'} maxWidth="88%" shadow="0 14px 24px var(--sh-5)" />
          </div>
          <div className="ov-rail-body">
          <span className="ov-rail-title">{order.title}</span>
          <div className="vh-rows">
            <div className="vh-row vh-row--mono"><span style={{ fontFamily: 'inherit' }}>Order total</span><span>{fmt(order.total)}</span></div>
            <div className="vh-row vh-row--mono"><span style={{ fontFamily: 'inherit' }}>Due on delivery</span><span>{fmt(order.total - deposit)}</span></div>
          </div>
          <div className="vh-total-row">
            <span>Deposit (30%)</span>
            <span>{fmt(deposit)}</span>
          </div>
          </div>
        </aside>
      </div>
      </div>
    </Page>
  )
}
