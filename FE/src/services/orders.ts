import { API_BASE, ApiError, api } from './api'

/**
 * Customer side of the order API: catalog, estimate, draft editing, submit,
 * privacy, quotation and the (mock) deposit. Shapes follow the backend
 * (`BE/docs/FE_API_GUIDE.md`, Swagger at /docs). Decimals arrive as strings
 * and are converted to numbers here, once.
 */

// ---------- enums ----------

export type OrderType = 'OT1_COPY_RESTORE' | 'OT2_LEARNED_STYLE' | 'OT3_TEMPLATE'

export type OrderStatus =
  | 'DRAFT'
  | 'SUBMITTED'
  | 'NEED_INFO'
  | 'REJECTED'
  | 'ACCEPTED'
  | 'AWAITING_PRIVACY'
  | 'QUOTED'
  | 'AWAITING_DEPOSIT'
  | 'CONFIRMED'
  | 'AWAITING_ACCEPTANCE'
  | 'AWAITING_FINAL_PAYMENT'
  | 'READY_TO_DELIVER'
  | 'DELIVERING'
  | 'COMPLETED'
  | 'CANCELLED'

export type ProductionStatus =
  | 'NOT_STARTED'
  | 'PENDING_SCHEDULE'
  | 'SCHEDULED'
  | 'PREPARING'
  | 'WRITING'
  | 'PAUSED'
  | 'FAILED'
  | 'WRITTEN'
  | 'PHOTO_UPLOADED'
  | 'REWRITE_REQUIRED'
  | 'FINISHED'

export type InputKind = 'ORIGINAL_IMAGE' | 'HANDWRITING_SAMPLE' | 'TEXT_CONTENT' | 'CANVAS'
export type Alignment = 'LEFT' | 'CENTER' | 'RIGHT' | 'JUSTIFY'
export type Gateway = 'VNPAY' | 'MOMO' | 'PAYOS'

/** Statuses in which the customer can still change the order. */
export const EDITABLE: OrderStatus[] = ['DRAFT', 'NEED_INFO']

/** Statuses that will change by themselves, so the order page keeps asking. */
export const WAITING: OrderStatus[] = ['SUBMITTED', 'ACCEPTED', 'AWAITING_DEPOSIT', 'CONFIRMED']

// ---------- catalog ----------

export interface Paper {
  id: number
  code: string
  name: string
  gsm: number
  surface: string
  size: string
  unitPrice: number
}

export interface Pen {
  id: number
  code: string
  name: string
  category: string
  strokeWidthMm: number
  surcharge: number
}

export interface Ink {
  id: number
  penId: number
  name: string
  hex: string | null
  unitPrice: number
}

export interface Template {
  id: number
  code: string
  name: string
  kind: string
}

export const num = (s: string | number | null | undefined): number | null => (s === null || s === undefined || s === '' ? null : Number(s))

interface RawPaper { id: number; code: string; name: string; gsm: number; surface: string; size: string; unit_price: string }
interface RawPen { id: number; code: string; name: string; category: string; stroke_width_mm: string; surcharge: string }
interface RawInk { id: number; pen_type_id: number; name: string; hex_code: string | null; unit_price: string }
interface RawTemplate { id: number; code: string; name: string; kind: string }

export const getPapers = async (): Promise<Paper[]> =>
  (await api<RawPaper[]>('/catalog/papers', { auth: false })).map((p) => ({ ...p, unitPrice: num(p.unit_price) ?? 0 }))

export const getPens = async (paperId?: number | null): Promise<Pen[]> =>
  (await api<RawPen[]>(`/catalog/pens${paperId ? `?paper_id=${paperId}` : ''}`, { auth: false })).map((p) => ({
    id: p.id, code: p.code, name: p.name, category: p.category,
    strokeWidthMm: num(p.stroke_width_mm) ?? 0, surcharge: num(p.surcharge) ?? 0,
  }))

export const getInks = async (penId: number): Promise<Ink[]> =>
  (await api<RawInk[]>(`/catalog/pens/${penId}/inks`, { auth: false })).map((i) => ({
    id: i.id, penId: i.pen_type_id, name: i.name, hex: i.hex_code, unitPrice: num(i.unit_price) ?? 0,
  }))

