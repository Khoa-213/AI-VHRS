import { ApiError, api } from './api'
import {
  num, toOrder, toPayment,
  type Order, type OrderStatus, type Page, type Payment, type RawOrder, type RawPayment,
} from './orders'

/**
 * Workshop side: Staff and Manager (`/workshop/*`), Manager only (`/manager/*`), and the order chat shared with the customer.
 * Staff see the orders assigned to them plus the unassigned SUBMITTED pool; a Manager sees every order that is not a draft.
 */

export type Complexity = 'SIMPLE' | 'MEDIUM' | 'COMPLEX'
export type RejectReason = 'TOO_OLD' | 'DAMAGED' | 'MISSING_CONTENT' | 'PROHIBITED_CONTENT' | 'OTHER'
export const REJECT_REASONS: RejectReason[] = ['TOO_OLD', 'DAMAGED', 'MISSING_CONTENT', 'PROHIBITED_CONTENT', 'OTHER']
export const COMPLEXITIES: Complexity[] = ['SIMPLE', 'MEDIUM', 'COMPLEX']

export type QuotationStatus = 'DRAFT' | 'PENDING_APPROVAL' | 'SENT' | 'APPROVED' | 'CHANGES_REQUESTED' | 'EXPIRED' | 'CANCELLED' | 'SUPERSEDED'
export type AdjustmentStatus = 'NONE' | 'WITHIN_THRESHOLD' | 'PENDING_MANAGER' | 'APPROVED' | 'REJECTED'
export type JobStatus = 'SCHEDULED' | 'PREPARING' | 'WRITING' | 'PAUSED' | 'WRITTEN' | 'PHOTO_UPLOADED' | 'DONE' | 'FAILED' | 'REWRITE_REQUIRED' | 'CANCELLED'

// ---------- orders ----------

export interface WorkOrder extends Order {
  customerName: string
  assignedStaffId: number | null
  complexity: Complexity | null
  privacyAcceptedAt: string | null
  finalSketchVersion: number | null
  openQuotationId: number | null
}

interface RawWork extends RawOrder {
  customer_name?: string
  assigned_staff_id?: number | null
  complexity?: Complexity | null
  privacy_accepted_at?: string | null
  final_sketch_version?: number | null
  open_quotation_id?: number | null
}

const toWork = (o: RawWork): WorkOrder => ({
  ...toOrder(o),
  customerName: o.customer_name ?? '',
  assignedStaffId: o.assigned_staff_id ?? null,
  complexity: o.complexity ?? null,
  privacyAcceptedAt: o.privacy_accepted_at ?? null,
  finalSketchVersion: o.final_sketch_version ?? null,
  openQuotationId: o.open_quotation_id ?? null,
})

export interface WorkQuery {
  status?: OrderStatus | OrderStatus[]
  q?: string
  orderType?: string
  unassigned?: boolean
  page?: number
  pageSize?: number
}

export async function listWork(opts: WorkQuery = {}): Promise<Page<WorkOrder>> {
  const q = new URLSearchParams()
  for (const st of [opts.status ?? []].flat()) q.append('status', st)
  if (opts.q?.trim()) q.set('q', opts.q.trim())
  if (opts.orderType) q.set('order_type', opts.orderType)
  if (opts.unassigned) q.set('unassigned', 'true')
  q.set('page', String(opts.page ?? 1))
  q.set('page_size', String(opts.pageSize ?? 50))
  const r = await api<{ items: RawWork[]; total: number; page: number; page_size: number }>(`/workshop/orders?${q}`)
  return { items: r.items.map(toWork), total: r.total, page: r.page, pageSize: r.page_size }
}

export const getWork = async (id: number): Promise<WorkOrder> => toWork(await api<RawWork>(`/workshop/orders/${id}`))

export const claimOrder = async (id: number) => toWork(await api<RawWork>(`/workshop/orders/${id}/claim`, { method: 'POST' }))

/** `staffId` is only for a Manager acting on an order nobody has claimed yet. */
export const acceptOrder = async (id: number, staffId?: number) =>
  toWork(await api<RawWork>(`/workshop/orders/${id}/accept`, { method: 'POST', body: staffId ? { staff_id: staffId } : {} }))

