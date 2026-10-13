import { navigate, orderPath } from '../../router/router'
import { fastForwardCourier, setStatus } from '../../store/store'
import type { Order, OrderStatus } from '../../types'

export const STAGES: OrderStatus[] = ['Sketching', 'Pending', 'Accepted', 'Queued', 'Written', 'Shipped', 'Delivered']

export interface Step {
  /** Simulates the part of the flow that has no customer screen. */
  simulate?: { run: (o: Order) => void }
  go?: { to: (o: Order) => string }
}

export const STEPS: Record<OrderStatus, Step> = {
  Sketching: {
    go: { to: (o) => orderPath(o.id, 'review') },
  },
  Pending: {
    simulate: {
      run: (o) => setStatus(o.id, 'Accepted', { staff: 'Minh · AI-VHRS Studio' }),
    },
    go: { to: (o) => `/staff/review/${encodeURIComponent(o.id)}` },
  },
  Rejected: {
    go: { to: (o) => orderPath(o.id, 'review') },
  },
  Accepted: {
    simulate: {
      run: (o) => setStatus(o.id, 'Queued', { depositMethod: 'Prototype' }),
    },
    go: { to: (o) => orderPath(o.id, 'deposit') },
  },
  Queued: {
    simulate: {
      run: (o) => {
        setStatus(o.id, 'Written', { run: undefined })
        navigate(orderPath(o.id, 'result'))
      },
    },
  },
  Written: {
    go: { to: (o) => orderPath(o.id, 'result') },
  },
  Rewriting: {
    simulate: { run: (o) => setStatus(o.id, 'Written') },
  },
  Shipped: {
    simulate: { run: (o) => fastForwardCourier(o.id) },
    go: { to: (o) => orderPath(o.id, 'tracking') },
  },
  Delivered: {
    go: { to: (o) => orderPath(o.id, 'tracking') },
  },
}