export const getTemplates = async (): Promise<Template[]> =>
  (await api<RawTemplate[]>('/catalog/templates', { auth: false })).map((x) => ({ id: x.id, code: x.code, name: x.name, kind: x.kind }))

/** PNG preview of a template with the customer's own words (the endpoint caps the text at 200 characters). */
export const templatePreviewUrl = (id: number, text: string) =>
  `${API_BASE}/catalog/templates/${id}/preview?text=${encodeURIComponent((text.trim() || 'Nét Việt').slice(0, 200))}`

// ---------- estimate ----------

export interface Estimate {
  charsMin: number
  charsMax: number
  priceMin: number
  priceMax: number
  minDepositPct: number
  basis: string
  materialsPriced: boolean
}

interface RawEstimate {
  chars_min: number; chars_max: number; price_min: string; price_max: string
  min_deposit_pct: string; basis: string; materials_priced: boolean
}

export async function estimate(body: {
  order_type: OrderType
  quantity: number
  paper_type_id?: number | null
  pen_type_id?: number | null
  ink_color_id?: number | null
  text?: string | null
  order_id?: number | null
}): Promise<Estimate> {
  const r = await api<RawEstimate>('/pricing/estimate', { method: 'POST', body })
  return {
    charsMin: r.chars_min, charsMax: r.chars_max,
    priceMin: num(r.price_min) ?? 0, priceMax: num(r.price_max) ?? 0,
    minDepositPct: num(r.min_deposit_pct) ?? 50, basis: r.basis, materialsPriced: r.materials_priced,
  }
}

// ---------- orders ----------

export interface Point { x: number; y: number; p: number }
export interface Stroke { points: Point[] }
export interface CanvasData {
  strokes: Stroke[]
  width_mm?: number
  height_mm?: number
}

export interface OrderInput {
  id: number
  kind: InputKind
  sortOrder: number
  mime: string | null
  size: number | null
  /** Quality check of an uploaded photo (set once the upload is confirmed). */
  quality: Record<string, unknown> | null
  rotation: number
  cropBox: Record<string, unknown> | null
  qualityWarning: boolean
  text: string | null
  templateId: number | null
  fontSizeMm: number | null
  alignment: Alignment | null
  canvas: CanvasData | null
  /** Temporary link to the stored file; only the workshop endpoints send it. */
  fileUrl: string | null
}

export interface Order {
  id: number
  code: string
  type: OrderType
  status: OrderStatus
  production: ProductionStatus
  paperId: number | null
  penId: number | null
  inkId: number | null
  workshopSuggest: boolean
  quantity: number
  charCount: number | null
  estMin: number | null
  estMax: number | null
  total: number | null
  depositPct: number | null
  depositAmount: number | null
  note: string | null
  infoRequestNote: string | null
  rejectReason: string | null
  rejectNote: string | null
  eta: string | null
  savedAt: string
  submittedAt: string | null
  createdAt: string
  inputs: OrderInput[]
  warnings: string[]
}

export interface RawInput {
  id: number; kind: InputKind; sort_order: number; mime_type: string | null; file_size_bytes: number | null
  quality_result: Record<string, unknown> | null; is_quality_warning: boolean
  rotation_deg?: number | null; crop_box?: Record<string, unknown> | null
  text_content: string | null; template_id: number | null; font_size_mm: string | null
  alignment: Alignment | null; canvas_data: CanvasData | null; file_url?: string | null
}

export interface RawOrder {
  id: number; code: string; order_type: OrderType; order_status: OrderStatus; production_status: ProductionStatus
  paper_type_id: number | null; pen_type_id: number | null; ink_color_id: number | null
  workshop_suggest_materials: boolean; quantity: number; char_count: number | null
  estimated_price_min: string | null; estimated_price_max: string | null
  total_amount?: string | null; deposit_pct?: string | null; deposit_amount?: string | null
  customer_note: string | null; info_request_note: string | null; reject_reason: string | null; reject_note: string | null
  eta: unknown; last_saved_at: string; submitted_at: string | null; created_at: string
  inputs?: RawInput[]; warnings?: string[]
}

