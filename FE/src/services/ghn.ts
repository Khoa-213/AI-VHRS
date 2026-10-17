import type { GhnStatus, Order, ShipLog, Shipment } from '../types'

/**
 * GHN (Giao Hàng Nhanh) shipping layer.
 *
 * The GHN token must never reach the browser, and GHN does not allow browser
 * calls (CORS), so the real integration is: backend books the order and
 * receives GHN's status webhook, then exposes two endpoints to this app:
 *
 *   POST {VITE_GHN_PROXY}/shipments            body { orderId, to, weightG, codAmount }
 *   GET  {VITE_GHN_PROXY}/shipments/{code}     -> { log: [{ status, updated_date }] }
 *
 * Without VITE_GHN_PROXY booking is refused. Everything GHN-shaped is normalised
 * in this file only.
 */

const BASE: string | undefined = import.meta.env.VITE_GHN_PROXY || undefined
export const GHN_LIVE = !!BASE

// ---------- packing ----------

export const PACK_STEPS = [{ id: 'wrap' }, { id: 'box' }, { id: 'label' }] as const

// ---------- status table ----------

/** Customer-facing stepper. Packing happens before GHN, the rest follows GHN scans. Labels are `phase.<i>`. */
export const PHASES = [0, 1, 2, 3, 4] as const

export type Tone = 'neutral' | 'good' | 'warn' | 'bad'

interface StatusMeta {
  /** Index into PHASES this status belongs to. */
  phase: number
  tone: Tone
}

export const GHN_STATUS: Record<GhnStatus, StatusMeta> = {
  ready_to_pick: { phase: 1, tone: 'neutral' },
  picking: { phase: 1, tone: 'neutral' },
  picked: { phase: 2, tone: 'good' },
  storing: { phase: 2, tone: 'neutral' },
  transporting: { phase: 2, tone: 'neutral' },
  sorting: { phase: 2, tone: 'neutral' },
  delivering: { phase: 3, tone: 'good' },
  delivered: { phase: 4, tone: 'good' },
  delivery_fail: { phase: 3, tone: 'bad' },
  waiting_to_return: { phase: 3, tone: 'bad' },
  return: { phase: 3, tone: 'bad' },
  return_transporting: { phase: 3, tone: 'bad' },
  return_sorting: { phase: 3, tone: 'bad' },
  returning: { phase: 3, tone: 'bad' },
  returned: { phase: 3, tone: 'bad' },
  cancel: { phase: 1, tone: 'bad' },
  exception: { phase: 2, tone: 'warn' },
  damage: { phase: 2, tone: 'bad' },
  lost: { phase: 2, tone: 'bad' },
}

export const toneColor: Record<Tone, string> = {
  neutral: 'var(--t3)',
  good: 'var(--good)',
  warn: 'var(--warn)',
  bad: 'var(--danger)',
}

const FINAL: GhnStatus[] = ['delivered', 'returned', 'cancel', 'lost', 'damage']
export const isFinal = (s: GhnStatus) => FINAL.includes(s)

// ---------- reading a shipment ----------

export const emptyShipment = (order: Order): Shipment => ({
  pack: [],
  weightG: Math.max(150, 120 + (order.spec.qty || 1) * 15),
  codAmount: 0,
  logs: [],
})

export const shipmentOf = (order: Order): Shipment => order.shipment ?? emptyShipment(order)

export const lastLog = (s: Shipment): ShipLog | undefined => s.logs[s.logs.length - 1]

export const packed = (s: Shipment) => PACK_STEPS.every((p) => s.pack.some((m) => m.id === p.id))

export type Stage = 'pack' | 'book' | 'courier' | 'done' | 'problem'

/** Where a shipped order is, from staff's point of view. */
export function stageOf(order: Order): Stage {
  const s = shipmentOf(order)
  const last = lastLog(s)
  if (last?.status === 'delivered' || (!s.ghnCode && order.status === 'Delivered')) return 'done'
  if (last && GHN_STATUS[last.status].tone === 'bad') return 'problem'
  if (s.ghnCode) return 'courier'
  return packed(s) ? 'book' : 'pack'
}

/** Translation key and colour for an order's shipping state, as staff read it. */
export function stageChip(order: Order): { key: string; color: string } {
  const stage = stageOf(order)
  const last = lastLog(shipmentOf(order))
  if (stage === 'pack') return { key: 'stage.pack', color: 'var(--warn)' }
  if (stage === 'book') return { key: 'stage.book', color: 'var(--accent-text)' }
  if (stage === 'done') return { key: 'stage.done', color: 'var(--good)' }
  if (last) return { key: `ghn.${last.status}.staff`, color: toneColor[GHN_STATUS[last.status].tone] }
  return { key: 'stage.booked', color: 'var(--t3)' }
}

/** Index into PHASES for the stepper. */
export function phaseOf(order: Order): number {
  const stage = stageOf(order)
  if (stage === 'done') return PHASES.length - 1
  if (stage === 'pack' || stage === 'book') return 0
  const last = lastLog(shipmentOf(order))
  return last ? GHN_STATUS[last.status].phase : 1
}

export const trackingUrl = (code: string) => `https://donhang.ghn.vn/?order_code=${encodeURIComponent(code)}`

// ---------- booking and tracking ----------

export interface Booking {
  code: string
  fee: number
  expectedAt: string
}

const DAY = 864e5

/** Books a GHN order for a packed parcel. */
export async function bookShipment(order: Order, weightG: number): Promise<Booking> {
  if (!BASE) throw new Error('GHN is not configured (VITE_GHN_PROXY)')
  const res = await fetch(`${BASE}/shipments`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ orderId: order.id, to: order.shipTo, weightG, codAmount: 0 }),
  })
  if (!res.ok) throw new Error(`GHN booking failed (${res.status})`)
  const d = (await res.json()) as { order_code: string; total_fee?: number; expected_delivery_time?: string }
  return {
    code: d.order_code,
    fee: d.total_fee ?? 0,
    expectedAt: d.expected_delivery_time ?? new Date(Date.now() + 3 * DAY).toISOString(),
  }
}

/** Every scan GHN has for a code, oldest first. */
export async function fetchLogs(code: string): Promise<ShipLog[]> {
  if (!BASE) return []
  const res = await fetch(`${BASE}/shipments/${encodeURIComponent(code)}`)
  if (!res.ok) throw new Error(`GHN tracking failed (${res.status})`)
  const d = (await res.json()) as { log?: { status: string; updated_date: string; warehouse?: string }[] }
  return (d.log ?? [])
    .filter((l) => l.status in GHN_STATUS)
    .map((l) => ({ status: l.status as GhnStatus, at: new Date(l.updated_date).toISOString(), place: l.warehouse }))
    .sort((a, b) => a.at.localeCompare(b.at))
}
