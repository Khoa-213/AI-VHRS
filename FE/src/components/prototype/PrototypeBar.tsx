import { useState } from 'react'
import { ORDER_HREF } from '../../constants'
import { STATUS_COLORS } from '../../constants/catalog'
import { Link, navigate, orderPath, usePath } from '../../router/router'
import { resetDemo, setPrototypeMode, setStatus, useOrders, usePrototypeMode } from '../../store/store'
import type { Order, OrderStatus } from '../../types'

const STAGES: OrderStatus[] = ['Sketching', 'Pending', 'Accepted', 'Queued', 'Written', 'Shipped', 'Delivered']

interface Step {
  /** What the customer does next, or what is being waited on. */
  hint: string
  /** Simulates the part of the flow that has no customer screen. */
  simulate?: { label: string; run: (o: Order) => void }
  go?: { label: string; to: (o: Order) => string }
}

const STEPS: Record<OrderStatus, Step> = {
  Sketching: {
    hint: 'Customer: review the AI sketch and send it to staff.',
    go: { label: 'Open sketch review', to: (o) => orderPath(o.id, 'review') },
  },
  Pending: {
    hint: 'Waiting for staff to check the sketch.',
    simulate: {
      label: 'Staff accepts sketch',
      run: (o) => setStatus(o.id, 'Accepted', { staff: 'Minh · AI-VHRS Studio' }),
    },
  },
  Accepted: {
    hint: 'Customer: pay the 30% deposit.',
    go: { label: 'Open deposit', to: (o) => orderPath(o.id, 'deposit') },
  },
  Queued: {
    hint: 'In the robot queue. The FR3 is writing.',
    simulate: {
      label: 'Robot finished writing',
      run: (o) => {
        setStatus(o.id, 'Written')
        navigate(orderPath(o.id, 'result'))
      },
    },
  },
  Written: {
    hint: 'Customer: check the photos, approve or ask for a rewrite.',
    go: { label: 'Open result photos', to: (o) => orderPath(o.id, 'result') },
  },
  Rewriting: {
    hint: 'The arm is writing a fresh copy.',
    simulate: { label: 'New rewrite photos arrive', run: (o) => setStatus(o.id, 'Written') },
  },
  Shipped: {
    hint: 'On its way to the customer.',
    simulate: { label: 'Courier delivers', run: (o) => setStatus(o.id, 'Delivered') },
  },
  Delivered: {
    hint: 'Done. Start another order to run the flow again.',
    go: { label: 'Create another order', to: () => ORDER_HREF },
  },
}

/** Floating control strip that stands in for staff, the robot and the courier. */
export default function PrototypeBar() {
  const on = usePrototypeMode()
  const orders = useOrders()
  const path = usePath()
  const [open, setOpen] = useState(true)

  if (!on) {
    return (
      <button className="vh-proto-chip vh-proto-chip--off" onClick={() => setPrototypeMode(true)}>
        Prototype off · turn on
      </button>
    )
  }

  const idInPath = /^\/orders\/([^/]+)\//.exec(path)?.[1]
  const order = orders.find((o) => o.id === (idInPath && decodeURIComponent(idInPath))) ?? orders[0]

  if (!open) {
    return (
      <button className="vh-proto-chip" onClick={() => setOpen(true)}>
        <span className="vh-proto-dot" /> Prototype
      </button>
    )
  }

  const step = order ? STEPS[order.status] : undefined
  const stageIdx = order ? STAGES.indexOf(order.status === 'Rewriting' ? 'Written' : order.status) : -1
  const [color, bg] = order ? STATUS_COLORS[order.status] : ['#fff', 'transparent']

  return (
    <aside className="vh-proto" aria-label="Prototype controls">
      <div className="vh-proto-top">
        <span className="vh-proto-label"><span className="vh-proto-dot" /> Prototype mode</span>
        <div className="vh-proto-tools">
          <Link to="/" className="vh-proto-link">Landing</Link>
          <Link to={ORDER_HREF} className="vh-proto-link">New order</Link>
          <Link to="/cart" className="vh-proto-link">Cart</Link>
          <button className="vh-proto-link" onClick={resetDemo}>Reset data</button>
          <button className="vh-proto-link" onClick={() => setOpen(false)} aria-label="Collapse">Hide</button>
          <button className="vh-proto-link" onClick={() => setPrototypeMode(false)}>Turn off</button>
        </div>
      </div>

      {order && step ? (
        <div className="vh-proto-body">
          <div className="vh-proto-order">
            <span className="vh-mono">{order.id}</span>
            <span className="vh-chip" style={{ color, background: bg }}>{order.status}</span>
          </div>
          <ol className="vh-proto-stages" aria-label="Order progress">
            {STAGES.map((s, i) => (
              <li key={s} className={i < stageIdx ? 'done' : i === stageIdx ? 'now' : ''} title={s} />
            ))}
          </ol>
          <span className="vh-proto-hint">{step.hint}</span>
          <div className="vh-proto-actions">
            {step.simulate && (
              <button className="vh-btn vh-btn--primary vh-btn--sm" onClick={() => step.simulate!.run(order)}>
                {step.simulate.label}
              </button>
            )}
            {step.go && (
              <Link to={step.go.to(order)} className="vh-btn vh-btn--white vh-btn--sm">
                {step.go.label} →
              </Link>
            )}
          </div>
        </div>
      ) : (
        <div className="vh-proto-body">
          <span className="vh-proto-hint">No orders yet. Create one to run the flow.</span>
          <Link to={ORDER_HREF} className="vh-btn vh-btn--white vh-btn--sm">Create order →</Link>
        </div>
      )}
    </aside>
  )
}