export const toInput = (i: RawInput): OrderInput => ({
  id: i.id, kind: i.kind, sortOrder: i.sort_order, mime: i.mime_type, size: i.file_size_bytes,
  quality: i.quality_result, qualityWarning: i.is_quality_warning, rotation: i.rotation_deg ?? 0, cropBox: i.crop_box ?? null,
  text: i.text_content, templateId: i.template_id, fontSizeMm: num(i.font_size_mm), alignment: i.alignment,
  canvas: i.canvas_data, fileUrl: i.file_url ?? null,
})

export const toOrder = (o: RawOrder): Order => ({
  id: o.id, code: o.code, type: o.order_type, status: o.order_status, production: o.production_status,
  paperId: o.paper_type_id, penId: o.pen_type_id, inkId: o.ink_color_id,
  workshopSuggest: o.workshop_suggest_materials, quantity: o.quantity, charCount: o.char_count,
  estMin: num(o.estimated_price_min), estMax: num(o.estimated_price_max),
  total: num(o.total_amount), depositPct: num(o.deposit_pct), depositAmount: num(o.deposit_amount),
  note: o.customer_note, infoRequestNote: o.info_request_note, rejectReason: o.reject_reason, rejectNote: o.reject_note,
  eta: typeof o.eta === 'string' ? o.eta : null,
  savedAt: o.last_saved_at, submittedAt: o.submitted_at, createdAt: o.created_at,
  inputs: (o.inputs ?? []).map(toInput), warnings: o.warnings ?? [],
})

export interface Page<T> {
  items: T[]
  total: number
  page: number
  pageSize: number
}

/** Every status except DRAFT: what the order history shows. */
export const SENT: OrderStatus[] = [
  'SUBMITTED', 'NEED_INFO', 'REJECTED', 'ACCEPTED', 'AWAITING_PRIVACY', 'QUOTED', 'AWAITING_DEPOSIT', 'CONFIRMED',
  'AWAITING_ACCEPTANCE', 'AWAITING_FINAL_PAYMENT', 'READY_TO_DELIVER', 'DELIVERING', 'COMPLETED', 'CANCELLED',
]

export async function listOrders(opts: { status?: OrderStatus | OrderStatus[]; page?: number; pageSize?: number } = {}): Promise<Page<Order>> {
  const q = new URLSearchParams()
  for (const st of [opts.status ?? []].flat()) q.append('status', st)
  q.set('page', String(opts.page ?? 1))
  q.set('page_size', String(opts.pageSize ?? 20))
  const r = await api<{ items: RawOrder[]; total: number; page: number; page_size: number }>(`/orders?${q}`)
  return { items: r.items.map(toOrder), total: r.total, page: r.page, pageSize: r.page_size }
}

export const getOrder = async (id: number): Promise<Order> => toOrder(await api<RawOrder>(`/orders/${id}`))

export const createOrder = async (type: OrderType, quantity = 1): Promise<Order> =>
  toOrder(await api<RawOrder>('/orders', { method: 'POST', body: { order_type: type, quantity } }))

export interface OrderPatch {
  order_type?: OrderType
  paper_type_id?: number | null
  pen_type_id?: number | null
  ink_color_id?: number | null
  workshop_suggest_materials?: boolean
  quantity?: number
  customer_note?: string | null
}

export const patchOrder = async (id: number, patch: OrderPatch): Promise<Order> =>
  toOrder(await api<RawOrder>(`/orders/${id}`, { method: 'PATCH', body: patch }))

export const deleteOrder = (id: number) => api(`/orders/${id}`, { method: 'DELETE' })

// ---------- inputs ----------

export async function putText(
  id: number,
  body: { text_content: string; template_id?: number | null; font_size_mm?: number | null; alignment?: Alignment | null },
): Promise<OrderInput> {
  return toInput(await api<RawInput>(`/orders/${id}/inputs/text`, { method: 'PUT', body }))
}

export async function putCanvas(id: number, canvas: CanvasData): Promise<OrderInput> {
  return toInput(await api<RawInput>(`/orders/${id}/inputs/canvas`, { method: 'PUT', body: { canvas_data: canvas } }))
}

export const deleteInput = (orderId: number, inputId: number) => api(`/orders/${orderId}/inputs/${inputId}`, { method: 'DELETE' })

