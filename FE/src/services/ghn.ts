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
 * Without VITE_GHN_PROXY the layer runs a scripted courier so the whole flow
 * can be demoed. Everything GHN-shaped is normalised in this file only.
 */

const BASE: string | undefined = import.meta.env.VITE_GHN_PROXY || undefined
export const GHN_LIVE = !!BASE

// ---------- packing ----------

export const PACK_STEPS = [
  { id: 'wrap', label: 'Piece wrapped in tissue and card backing' },
  { id: 'box', label: 'Boxed and sealed' },
  { id: 'label', label: 'Shipping label printed and attached' },
] as const

// ---------- status table ----------

/** Customer-facing stepper. Packing happens before GHN, the rest follows GHN scans. */
export const PHASES = ['Packing', 'Pickup', 'In transit', 'Out for delivery', 'Delivered'] as const

export type Tone = 'neutral' | 'good' | 'warn' | 'bad'

interface StatusMeta {
  /** GHN wording, for staff. */
  staff: string
  /** Plain wording, for the customer. */
  customer: string
  /** Index into PHASES this status belongs to. */
  phase: number
  tone: Tone
}

export const GHN_STATUS: Record<GhnStatus, StatusMeta> = {
  ready_to_pick: { staff: 'Waiting for pickup', customer: 'GHN has your parcel booked and will collect it from the studio', phase: 1, tone: 'neutral' },
  picking: { staff: 'Courier is picking up', customer: 'A GHN courier is on the way to the studio', phase: 1, tone: 'neutral' },
  picked: { staff: 'Picked up', customer: 'Collected from the studio by GHN', phase: 2, tone: 'good' },
  storing: { staff: 'Stored at hub', customer: 'Arrived at a GHN hub', phase: 2, tone: 'neutral' },
  transporting: { staff: 'In transit', customer: 'On its way between GHN hubs', phase: 2, tone: 'neutral' },
  sorting: { staff: 'Sorting', customer: 'Being sorted at the hub nearest you', phase: 2, tone: 'neutral' },
  delivering: { staff: 'Out for delivery', customer: 'Out for delivery today. Keep your phone close', phase: 3, tone: 'good' },
  delivered: { staff: 'Delivered', customer: 'Delivered to you', phase: 4, tone: 'good' },
  delivery_fail: { staff: 'Delivery failed', customer: 'The courier could not reach you. GHN will try again', phase: 3, tone: 'bad' },
  waiting_to_return: { staff: 'Waiting to return', customer: 'Delivery was not possible. The parcel is waiting to go back to the studio', phase: 3, tone: 'bad' },
  return: { staff: 'Return started', customer: 'The parcel is being sent back to the studio', phase: 3, tone: 'bad' },
  return_transporting: { staff: 'Return in transit', customer: 'The parcel is on its way back to the studio', phase: 3, tone: 'bad' },
  return_sorting: { staff: 'Return sorting', customer: 'The parcel is being sorted for return', phase: 3, tone: 'bad' },
  returning: { staff: 'Returning', customer: 'The parcel is almost back at the studio', phase: 3, tone: 'bad' },
  returned: { staff: 'Returned to studio', customer: 'The parcel is back at the studio. We will contact you', phase: 3, tone: 'bad' },
  cancel: { staff: 'Cancelled', customer: 'This shipment was cancelled. The studio will contact you', phase: 1, tone: 'bad' },
  exception: { staff: 'Exception', customer: 'GHN reported a problem with this parcel. The studio is looking into it', phase: 2, tone: 'warn' },
  damage: { staff: 'Damaged', customer: 'The parcel was damaged on the way. The studio will contact you', phase: 2, tone: 'bad' },
  lost: { staff: 'Lost', customer: 'GHN lost this parcel. The studio will contact you', phase: 2, tone: 'bad' },
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

/** Label and colour for an order's shipping state, as staff read it. */
export function stageChip(order: Order): { label: string; color: string } {
  const stage = stageOf(order)
  const last = lastLog(shipmentOf(order))
  if (stage === 'pack') return { label: 'Needs packing', color: 'var(--warn)' }
  if (stage === 'book') return { label: 'Ready to book', color: 'var(--accent-text)' }
  if (stage === 'done') return { label: 'Delivered', color: 'var(--good)' }
  if (last) return { label: GHN_STATUS[last.status].staff, color: toneColor[GHN_STATUS[last.status].tone] }
  return { label: 'Booked', color: 'var(--t3)' }
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

const sleep = (ms: number) => new Promise((r) => window.setTimeout(r, ms))
const DAY = 864e5

function mockCode() {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
  return Array.from({ length: 8 }, () => chars[Math.floor(Math.random() * chars.length)]).join('')
}

/** Books a GHN order for a packed parcel. */
export async function bookShipment(order: Order, weightG: number): Promise<Booking> {
  if (BASE) {
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
  await sleep(700)
  return { code: mockCode(), fee: 22000 + Math.round(weightG / 500) * 5000, expectedAt: new Date(Date.now() + 3 * DAY).toISOString() }
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

// ---------- scripted courier (prototype only) ----------

const SCRIPT: GhnStatus[] = ['ready_to_pick', 'picking', 'picked', 'storing', 'transporting', 'sorting', 'delivering', 'delivered']

function placeFor(status: GhnStatus, city: string): string | undefined {
  switch (status) {
    case 'picking':
    case 'picked':
      return 'Bưu cục Bến Thành, TP. Hồ Chí Minh'
    case 'storing':
      return 'Kho trung chuyển Bình Tân'
    case 'transporting':
      return 'Tuyến liên tỉnh'
    case 'sorting':
      return `Kho phân loại ${city}`
    case 'delivering':
    case 'delivered':
      return `Bưu cục ${city}`
    default:
      return undefined
  }
}

/** The next scan the scripted courier would report, or null when it is done. */
export function nextMockLog(logs: ShipLog[], city: string, at = new Date()): ShipLog | null {
  const last = logs[logs.length - 1]
  const i = last ? SCRIPT.indexOf(last.status) : -1
  const status = SCRIPT[i + 1]
  return status ? { status, at: at.toISOString(), place: placeFor(status, city) } : null
}

/** Scans up to and including `through`, spaced 5 hours apart ending at `end`. Used for sample orders. */
export function scriptedLogs(through: GhnStatus, end: Date, city: string): ShipLog[] {
  const n = SCRIPT.indexOf(through) + 1
  return SCRIPT.slice(0, n).map((status, i) => ({
    status,
    at: new Date(end.getTime() - (n - 1 - i) * 5 * 36e5).toISOString(),
    place: placeFor(status, city),
  }))
}
