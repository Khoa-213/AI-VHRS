import type { Order } from '../../types'
import { hashOf, PASS_SCORE } from './evaluate'

/**
 * Stand-in for the robot controller and the AI services. Counts that can be
 * derived from orders are derived (pending, accepted, revenue, scores). The
 * rest is deterministic per day, so the dashboard looks the same on reload.
 */

const dayKey = () => new Date().toISOString().slice(0, 10)
const jitter = (seed: string, min: number, span: number) => min + (hashOf(dayKey() + seed) % span)

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

export function robotTelemetry(orders: Order[]) {
  const job = orders.find((o) => o.status === 'Queued')
  const progress = job ? 20 + (hashOf(job.id) % 60) : 0
  const jobMinutes = job ? (job.spec.mins || 4) * (job.spec.qty || 1) : 0
  const writing = jobMinutes ? Math.min(jobMinutes, 240) : 0
  const minutes = {
    writing: jitter('write', 150, 90) + Math.round(writing / 4),
    idle: jitter('idle', 120, 80),
    calibrating: jitter('cal', 12, 18),
  }
  return {
    state: job ? 'Writing' : 'Idle',
    job,
    progress,
    minutesLeft: job ? Math.max(1, Math.round(jobMinutes * (1 - progress / 100))) : 0,
    minutes,
    piecesToday: jitter('pieces', 24, 30) + orders.filter((o) => FINISHED.includes(o.status)).length,
    consumables: [
      { k: 'Ink', v: jitter('ink', 55, 35) },
      { k: 'Paper tray', v: jitter('paper', 40, 50) },
      { k: 'Nib wear', v: jitter('nib', 10, 40) },
    ],
  }
}

export function aiTelemetry(orders: Order[]) {
  const scored = orders.filter((o) => typeof o.evalScore === 'number')
  const avg = scored.length ? Math.round(scored.reduce((a, o) => a + (o.evalScore ?? 0), 0) / scored.length) : 91
  const pass = scored.length ? Math.round((scored.filter((o) => (o.evalScore ?? 0) >= PASS_SCORE).length / scored.length) * 100) : 94
  const services = [
    { k: 'Handwriting OCR', v: jitter('ocr', 60, 60) },
    { k: 'Stroke vectorization', v: jitter('vec', 70, 60) },
    { k: 'Trajectory planning', v: jitter('traj', 55, 50) },
    { k: 'Quality evaluation', v: jitter('eval', 50, 50) },
  ]
  const week = Array.from({ length: 7 }, (_, i) => 40 + (hashOf('w' + i + dayKey()) % 70))
  const total = services.reduce((a, s) => a + s.v, 0)
  week[6] = total
  return { avg, pass, services, total, week, scoredCount: scored.length }
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