export const ACCEPTED_UPLOADS = ['image/jpeg', 'image/png', 'application/pdf']
export const MAX_UPLOAD_MB = 20

/** Three steps: ask for a signed link, PUT the file straight to storage (no token), then confirm. */
export async function uploadOriginal(orderId: number, file: File): Promise<OrderInput> {
  const ticket = await api<{ input_id: number; upload_url: string; method: string }>(`/orders/${orderId}/inputs/upload-url`, {
    method: 'POST',
    body: { kind: 'ORIGINAL_IMAGE', mime_type: file.type, size_bytes: file.size },
  })
  let res: Response
  try {
    res = await fetch(ticket.upload_url, { method: ticket.method || 'PUT', headers: { 'Content-Type': file.type }, body: file })
  } catch (e) {
    throw new ApiError(0, 'NETWORK', e instanceof Error ? e.message : 'Network error')
  }
  if (!res.ok) throw new ApiError(res.status, 'UPLOAD_FAILED', `Upload failed (${res.status})`)
  return toInput(await api<RawInput>(`/orders/${orderId}/inputs/${ticket.input_id}/confirm`, { method: 'POST' }))
}

/** Temporary link (10 minutes) to a stored original. */
export async function getInputFileUrl(orderId: number, inputId: number): Promise<string> {
  const r = await api<{ url?: string; download_url?: string }>(`/orders/${orderId}/inputs/${inputId}/file`)
  return r.url ?? r.download_url ?? ''
}

// ---------- submit, cancel ----------

export const submitOrder = async (id: number): Promise<Order> =>
  toOrder(await api<RawOrder>(`/orders/${id}/submit`, { method: 'POST', body: { terms_accepted: true } }))

export const provideInfo = async (id: number): Promise<Order> =>
  toOrder(await api<RawOrder>(`/orders/${id}/provide-info`, { method: 'POST', body: { terms_accepted: true } }))

export const cancelOrder = async (id: number, reason: string): Promise<Order> =>
  toOrder(await api<RawOrder>(`/orders/${id}/cancel`, { method: 'POST', body: { reason } }))

// ---------- privacy and quotation ----------

export interface PrivacyPolicy {
  version: string
  title: string | null
  body: string
}

export const getPrivacyPolicy = () => api<PrivacyPolicy>('/privacy-policy', { auth: false })

export const decidePrivacy = async (id: number, accept: boolean): Promise<Order> =>
  toOrder(await api<RawOrder>(`/orders/${id}/privacy`, { method: 'POST', body: { accept } }))

export interface QuotationLine {
  option: number
  item: string
  calc: string
  amount: number
}

export interface QuotationOption {
  option: number
  paper: string
  pen: string
  ink: string
  total: number
  minDeposit: number
}

export interface Quotation {
  id: number
  version: number
  status: string
  lines: QuotationLine[]
  options: QuotationOption[]
  chosenOption: number | null
  charCount: number
  quantity: number
  finalTotal: number
  minDepositPct: number
  eta: string | null
  validUntil: string | null
  pdfUrl: string | null
  note: string
  sketch: {
    version: number
    previewUrls: string[]
    approachNote: string | null
    estimatedWritingSec: number | null
    similarity: number | null
  } | null
}

interface RawQuotation {
  id: number; version: number; status: string
  line_items: { option?: number; item?: string; calc?: string; amount?: number | string }[]
  options: { option: number; paper: string; pen: string; ink: string; total: number; min_deposit: number }[]
  chosen_option: number | null; char_count: number; quantity: number
  final_total: string; min_deposit_pct: string; eta: string | null; valid_until: string | null
  pdf_url: string | null; note: string
  sketch: {
    version: number; preview_urls: string[]; approach_note: string | null
    estimated_writing_sec: number | null; similarity_score: string | null
  } | null
}

