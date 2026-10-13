import { navigate, orderPath } from '../../router/router'
import { fastForwardCourier, setStatus } from '../../store/store'
import type { Order, OrderStatus } from '../../types'

export const STAGES: OrderStatus[] = ['Sketching', 'Pending', 'Accepted', 'Queued', 'Written', 'Shipped', 'Delivered']

export interface Step {
  /** What the customer does next, or what is being waited on. */
  hint: string
  /** Simulates the part of the flow that has no customer screen. */
  simulate?: { label: string; run: (o: Order) => void }
  go?: { label: string; to: (o: Order) => string }
}

export const STEPS: Record<OrderStatus, Step> = {
  Sketching: {
    hint: 'Customer: review the AI sketch and send it to staff.',
    go: { label: 'Open sketch review', to: (o) => orderPath(o.id, 'review') },
  },
  Pending: {
    hint: 'Waiting for staff. Review it in the staff console, or accept it from here.',
    simulate: {
      label: 'Staff accepts sketch',
      run: (o) => setStatus(o.id, 'Accepted', { staff: 'Minh · AI-VHRS Studio' }),
    },
    go: { label: 'Open staff console', to: (o) => `/staff/review/${encodeURIComponent(o.id)}` },
  },
  Rejected: {
    hint: 'Staff rejected the input. The customer sees the reasons and can start again.',
    go: { label: 'Open order', to: (o) => orderPath(o.id, 'review') },
  },
  Accepted: {
    hint: 'Customer: pay the 30% deposit.',
    simulate: {
      label: 'Customer pays deposit',
      run: (o) => setStatus(o.id, 'Queued', { depositMethod: 'Prototype' }),
    },
    go: { label: 'Open deposit', to: (o) => orderPath(o.id, 'deposit') },
  },
  Queued: {
    hint: 'In the robot queue. The FR3 is writing.',
    simulate: {
      label: 'Robot finished writing',
      run: (o) => {
        setStatus(o.id, 'Written', { run: undefined })
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
    hint: 'Staff packs and books GHN, then the courier delivers. Follow it on the tracking page.',
    simulate: { label: 'Courier delivers', run: (o) => fastForwardCourier(o.id) },
    go: { label: 'Open tracking', to: (o) => orderPath(o.id, 'tracking') },
  },
  Delivered: {
    hint: 'Done. Start another order to run the flow again.',
    go: { label: 'Open tracking', to: (o) => orderPath(o.id, 'tracking') },
  },
}
