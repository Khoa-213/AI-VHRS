import { api } from './api'
import { num, toOrder, type Order, type RawOrder } from './orders'

/**
 * Cancelling after the deposit, refunds and the ETA (contract: `BE/docs/FE_API_GUIDE.md` 7h and 7i).
 * The backend decides every rule and amount; this file only carries them to the screens.
 */

export interface RefundAccount {
  bankName: string
  accountNumber: string
  accountName: string
}

const toRawAccount = (a: RefundAccount) => ({ bank_name: a.bankName, account_number: a.accountNumber, account_name: a.accountName })
const fromRawAccount = (a: { bank_name: string; account_number: string; account_name: string } | null | undefined): RefundAccount | null =>
  a ? { bankName: a.bank_name, accountNumber: a.account_number, accountName: a.account_name } : null

export interface CancelPreview {
  orderId: number
  allowed: boolean
  rule: string | null
  errorCode: string | null
  message: string
  paid: number
  refundAmount: number
  deduction: number
  setupFee: number
  etaPostponedDays: number
  thresholdDays: number
  accountRequired: boolean
}

interface RawPreview {
  order_id: number; allowed: boolean; rule: string | null; error_code: string | null; message: string
  paid: string | number; refund_amount: string | number; deduction: string | number; setup_fee: string | number
  eta_postponed_days: number; threshold_days: number; account_required: boolean
}

const toPreview = (p: RawPreview): CancelPreview => ({
  orderId: p.order_id, allowed: p.allowed, rule: p.rule, errorCode: p.error_code, message: p.message,
  paid: num(p.paid) ?? 0, refundAmount: num(p.refund_amount) ?? 0, deduction: num(p.deduction) ?? 0, setupFee: num(p.setup_fee) ?? 0,
  etaPostponedDays: p.eta_postponed_days, thresholdDays: p.threshold_days, accountRequired: p.account_required,
})

export interface Refund {
  id: number
  orderId: number
  orderCode: string
  amount: number
  gateway: string
  /** PENDING = the workshop has not transferred yet; SUCCESS = transferred. */
  status: string
  createdAt: string
  paidAt: string | null
  kind: 'CANCELLATION' | 'ORPHAN'
  refundOfId: number
  reason: string | null
  rule: string | null
  deduction: number
  /** Masked (last 4 digits) for the customer, in full for the workshop. */
  account: RefundAccount | null
  reference: string | null
  confirmedAt: string | null
}

interface RawRefundInfo {
  kind: 'CANCELLATION' | 'ORPHAN'; refund_of_id: number; reason: string | null; rule: string | null; deduction: number | string
  account: { bank_name: string; account_number: string; account_name: string } | null; reference: string | null; confirmed_at: string | null
}

interface RawRefund {
  id: number; order_id?: number; order_code?: string; amount: string | number; gateway: string; status: string
  created_at: string; paid_at: string | null; refund: RawRefundInfo
}

const toRefund = (r: RawRefund, orderId?: number): Refund => ({
  id: r.id, orderId: r.order_id ?? orderId ?? 0, orderCode: r.order_code ?? '', amount: num(r.amount) ?? 0, gateway: r.gateway,
  status: r.status, createdAt: r.created_at, paidAt: r.paid_at, kind: r.refund.kind, refundOfId: r.refund.refund_of_id,
  reason: r.refund.reason, rule: r.refund.rule, deduction: num(r.refund.deduction) ?? 0, account: fromRawAccount(r.refund.account),
  reference: r.refund.reference, confirmedAt: r.refund.confirmed_at,
})

// ---------- customer ----------

export const cancelPreview = async (orderId: number) => toPreview(await api<RawPreview>(`/orders/${orderId}/cancel-preview`))

/** Cancels after the deposit. `account` is required when the preview says `accountRequired` (payOS deposit). */
export const cancelPaidOrder = async (orderId: number, reason: string, account?: RefundAccount | null): Promise<Order> =>
  toOrder(await api<RawOrder>(`/orders/${orderId}/cancel`, {
    method: 'POST',
    body: { reason, ...(account ? { refund_account: toRawAccount(account) } : {}) },
  }))