export async function getQuotation(id: number): Promise<Quotation> {
  const q = await api<RawQuotation>(`/orders/${id}/quotation`)
  return {
    id: q.id, version: q.version, status: q.status,
    lines: q.line_items.map((l) => ({ option: l.option ?? 1, item: l.item ?? '', calc: l.calc ?? '', amount: Number(l.amount ?? 0) })),
    options: q.options.map((o) => ({ option: o.option, paper: o.paper, pen: o.pen, ink: o.ink, total: o.total, minDeposit: o.min_deposit })),
    chosenOption: q.chosen_option, charCount: q.char_count, quantity: q.quantity,
    finalTotal: num(q.final_total) ?? 0, minDepositPct: num(q.min_deposit_pct) ?? 50,
    eta: q.eta, validUntil: q.valid_until, pdfUrl: q.pdf_url, note: q.note,
    sketch: q.sketch && {
      version: q.sketch.version, previewUrls: q.sketch.preview_urls, approachNote: q.sketch.approach_note,
      estimatedWritingSec: q.sketch.estimated_writing_sec, similarity: num(q.sketch.similarity_score),
    },
  }
}

export const requestChanges = async (id: number, note: string): Promise<void> => {
  await api(`/orders/${id}/quotation/request-changes`, { method: 'POST', body: { note } })
}

export const approveQuotation = async (id: number, body: { option?: number; deposit_pct?: number }): Promise<Order> =>
  toOrder(await api<RawOrder>(`/orders/${id}/quotation/approve`, { method: 'POST', body }))

// ---------- deposit ----------

/** `MOCK` moves no money; `SANDBOX` is the gateway's test environment; `LIVE` is real money. */
export type PayMode = 'MOCK' | 'SANDBOX' | 'LIVE'

export interface GatewayInfo {
  gateway: Gateway
  mode: PayMode
  enabled: boolean
}

/** payOS: who receives the transfer and what it must say. */
export interface BankTransfer {
  bin: string | null
  accountNumber: string | null
  accountName: string | null
  amount: number
  content: string | null
}

export interface Payment {
  id: number
  type: string
  amount: number
  status: string
  gateway: Gateway
  mode: PayMode
  /** Money landed on a cancelled payment or with the wrong amount: the workshop has to refund it. */
  needsRefund: boolean
  createdAt: string
  /** SANDBOX / LIVE, while PENDING: the gateway's page the customer is sent to. */
  payUrl: string | null
  payUrlExpiresAt: string | null
  /** payOS, while PENDING: the bank details of the VietQR transfer. */
  bank: BankTransfer | null
}

export interface RawPayment {
  id: number; type?: string; amount: string; status: string; gateway: Gateway; mode?: string
  needs_refund?: boolean; created_at: string; pay_url?: string | null; pay_url_expires_at?: string | null
  bank?: { bin: string | null; account_number: string | null; account_name: string | null; amount: number | string; content: string | null } | null
}

export const toPayment = (p: RawPayment): Payment => ({
  id: p.id, type: p.type ?? 'DEPOSIT', amount: num(p.amount) ?? 0, status: p.status, gateway: p.gateway,
  mode: (p.mode ?? 'MOCK') as PayMode, needsRefund: !!p.needs_refund, createdAt: p.created_at,
  payUrl: p.pay_url ?? null, payUrlExpiresAt: p.pay_url_expires_at ?? null,
  bank: p.bank ? {
    bin: p.bank.bin, accountNumber: p.bank.account_number, accountName: p.bank.account_name,
    amount: num(p.bank.amount) ?? 0, content: p.bank.content,
  } : null,
})

/** Gateways the server can take right now; only `enabled` ones are offered. */
export const getGateways = () => api<GatewayInfo[]>('/payments/gateways')

/** Asks the gateway itself about a PENDING payment when its webhook is late. Not for MOCK payments. */
export const refreshPayment = (paymentId: number) =>
  api<{ result: string; status: string; order_status: OrderStatus | null }>(`/payments/${paymentId}/refresh`, { method: 'POST' })

export const startDeposit = async (id: number, gateway: Gateway): Promise<Payment> =>
  toPayment(await api<RawPayment>(`/orders/${id}/payments/deposit`, { method: 'POST', body: { gateway } }))

export const mockCheckout = (paymentId: number, result: 'SUCCESS' | 'FAILED') =>
  api<{ result: string; status: string; order_status: OrderStatus }>(`/payments/${paymentId}/mock-checkout`, {
    method: 'POST',
    body: { result },
  })

