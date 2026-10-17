import type { Order } from '../../types'
import { PASS_SCORE } from './evaluate'

/** Counts and groups derived from the orders themselves. */

export const PRODUCING: Order['status'][] = ['Queued', 'Rewriting']
export const FINISHED: Order['status'][] = ['Written', 'Shipped', 'Delivered']

export interface Group {
  id: string
  label: string
  note: string
  statuses: Order['status'][]
  /** Opens in the review console. */
  reviewable: boolean
}

export const GROUPS: Group[] = [
  { id: 'review', label: 'Needs review', note: 'Waiting for staff', statuses: ['Pending'], reviewable: true },
  { id: 'accepted', label: 'Accepted', note: 'Waiting for the deposit', statuses: ['Accepted'], reviewable: true },
  { id: 'producing', label: 'In production', note: 'Robot queue', statuses: PRODUCING, reviewable: false },
  { id: 'finished', label: 'Finished', note: 'Written and shipped', statuses: FINISHED, reviewable: false },
  { id: 'rejected', label: 'Rejected', note: 'Sent back to customer', statuses: ['Rejected'], reviewable: true },
]

/** Average score and pass rate over the orders that have been evaluated. Zero orders gives no figures. */
export function qualityStats(orders: Order[]) {
  const scored = orders.filter((o) => typeof o.evalScore === 'number')
  if (!scored.length) return { avg: null, pass: null, scoredCount: 0 }
  const avg = Math.round(scored.reduce((a, o) => a + (o.evalScore ?? 0), 0) / scored.length)
  const pass = Math.round((scored.filter((o) => (o.evalScore ?? 0) >= PASS_SCORE).length / scored.length) * 100)
  return { avg, pass, scoredCount: scored.length }
}

export function reviewTelemetry(orders: Order[]) {
  const count = (s: Order['status']) => orders.filter((o) => o.status === s).length
  const accepted = orders.filter((o) => o.status === 'Accepted' || o.staff)
  const queuedValue = orders
    .filter((o) => ['Pending', 'Accepted', ...PRODUCING].includes(o.status))
    .reduce((a, o) => a + o.total, 0)
  return {
    pending: count('Pending'),
    accepted: count('Accepted'),
    rejected: count('Rejected'),
    producing: orders.filter((o) => PRODUCING.includes(o.status)).length,
    queuedValue,
    acceptedCount: accepted.length,
  }
}