export const rejectOrder = async (id: number, reason: RejectReason, note: string, staffId?: number) =>
  toWork(await api<RawWork>(`/workshop/orders/${id}/reject`, {
    method: 'POST',
    body: { reason, note: note.trim() || null, ...(staffId ? { staff_id: staffId } : {}) },
  }))

export const requestInfo = async (id: number, note: string, staffId?: number) =>
  toWork(await api<RawWork>(`/workshop/orders/${id}/request-info`, {
    method: 'POST',
    body: { note, ...(staffId ? { staff_id: staffId } : {}) },
  }))

// ---------- sketches ----------

export interface Sketch {
  id: number
  version: number
  similarity: number | null
  complexity: Complexity | null
  writingSec: number | null
  strokeMm: number | null
  penLifts: number | null
  note: string | null
  isFinal: boolean
  createdAt: string
  /** Temporary links (10 minutes) to a PNG per page. */
  previewUrls: string[]
  warnings: string[]
}

interface RawSketch {
  id: number; version: number; similarity_score: string | null; suggested_complexity: Complexity | null
  estimated_writing_sec: number | null; total_stroke_mm: string | null; pen_lift_count: number | null
  approach_note: string | null; is_final: boolean; created_at: string; preview_urls?: string[]; warnings?: string[]
}

const toSketch = (s: RawSketch): Sketch => ({
  id: s.id, version: s.version, similarity: num(s.similarity_score), complexity: s.suggested_complexity,
  writingSec: s.estimated_writing_sec, strokeMm: num(s.total_stroke_mm), penLifts: s.pen_lift_count,
  note: s.approach_note, isFinal: s.is_final, createdAt: s.created_at, previewUrls: s.preview_urls ?? [], warnings: s.warnings ?? [],
})

export const listSketches = async (orderId: number) => (await api<RawSketch[]>(`/workshop/orders/${orderId}/sketches`)).map(toSketch)

export const getSketch = async (orderId: number, version: number) => toSketch(await api<RawSketch>(`/workshop/orders/${orderId}/sketches/${version}`))

export const generateSketch = async (orderId: number, body: { paper_size?: 'A6' | 'A5' | 'A4'; approach_note?: string; seed?: number }) =>
  toSketch(await api<RawSketch>(`/workshop/orders/${orderId}/sketches/generate`, { method: 'POST', body }))

export const patchSketch = async (orderId: number, version: number, body: { approach_note?: string | null; suggested_complexity?: Complexity | null }) =>
  toSketch(await api<RawSketch>(`/workshop/orders/${orderId}/sketches/${version}`, { method: 'PATCH', body }))

/** The full pen path of a version (`vhrs-trajectory/1`, millimetres), to download or check. */
export const sketchTrajectory = async (orderId: number, version: number): Promise<unknown> =>
  (await api<{ trajectory: unknown }>(`/workshop/orders/${orderId}/sketches/${version}`)).trajectory

/** Saves a hand-made or edited trajectory as a new version (the only way to sketch a learned-handwriting order). */
export const uploadTrajectory = async (orderId: number, trajectory: unknown, note?: string) =>
  toSketch(await api<RawSketch>(`/workshop/orders/${orderId}/sketches`, {
    method: 'POST',
    body: { trajectory, ...(note?.trim() ? { approach_note: note.trim() } : {}) },
  }))

export const finalizeSketch = async (orderId: number, version: number) =>
  toSketch(await api<RawSketch>(`/workshop/orders/${orderId}/sketches/${version}/finalize`, { method: 'POST' }))

// ---------- quotations ----------

export interface WorkQuotation {
  id: number
  version: number
  sketchId: number
  status: QuotationStatus
  adjustment: AdjustmentStatus
  lines: { option: number; item: string; calc: string; amount: number }[]
  options: { option: number; paper: string; pen: string; ink: string; total: number; minDeposit: number }[]
  chosenOption: number | null
  charCount: number
  quantity: number
  complexity: Complexity
  computedTotal: number
  adjustedTotal: number | null
  adjustmentPct: number | null
  adjustmentReason: string | null
  finalTotal: number
  minDepositPct: number
  eta: string | null
  sentAt: string | null
  validUntil: string | null
  hasPdf: boolean
  createdAt: string
}