export const listPayments = async (id: number): Promise<Payment[]> => {
  const r = await api<RawPayment[] | { items: RawPayment[] }>(`/orders/${id}/payments`)
  return (Array.isArray(r) ? r : r.items).map(toPayment)
}

// ---------- product photos and acceptance ----------

export type PhotoKind = 'OVERALL' | 'CLOSE_UP' | 'OTHER'
export type RewriteReason = 'WORKSHOP_ERROR' | 'DIFFERS_FROM_SKETCH'

/** Statuses in which the written product has photos the customer can see. */
export const HAS_PRODUCT_PHOTOS: OrderStatus[] = ['AWAITING_ACCEPTANCE', 'AWAITING_FINAL_PAYMENT', 'READY_TO_DELIVER', 'DELIVERING', 'COMPLETED']

export interface ProductPhotos {
  /** QC-passed photos of the latest writing, through signed links that last 30 minutes. */
  photos: { id: number; kind: PhotoKind; url: string | null }[]
  sketchUrl: string | null
  acceptanceDueAt: string | null
  canAccept: boolean
  canRewrite: boolean
}

export async function getProductPhotos(id: number): Promise<ProductPhotos> {
  const r = await api<{
    photos: { id: number; kind: PhotoKind; url: string | null }[]
    sketch_preview_url: string | null; acceptance_due_at: string | null; can_accept: boolean; can_request_rewrite: boolean
  }>(`/orders/${id}/product-photos`)
  return {
    photos: r.photos.map((p) => ({ id: p.id, kind: p.kind, url: p.url })),
    sketchUrl: r.sketch_preview_url, acceptanceDueAt: r.acceptance_due_at, canAccept: r.can_accept, canRewrite: r.can_request_rewrite,
  }
}

export const acceptProduct = async (id: number): Promise<Order> =>
  toOrder(await api<RawOrder>(`/orders/${id}/accept`, { method: 'POST' }))

export const requestRewrite = async (id: number, reason_code: RewriteReason, note: string): Promise<Order> =>
  toOrder(await api<RawOrder>(`/orders/${id}/rewrite`, { method: 'POST', body: { reason_code, note } }))

// ---------- errors ----------

