import { api } from './api'

export type ShipmentStatus = 'CREATED' | 'PICKED_UP' | 'DELIVERING' | 'DELIVERED' | 'FAILED' | 'RETURNED' | 'CANCELLED'
export interface Shipment {
  id: number
  order_id: number
  carrier: string
  service_code: string | null
  waybill_code: string | null
  status: ShipmentStatus
  fee: string | number
  eta: string | null
  picked_up_at: string | null
  delivered_at: string | null
  mode: string
  tracking_url: string | null
  created_at: string
}
export interface StaffShipment extends Shipment {
  package_type: string | null
  weight_g: number | null
  is_fallback_fee: boolean
  carrier_status_raw: string | null
  to_address: Record<string, unknown>
  label_link: string | null
  created_by: number | null
}

// Mirrors the carrier's accepted transitions; the backend remains authoritative.
export const MOCK_MOVES: Record<ShipmentStatus, ShipmentStatus[]> = {
  CREATED: ['PICKED_UP', 'DELIVERING', 'DELIVERED', 'FAILED', 'RETURNED', 'CANCELLED'],
  PICKED_UP: ['DELIVERING', 'DELIVERED', 'FAILED', 'RETURNED'],
  DELIVERING: ['DELIVERED', 'FAILED', 'RETURNED'],
  FAILED: ['DELIVERING', 'DELIVERED', 'RETURNED'],
  DELIVERED: [], RETURNED: [], CANCELLED: [],
}
export const ACTIVE_SHIPMENTS: ShipmentStatus[] = ['CREATED', 'PICKED_UP', 'DELIVERING']
export const workshopShipments = (id: number) => api<StaffShipment[]>(`/workshop/orders/${id}/shipment`)
export const customerShipments = (id: number) => api<Shipment[]>(`/orders/${id}/shipment`)
export const createShipment = (id: number, note: string) => api<StaffShipment>(`/workshop/orders/${id}/shipment`, {
  method: 'POST', body: { note: note.trim() || null },
})
export const cancelShipment = (id: number, reason: string) => api<StaffShipment>(`/workshop/shipments/${id}/cancel`, {
  method: 'POST', body: { reason: reason.trim() },
})
export const mockShipmentEvent = (id: number, status: ShipmentStatus, reason: string) =>
  api<{ result: string; status: string; order_status?: string }>(`/workshop/shipments/${id}/mock-event`, {
    method: 'POST', body: { status, reason: reason.trim() || null },
  })
export const confirmPickup = (id: number, phone: string) => api(`/workshop/orders/${id}/pickup/confirm`, {
  method: 'POST', body: { phone: phone.trim() },
})
export const confirmReceipt = (id: number) => api(`/orders/${id}/receipt`, { method: 'POST' })

export const addressLine = (a: Record<string, unknown> | null | undefined) =>
  ['street', 'ward_name', 'district_name', 'province_name'].map((k) => a?.[k]).filter(Boolean).join(', ')

/** Only links supplied by the API, with a web protocol, may leave the application. */
export function webLink(value: string | null): string | undefined {
  if (!value) return undefined
  try { const u = new URL(value); return ['https:', 'http:'].includes(u.protocol) ? u.href : undefined } catch { return undefined }
}