interface RawWorkQuotation {
  id: number; version: number; sketch_id: number; status: QuotationStatus; adjustment_status: AdjustmentStatus
  line_items: { option?: number; item?: string; calc?: string; amount?: number | string }[]
  options?: { option: number; paper: string; pen: string; ink: string; total: number; min_deposit: number }[]
  chosen_option: number | null; char_count: number; quantity: number; complexity: Complexity
  computed_total: string; adjusted_total: string | null; adjustment_pct: string | null; adjustment_reason: string | null
  final_total: string; min_deposit_pct: string; eta: string | null; sent_at: string | null; valid_until: string | null
  has_pdf?: boolean; created_at: string
}

const toQuotation = (q: RawWorkQuotation): WorkQuotation => ({
  id: q.id, version: q.version, sketchId: q.sketch_id, status: q.status, adjustment: q.adjustment_status,
  lines: q.line_items.map((l) => ({ option: l.option ?? 1, item: l.item ?? '', calc: l.calc ?? '', amount: Number(l.amount ?? 0) })),
  options: (q.options ?? []).map((o) => ({ option: o.option, paper: o.paper, pen: o.pen, ink: o.ink, total: o.total, minDeposit: o.min_deposit })),
  chosenOption: q.chosen_option, charCount: q.char_count, quantity: q.quantity, complexity: q.complexity,
  computedTotal: num(q.computed_total) ?? 0, adjustedTotal: num(q.adjusted_total), adjustmentPct: num(q.adjustment_pct),
  adjustmentReason: q.adjustment_reason, finalTotal: num(q.final_total) ?? 0, minDepositPct: num(q.min_deposit_pct) ?? 50,
  eta: q.eta, sentAt: q.sent_at, validUntil: q.valid_until, hasPdf: !!q.has_pdf, createdAt: q.created_at,
})

export const listQuotations = async (orderId: number) =>
  (await api<RawWorkQuotation[]>(`/workshop/orders/${orderId}/quotations`)).map(toQuotation)

export interface MaterialOption {
  paper_type_id: number
  pen_type_id: number
  ink_color_id: number
}

export const createQuotation = async (orderId: number, body: { complexity?: Complexity; char_count?: number; options?: MaterialOption[]; eta?: string }) =>
  toQuotation(await api<RawWorkQuotation>(`/workshop/orders/${orderId}/quotations`, { method: 'POST', body }))

export const adjustQuotation = async (id: number, adjustedTotal: number, reason: string) =>
  toQuotation(await api<RawWorkQuotation>(`/workshop/quotations/${id}/adjustment`, { method: 'PUT', body: { adjusted_total: adjustedTotal, reason } }))

export const clearAdjustment = async (id: number) =>
  toQuotation(await api<RawWorkQuotation>(`/workshop/quotations/${id}/adjustment`, { method: 'DELETE' }))

export const sendQuotation = async (id: number) =>
  toQuotation(await api<RawWorkQuotation>(`/workshop/quotations/${id}/send`, { method: 'POST' }))

export const cancelQuotation = async (id: number) =>
  toQuotation(await api<RawWorkQuotation>(`/workshop/quotations/${id}/cancel`, { method: 'POST' }))

export const quotationPdf = async (id: number) => (await api<{ url: string }>(`/workshop/quotations/${id}/pdf`)).url

// ---------- read-only extras of an order ----------

export const orderPayments = async (orderId: number): Promise<Payment[]> =>
  (await api<RawPayment[]>(`/workshop/orders/${orderId}/payments`)).map(toPayment)

export interface Job {
  id: number
  orderId: number
  orderCode: string
  robotId: number
  robotCode: string
  technicianId: number
  technicianName: string
  status: JobStatus
  isRewrite: boolean
  slotStart: string
  slotEnd: string
  durationMin: number
}

interface RawJob {
  id: number; order_id: number; order_code?: string; robot_id: number; robot_code?: string; technician_id: number
  technician_name?: string; status: JobStatus; is_rewrite: boolean; slot_start: string; slot_end: string
  estimated_duration_min: number
}

const toJob = (j: RawJob): Job => ({
  id: j.id, orderId: j.order_id, orderCode: j.order_code ?? '', robotId: j.robot_id, robotCode: j.robot_code ?? '',
  technicianId: j.technician_id, technicianName: j.technician_name ?? '', status: j.status, isRewrite: j.is_rewrite,
  slotStart: j.slot_start, slotEnd: j.slot_end, durationMin: j.estimated_duration_min,
})