/** The refund rows of an order, from `GET /orders/{id}/payments` (rows with `type = REFUND`). */
export async function orderRefunds(orderId: number, workshop = false): Promise<Refund[]> {
  const rows = await api<(RawRefund & { type?: string })[] | { items: (RawRefund & { type?: string })[] }>(
    workshop ? `/workshop/orders/${orderId}/payments` : `/orders/${orderId}/payments`)
  const list = Array.isArray(rows) ? rows : rows.items
  return list.filter((p) => p.type === 'REFUND' && p.refund).map((p) => toRefund(p, orderId))
}

export const setRefundAccount = (orderId: number, refundId: number, account: RefundAccount) =>
  api(`/orders/${orderId}/refunds/${refundId}/account`, { method: 'PUT', body: toRawAccount(account) })

// ---------- workshop ----------

export const workshopCancelPreview = async (orderId: number) => toPreview(await api<RawPreview>(`/workshop/orders/${orderId}/cancel-preview`))

export const workshopCancel = async (orderId: number, reason: string): Promise<Order> =>
  toOrder(await api<RawOrder>(`/workshop/orders/${orderId}/cancel`, { method: 'POST', body: { reason } }))

export interface Orphan {
  paymentId: number
  orderId: number
  orderCode: string
  orderStatus: string
  gateway: string
  types: string[]
  receivedAmount: number
  paymentStatus: string
}

export async function workshopRefunds(status: 'PENDING' | 'SUCCESS'): Promise<{ refunds: Refund[]; orphans: Orphan[] }> {
  const r = await api<{
    refunds: RawRefund[]
    orphans: { payment_id: number; order_id: number; order_code: string; order_status: string; gateway: string; types: string[]; received_amount: number; payment_status: string }[]
  }>(`/workshop/refunds?status=${status}`)
  return {
    refunds: r.refunds.map((x) => toRefund(x)),
    orphans: r.orphans.map((o) => ({
      paymentId: o.payment_id, orderId: o.order_id, orderCode: o.order_code, orderStatus: o.order_status, gateway: o.gateway,
      types: o.types, receivedAmount: o.received_amount, paymentStatus: o.payment_status,
    })),
  }
}

export async function refundOrphan(paymentId: number, body: { reason: string; amount?: number; account?: RefundAccount | null }) {
  return toRefund(await api<RawRefund>(`/workshop/payments/${paymentId}/refund`, {
    method: 'POST',
    body: { reason: body.reason, ...(body.amount ? { amount: body.amount } : {}), ...(body.account ? { refund_account: toRawAccount(body.account) } : {}) },
  }))
}

export async function confirmRefund(refundId: number, body: { reference: string; note?: string; account?: RefundAccount | null }) {
  return toRefund(await api<RawRefund>(`/workshop/refunds/${refundId}/confirm`, {
    method: 'POST',
    body: { reference: body.reference, ...(body.note ? { note: body.note } : {}), ...(body.account ? { refund_account: toRawAccount(body.account) } : {}) },
  }))
}

// ---------- ETA ----------

export interface EtaChange {
  oldEta: string | null
  newEta: string
  reason: string | null
  changedAt: string
  /** Workshop view only: null = the system. */
  actorId: number | null
}

export interface Eta {
  orderId: number
  eta: string | null
  postponedDays: number
  thresholdDays: number
  canCancelFullRefund: boolean
  history: EtaChange[]
  /** Workshop view only: the backend's estimate if confirmed now. */
  suggestedEta: string | null
}

interface RawEta {
  order_id: number; eta: string | null; postponed_days: number; threshold_days: number; can_cancel_full_refund: boolean
  history: { old_eta: string | null; new_eta: string; reason: string | null; changed_at: string; actor_id?: number | null }[]
  suggested_eta?: string | null
}

const toEta = (e: RawEta): Eta => ({
  orderId: e.order_id, eta: e.eta, postponedDays: e.postponed_days, thresholdDays: e.threshold_days, canCancelFullRefund: e.can_cancel_full_refund,
  history: e.history.map((h) => ({ oldEta: h.old_eta, newEta: h.new_eta, reason: h.reason, changedAt: h.changed_at, actorId: h.actor_id ?? null })),
  suggestedEta: e.suggested_eta ?? null,
})

export const getEta = async (orderId: number) => toEta(await api<RawEta>(`/orders/${orderId}/eta`))
export const getWorkshopEta = async (orderId: number) => toEta(await api<RawEta>(`/workshop/orders/${orderId}/eta`))
export const setWorkshopEta = async (orderId: number, eta: string, reason: string) =>
  toEta(await api<RawEta>(`/workshop/orders/${orderId}/eta`, { method: 'POST', body: { eta, reason } }))
