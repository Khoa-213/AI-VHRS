import type { OrderStatus } from '../services/orders'

/** Text colour of the status chip, as theme tokens. */
export const STATUS_COLOR: Record<OrderStatus, string> = {
  DRAFT: 'var(--st-sketch)',
  SUBMITTED: 'var(--st-pending)',
  NEED_INFO: 'var(--warn)',
  REJECTED: 'var(--danger)',
  ACCEPTED: 'var(--st-accepted)',
  AWAITING_PRIVACY: 'var(--st-pending)',
  QUOTED: 'var(--st-accepted)',
  AWAITING_DEPOSIT: 'var(--st-accepted)',
  CONFIRMED: 'var(--st-queued)',
  AWAITING_ACCEPTANCE: 'var(--st-written)',
  AWAITING_FINAL_PAYMENT: 'var(--st-written)',
  READY_TO_DELIVER: 'var(--st-written)',
  DELIVERING: 'var(--st-pending)',
  COMPLETED: 'var(--st-written)',
  CANCELLED: 'var(--danger)',
}

/** Index into the five order steps (`os.step.0` to `os.step.4`) a status belongs to. */
export const STATUS_STEP: Record<OrderStatus, number> = {
  DRAFT: 0,
  SUBMITTED: 1,
  NEED_INFO: 1,
  REJECTED: 1,
  ACCEPTED: 2,
  AWAITING_PRIVACY: 2,
  QUOTED: 2,
  AWAITING_DEPOSIT: 3,
  CONFIRMED: 4,
  AWAITING_ACCEPTANCE: 4,
  AWAITING_FINAL_PAYMENT: 4,
  READY_TO_DELIVER: 4,
  DELIVERING: 4,
  COMPLETED: 4,
  CANCELLED: 0,
}

export const STEP_KEYS = ['os.step.0', 'os.step.1', 'os.step.2', 'os.step.3', 'os.step.4']

/** Where a customer's order opens from a list. */
export const orderLink = (id: number, status: OrderStatus): string =>
  status === 'DRAFT' ? `/create-order/draft/${id}` : status === 'AWAITING_DEPOSIT' ? `/orders/${id}/deposit` : `/orders/${id}/review`