/** Backend error codes that have their own translated text (keys live under `err.`). */
const ERROR_KEYS: Record<string, string> = {
  TIMEOUT: 'auth.err.timeout',
  NETWORK: 'auth.err.network',
  RATE_LIMITED: 'auth.err.rate',
  VALIDATION_ERROR: 'auth.err.validation',
  UPLOAD_FAILED: 'err.uploadFailed',
  ORDER_INCOMPLETE: 'err.incomplete',
  ORDER_NOT_FOUND: 'err.notFound',
  STATE_CONFLICT: 'err.stateConflict',
  ORDER_TYPE_SUSPENDED: 'err.typeSuspended',
  ORDER_TYPE_LOCKED: 'err.typeLocked',
  ORDER_TYPE_HAS_INPUTS: 'err.typeHasInputs',
  ORDER_NOT_EDITABLE: 'err.notEditable',
  ORDER_NOT_DRAFT: 'err.alreadySent',
  ORDER_NOT_NEED_INFO: 'err.notNeedInfo',
  ORDER_IS_DRAFT: 'err.isDraft',
  TERMS_NOT_ACCEPTED: 'err.termsNotAccepted',
  PEN_INCOMPATIBLE: 'err.penIncompatible',
  INK_REQUIRES_PEN: 'err.inkNeedsPen',
  INVALID_PAPER: 'err.invalidPaper',
  INVALID_PEN: 'err.invalidPen',
  INVALID_INK: 'err.invalidInk',
  FILE_TOO_LARGE: 'err.fileTooLarge',
  TOO_MANY_FILES: 'err.tooManyFiles',
  INVALID_FILE: 'err.invalidFile',
  INVALID_IMAGE: 'err.invalidImage',
  INVALID_CROP: 'err.invalidCrop',
  UPLOAD_NOT_FOUND: 'err.uploadNotFound',
  STORAGE_NOT_CONFIGURED: 'err.storage',
  STORAGE_UNAVAILABLE: 'err.storage',
  TEMPLATE_REQUIRED: 'err.templateRequired',
  INVALID_TEMPLATE: 'err.templateInvalid',
  EMPTY_TEXT: 'err.emptyText',
  EMPTY_CANVAS: 'err.emptyCanvas',
  INPUT_KIND_NOT_ALLOWED: 'err.inputKind',
  PRIVACY_REQUIRED: 'err.privacyRequired',
  PRIVACY_NOT_PENDING: 'err.privacyNotPending',
  QUOTATION_NOT_OPEN: 'err.quotationClosed',
  QUOTATION_EXPIRED: 'err.quotationClosed',
  QUOTATION_NOT_FOUND: 'err.quotationNotFound',
  INVALID_DEPOSIT: 'err.invalidDeposit',
  OPTION_REQUIRED: 'err.option',
  INVALID_OPTION: 'err.option',
  NOTE_REQUIRED: 'err.noteRequired',
  DEPOSIT_NOT_EXPECTED: 'err.depositState',
  DEPOSIT_ALREADY_PAID: 'err.depositState',
  GATEWAY_NOT_CONFIGURED: 'err.gatewayOff',
  GATEWAY_UNAVAILABLE: 'err.gatewayDown',
  GATEWAY_REJECTED: 'err.gatewayRejected',
  NOT_A_MOCK_PAYMENT: 'err.notMock',
  ORDER_CANCEL_UNSUPPORTED: 'err.cancelUnsupported',
  FORBIDDEN: 'err.forbidden',
  NOT_AUTHENTICATED: 'err.notSignedIn',
  ORDER_NOT_CLAIMED: 'err.notClaimed',
  ORDER_NOT_SUBMITTED: 'err.notSubmitted',
  ORDER_CLOSED: 'err.orderClosed',
  ALREADY_ASSIGNED: 'err.alreadyAssigned',
  STAFF_REQUIRED: 'err.staffRequired',
  INVALID_STAFF: 'err.invalidStaff',
  ORDER_NOT_ACCEPTED: 'err.notAccepted',
  NO_STROKES_FOUND: 'err.noStrokes',
  IMAGE_TOO_NOISY: 'err.tooNoisy',
  UNSUPPORTED_CHARS: 'err.unsupportedChars',
  TEXT_TOO_LONG: 'err.textTooLong',
  FONT_TOO_LARGE: 'err.fontTooLarge',
  CANVAS_OUT_OF_PAPER: 'err.canvasOut',
  AI_TYPE_UNSUPPORTED: 'err.aiUnsupported',
  SKETCH_REQUIRED: 'err.sketchRequired',
  SKETCH_CHANGED: 'err.sketchChanged',
  QUOTATION_ALREADY_OPEN: 'err.quotationOpen',
  QUOTATION_LOCKED: 'err.quotationLocked',
  QUOTATION_NOT_SENDABLE: 'err.quotationNotSendable',
  OPTIONS_REQUIRED: 'err.optionsRequired',
  MATERIALS_MISSING: 'err.materialsMissing',
  INVALID_MATERIALS: 'err.invalidMaterials',
  REASON_REQUIRED: 'err.reasonRequired',
  INVALID_AMOUNT: 'err.invalidAmount',
  ADJUST_NOT_ALLOWED_MULTI_OPTION: 'err.adjustMulti',
  NOTHING_TO_APPROVE: 'err.nothingToApprove',
  APPROVAL_PENDING: 'err.approvalPending',
  PDF_NOT_AVAILABLE: 'err.pdfMissing',
  PRICING_NOT_CONFIGURED: 'err.pricingMissing',
  EMPTY_MESSAGE: 'err.emptyMessage',
  MESSAGE_TOO_LONG: 'err.messageTooLong',
  TOO_MANY_ATTACHMENTS: 'err.tooManyAttachments',
  INVALID_ATTACHMENT: 'err.invalidAttachment',
  ATTACHMENT_NOT_UPLOADED: 'err.invalidAttachment',
  UNSUPPORTED_FILE: 'err.fileType',
  SLOT_CONFLICT: 'err.slotConflict',
  ROBOT_UNAVAILABLE: 'err.robotUnavailable',
  ROBOT_NOT_SUITABLE: 'err.robotNotSuitable',
  OUTSIDE_WORKING_HOURS: 'err.outsideHours',
  SLOT_IN_PAST: 'err.slotPast',
  JOB_ALREADY_STARTED: 'err.jobStarted',
  STOCK_NEGATIVE: 'err.stockNegative',
  CODE_TAKEN: 'err.codeTaken',
  JOB_NOT_FOUND: 'err.jobNotFound',
  JOB_STATE_CONFLICT: 'err.jobState',
  JOB_NOT_ACTIVE: 'err.jobState',
  ORDER_NOT_ACTIVE: 'err.orderNotActive',
  JOB_NOT_DOWNLOADED: 'err.jobNotDownloaded',
  CALIBRATION_REQUIRED: 'err.calRequired',
  SIMULATION_REQUIRED: 'err.simRequired',
  SIMULATION_FAILED: 'err.simFailed',
  JOB_HASH_MISMATCH: 'err.hashMismatch',
  CHECKLIST_INCOMPLETE: 'err.checklist',
  INVALID_PROBE_POINTS: 'err.probes',
  PROGRESS_REQUIRED: 'err.progress',
  PHOTO_REQUIREMENTS_NOT_MET: 'err.photoReqs',
  INVALID_PHOTO: 'err.photoInvalid',
  INVALID_PHOTO_KEY: 'err.photoInvalid',
  PHOTO_TOO_SMALL: 'err.photoSmall',
  TOO_MANY_PHOTOS: 'err.photoMany',
  QC_NOTE_REQUIRED: 'err.qcNote',
  PHOTO_REMOVED: 'err.photoRemoved',
  PHOTO_NOT_FOUND: 'err.photoGone',
  REWRITE_LIMIT_REACHED: 'err.rewriteLimit',
  ACCEPTANCE_CLOSED: 'err.acceptanceClosed',
  DOWNLOAD_FAILED: 'err.downloadFailed',
  FILE_MISSING: 'err.fileMissing',
}