export const orderJobs = async (orderId: number) => (await api<RawJob[]>(`/workshop/orders/${orderId}/jobs`)).map(toJob)

// ---------- manager ----------

export interface StaffBrief {
  id: number
  fullName: string
  email: string
  openOrders: number
}

export const getStaffDirectory = async (): Promise<StaffBrief[]> =>
  (await api<{ id: number; full_name: string; email: string; open_orders: number }[]>('/manager/staff')).map((s) => ({
    id: s.id, fullName: s.full_name, email: s.email, openOrders: s.open_orders,
  }))

export const assignStaff = async (orderId: number, staffId: number) =>
  toWork(await api<RawWork>(`/manager/orders/${orderId}/assignment`, { method: 'PUT', body: { staff_id: staffId } }))

export async function pendingApprovals(page = 1): Promise<Page<WorkQuotation & { orderId: number }>> {
  const r = await api<{ items: (RawWorkQuotation & { order_id: number })[]; total: number; page: number; page_size: number }>(
    `/manager/quotations/pending-approval?page=${page}&page_size=50`,
  )
  return { items: r.items.map((q) => ({ ...toQuotation(q), orderId: q.order_id })), total: r.total, page: r.page, pageSize: r.page_size }
}

export const approveAdjustment = async (id: number) =>
  toQuotation(await api<RawWorkQuotation>(`/manager/quotations/${id}/approve-adjustment`, { method: 'POST' }))

export const rejectAdjustment = async (id: number, reason: string) =>
  toQuotation(await api<RawWorkQuotation>(`/manager/quotations/${id}/reject-adjustment`, { method: 'POST', body: { reason } }))

export interface QueueRow {
  orderId: number
  code: string
  customerName: string
  type: string
  quantity: number
  eta: string | null
  production: string
  confirmedAt: string | null
  durationMin: number | null
}

export async function scheduleQueue(page = 1): Promise<Page<QueueRow>> {
  const r = await api<{
    items: {
      order_id: number; code: string; customer_name: string; order_type: string; quantity: number; eta: string | null
      production_status: string; confirmed_at: string | null; duration_min: number | null
    }[]
    total: number; page: number; page_size: number
  }>(`/manager/schedule/queue?page=${page}&page_size=50`)
  return {
    items: r.items.map((x) => ({
      orderId: x.order_id, code: x.code, customerName: x.customer_name, type: x.order_type, quantity: x.quantity, eta: x.eta,
      production: x.production_status, confirmedAt: x.confirmed_at, durationMin: x.duration_min,
    })),
    total: r.total, page: r.page, pageSize: r.page_size,
  }
}

export interface Suggestion {
  robotId: number
  robotCode: string
  isSimulated: boolean
  technicianId: number
  technicianName: string
  slotStart: string
  slotEnd: string
  finishBy: string
  etaRisk: boolean
}

export interface SuggestionSet {
  durationMin: number
  writingSecPerCopy: number
  quantity: number
  eta: string | null
  stockWarnings: string[]
  suggestions: Suggestion[]
}

export async function scheduleSuggestion(orderId: number): Promise<SuggestionSet> {
  const r = await api<{
    duration_min: number; writing_sec_per_copy: number; quantity: number; eta: string | null; stock_warnings: string[]
    suggestions: {
      robot_id: number; robot_code: string; is_simulated: boolean; technician_id: number; technician_name: string
      slot_start: string; slot_end: string; finish_by: string; eta_risk: boolean
    }[]
  }>(`/manager/orders/${orderId}/schedule-suggestion`)
  return {
    durationMin: r.duration_min, writingSecPerCopy: r.writing_sec_per_copy, quantity: r.quantity, eta: r.eta,
    stockWarnings: r.stock_warnings,
    suggestions: r.suggestions.map((s) => ({
      robotId: s.robot_id, robotCode: s.robot_code, isSimulated: s.is_simulated, technicianId: s.technician_id,
      technicianName: s.technician_name, slotStart: s.slot_start, slotEnd: s.slot_end, finishBy: s.finish_by, etaRisk: s.eta_risk,
    })),
  }
}

export const scheduleOrder = async (orderId: number, body: { robot_id: number; technician_id: number; slot_start: string; note?: string }) =>
  toJob(await api<RawJob>(`/manager/orders/${orderId}/schedule`, { method: 'POST', body }))

