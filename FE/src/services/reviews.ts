import { ApiError, api } from './api'

/**
 * The customer's review of a completed order (`/orders/{id}/review`, `BE/app/api/v1/reviews.py`): one per order, 1 to 5 stars,
 * an optional comment (2000 characters) and up to 5 photos. It can be edited until `editable_until` (30 days) unless a
 * Manager hid it. PUT replaces everything, including the photo list.
 */
export interface ReviewPhoto { id: number; path: string; url: string | null }

export interface OrderReview {
  id: number
  orderId: number
  rating: number
  comment: string | null
  photos: ReviewPhoto[]
  hidden: boolean
  createdAt: string
  updatedAt: string
  editableUntil: string
}

interface RawReview {
  id: number; order_id: number; rating: number; comment: string | null; photos: ReviewPhoto[]; hidden: boolean
  created_at: string; updated_at: string; editable_until: string
}

export interface ReviewInput { rating: number; comment?: string | null; photos: string[] }

export const REVIEW_MAX_PHOTOS = 5
export const REVIEW_MAX_MB = 5
export const REVIEW_TYPES = ['image/jpeg', 'image/png']
export const REVIEW_MAX_COMMENT = 2000

const toReview = (r: RawReview): OrderReview => ({
  id: r.id, orderId: r.order_id, rating: r.rating, comment: r.comment, photos: r.photos ?? [], hidden: r.hidden,
  createdAt: r.created_at, updatedAt: r.updated_at, editableUntil: r.editable_until,
})

/** The order's review, or null when the customer has not written one yet (`404 REVIEW_NOT_FOUND`). */
export async function getOrderReview(orderId: number): Promise<OrderReview | null> {
  try {
    return toReview(await api<RawReview>(`/orders/${orderId}/review`))
  } catch (e) {
    if (e instanceof ApiError && e.code === 'REVIEW_NOT_FOUND') return null
    throw e
  }
}

export const createOrderReview = async (orderId: number, body: ReviewInput) =>
  toReview(await api<RawReview>(`/orders/${orderId}/review`, { method: 'POST', body }))

export const updateOrderReview = async (orderId: number, body: ReviewInput) =>
  toReview(await api<RawReview>(`/orders/${orderId}/review`, { method: 'PUT', body }))

/** Asks for a signed link, PUTs the file straight to storage (no token) and returns the `path` to send in `photos`. */
export async function uploadReviewPhoto(orderId: number, file: File): Promise<string> {
  const ticket = await api<{ path: string; upload_url: string; method: string; expires_in: number }>(`/orders/${orderId}/review/photos/upload-url`, {
    method: 'POST', body: { mime_type: file.type, size_bytes: file.size },
  })
  let res: Response
  try {
    res = await fetch(ticket.upload_url, { method: ticket.method || 'PUT', headers: { 'Content-Type': file.type }, body: file })
  } catch (e) {
    throw new ApiError(0, 'NETWORK', e instanceof Error ? e.message : 'Network error')
  }
  if (!res.ok) throw new ApiError(res.status, 'UPLOAD_FAILED', `Upload failed (${res.status})`)
  return ticket.path
}