/**
 * What to show for an error from the API: a translation key when the code has one, otherwise `msg:` plus the
 * backend's own (Vietnamese) message, so a code nobody mapped yet still says something useful. Show it with `errText`.
 */
export function orderErrorKey(e: unknown): string {
  if (!(e instanceof ApiError)) return 'err.unknown'
  const known = ERROR_KEYS[e.code]
  if (known) return known
  if (e.status >= 500) return 'auth.err.server'
  return e.message && e.status >= 400 ? `msg:${e.message}` : 'err.unknown'
}

/** Text for a value from `orderErrorKey` (or any key). */
export const errText = (t: (key: string) => string, key: string): string => (key.startsWith('msg:') ? key.slice(4) : t(key))

/** Field problems of a 422 (`details: [{field, message}]`), as plain lines. */
export function errDetails(e: unknown): string[] {
  if (!(e instanceof ApiError) || !Array.isArray(e.details)) return []
  return (e.details as { field?: string; message?: string }[])
    .map((d) => [d.field, d.message].filter(Boolean).join(': '))
    .filter(Boolean)
}

/** Which part of the form a problem from `ORDER_INCOMPLETE` points at (`details[].field`). */
export function incompleteFields(e: unknown): string[] {
  if (!(e instanceof ApiError) || !Array.isArray(e.details)) return []
  return (e.details as { field?: string }[]).map((d) => d.field ?? '').filter(Boolean)
}

// ---------- photo editing ----------

export interface CropBox {
  x: number
  y: number
  w: number
  h: number
}

/** Rotation (0, 90, 180, 270) and crop (fractions 0 to 1 of the rotated photo) of an uploaded original. The backend checks the photo again. */
export async function editPhoto(
  orderId: number,
  inputId: number,
  patch: { rotation_deg?: 0 | 90 | 180 | 270; crop_box?: CropBox | null },
): Promise<OrderInput> {
  return toInput(await api<RawInput>(`/orders/${orderId}/inputs/${inputId}`, { method: 'PATCH', body: patch }))
}

/** Rotation and crop as the backend stored them in `crop_box` / the input. */
export const cropOf = (i: OrderInput): CropBox | null => {
  const c = i.cropBox
  return c && ['x', 'y', 'w', 'h'].every((k) => typeof c[k] === 'number') ? (c as unknown as CropBox) : null
}