export const unscheduleJob = async (jobId: number, reason: string) =>
  toJob(await api<RawJob>(`/manager/jobs/${jobId}/unschedule`, { method: 'POST', body: { reason } }))

export const rescheduleJob = async (jobId: number, body: { robot_id?: number; technician_id?: number; slot_start?: string; reason: string }) =>
  toJob(await api<RawJob>(`/manager/jobs/${jobId}/reschedule`, { method: 'POST', body }))

export async function listJobs(opts: { status?: JobStatus[]; page?: number } = {}): Promise<Page<Job>> {
  const q = new URLSearchParams()
  for (const st of opts.status ?? []) q.append('status', st)
  q.set('page', String(opts.page ?? 1))
  q.set('page_size', '50')
  const r = await api<{ items: RawJob[]; total: number; page: number; page_size: number }>(`/manager/jobs?${q}`)
  return { items: r.items.map(toJob), total: r.total, page: r.page, pageSize: r.page_size }
}

// ---------- chat (customer and workshop share these) ----------

export interface Message {
  id: number
  mine: boolean
  body: string | null
  attachments: { url: string; mime: string }[]
  readAt: string | null
  createdAt: string
}

export interface MessagePage {
  items: Message[]
  total: number
  unread: number
}

interface RawMessage {
  id: number; mine: boolean; body: string | null; attachments: { url: string; mime: string }[]
  read_at: string | null; created_at: string
}

const toMessage = (m: RawMessage): Message => ({
  id: m.id, mine: m.mine, body: m.body, attachments: m.attachments, readAt: m.read_at, createdAt: m.created_at,
})

export const CHAT_IMAGES = ['image/jpeg', 'image/png']
export const CHAT_MAX_MB = 5

export async function listMessages(orderId: number): Promise<MessagePage> {
  const r = await api<{ items: RawMessage[]; total: number; unread: number }>(`/orders/${orderId}/messages?page=1&page_size=100`)
  // The API answers newest first or oldest first depending on the page; a chat reads oldest to newest.
  return { items: r.items.map(toMessage).sort((a, b) => a.createdAt.localeCompare(b.createdAt) || a.id - b.id), total: r.total, unread: r.unread }
}

export async function sendMessage(orderId: number, body: string, image?: File): Promise<Message> {
  let attachments: { path: string }[] | undefined
  if (image) {
    const t = await api<{ path: string; upload_url: string; method: string }>(`/orders/${orderId}/messages/upload-url`, {
      method: 'POST',
      body: { mime_type: image.type, size_bytes: image.size },
    })
    const res = await fetch(t.upload_url, { method: t.method || 'PUT', headers: { 'Content-Type': image.type }, body: image })
    if (!res.ok) throw new ApiError(res.status, 'UPLOAD_FAILED', 'Upload failed')
    attachments = [{ path: t.path }]
  }
  return toMessage(await api<RawMessage>(`/orders/${orderId}/messages`, {
    method: 'POST',
    body: { body: body.trim() || null, ...(attachments ? { attachments } : {}) },
  }))
}

export const markMessagesRead = (orderId: number) => api(`/orders/${orderId}/messages/read`, { method: 'POST' })

export interface Robot {
  id: number
  code: string
  station: string | null
  status: 'AVAILABLE' | 'BUSY' | 'MAINTENANCE' | 'BROKEN'
  isSimulated: boolean
  penCategories: string[]
}

export const listRobots = async (): Promise<Robot[]> =>
  (await api<{ id: number; code: string; station: string | null; status: Robot['status']; is_simulated: boolean; supported_pen_categories: string[] | null }[]>('/manager/robots')).map((r) => ({
    id: r.id, code: r.code, station: r.station, status: r.status, isSimulated: r.is_simulated, penCategories: r.supported_pen_categories ?? [],
  }))

export interface Technician {
  id: number
  fullName: string
  email: string
  activeJobs: number
}

export const listTechnicians = async (): Promise<Technician[]> =>
  (await api<{ id: number; full_name: string; email: string; active_jobs: number }[]>('/manager/technicians')).map((x) => ({
    id: x.id, fullName: x.full_name, email: x.email, activeJobs: x.active_jobs,
  }))
