import { API_BASE, ApiError, api, getTokens } from './api'
import type { Alignment } from './orders'

/**
 * Customer studio (U5): a draft that comes before an order, with undo and redo, a server preview, a check that runs the
 * workshop's own stroke engine, and an AI assistant. Shapes follow `BE/app/api/v1/studio.py` and section 7q of
 * `BE/docs/FE_API_GUIDE.md`. Decimals arrive as strings and are converted here.
 */

export type StudioMode = 'TEXT' | 'RESTORE'
export type DraftStatus = 'OPEN' | 'SUBMITTED' | 'ABANDONED'
export type RestorationMode = 'FAITHFUL' | 'ASSISTED'

export interface StudioImage {
  id: string
  /** The backend stores more while it analyses the photo; only the keys the UI reads are named. */
  rotation_deg?: number
  mime_type?: string
  [key: string]: unknown
}

/** `content` of a revision. Keys come from `empty_content` in `BE/app/services/studio.py`. */
export interface StudioContent {
  order_type: string
  quantity: number
  text: string
  template_id: number | null
  font_size_mm: number | null
  alignment: Alignment | null
  layout: Record<string, unknown> | null
  canvas: Record<string, unknown> | null
  paper_type_id: number | null
  pen_type_id: number | null
  ink_color_id: number | null
  workshop_suggest_materials: boolean
  physical_watermark: boolean
  restoration_mode: RestorationMode | null
  customer_note: string | null
  images: StudioImage[]
}

export interface Problem { field: string; code: string; message: string }

export interface StudioEstimate {
  charsMin: number
  charsMax: number
  priceMin: number
  priceMax: number
  basis: string
  materialsPriced: boolean
}

export interface Draft {
  id: number
  mode: StudioMode
  status: DraftStatus
  title: string | null
  orderId: number | null
  revisionId: number
  revisionSeq: number
  content: StudioContent
  canUndo: boolean
  canRedo: boolean
  ready: boolean
  problems: Problem[]
  estimate: StudioEstimate | null
  warnings: string[]
  createdAt: string
  updatedAt: string
  submittedAt: string | null
}

export interface DraftListItem {
  id: number
  mode: StudioMode
  status: DraftStatus
  title: string | null
  orderId: number | null
  updatedAt: string
}

export interface Revision {
  id: number
  seq: number
  parentId: number | null
  author: 'CUSTOMER' | 'AI'
  toolName: string | null
  note: string | null
  isCurrent: boolean
  createdAt: string
}

export interface Check {
  ready: boolean
  problems: Problem[]
  estimate: StudioEstimate | null
  pages: number | null
}

/** Fields of `PATCH /studio/{id}`: send only what changed, `null` clears a value. */
export interface DraftPatch {
  title?: string | null
  text?: string
  template_id?: number | null
  font_size_mm?: number | null
  alignment?: Alignment | null
  layout?: Record<string, unknown> | null
  canvas?: Record<string, unknown> | null
  paper_type_id?: number | null
  pen_type_id?: number | null
  ink_color_id?: number | null
  workshop_suggest_materials?: boolean
  quantity?: number
  physical_watermark?: boolean
  restoration_mode?: RestorationMode | null
  customer_note?: string | null
}

/** An action that answers with the updated draft. */
export type DraftCall = () => Promise<Draft>

interface RawEstimate {
  chars_min: number; chars_max: number; price_min: string; price_max: string; basis: string; materials_priced: boolean
}
interface RawDraft {
  id: number; mode: StudioMode; status: DraftStatus; title: string | null; order_id: number | null
  revision_id: number; revision_seq: number; content: StudioContent; can_undo: boolean; can_redo: boolean
  ready: boolean; problems: Problem[]; estimate: RawEstimate | null; warnings?: string[]
  created_at: string; updated_at: string; submitted_at: string | null
}
interface RawCheck { ready: boolean; problems: Problem[]; estimate: RawEstimate | null; pages: number | null }

const toEstimate = (e: RawEstimate | null): StudioEstimate | null => e && {
  charsMin: e.chars_min, charsMax: e.chars_max, priceMin: Number(e.price_min), priceMax: Number(e.price_max),
  basis: e.basis, materialsPriced: e.materials_priced,
}

export const toDraft = (d: RawDraft): Draft => ({
  id: d.id, mode: d.mode, status: d.status, title: d.title, orderId: d.order_id, revisionId: d.revision_id,
  revisionSeq: d.revision_seq, content: { ...d.content, images: d.content.images ?? [] }, canUndo: d.can_undo, canRedo: d.can_redo,
  ready: d.ready, problems: d.problems ?? [], estimate: toEstimate(d.estimate), warnings: d.warnings ?? [],
  createdAt: d.created_at, updatedAt: d.updated_at, submittedAt: d.submitted_at,
})

// ---------- drafts ----------

export const createDraft = async (mode: StudioMode, title?: string): Promise<Draft> =>
  toDraft(await api<RawDraft>('/studio', { method: 'POST', body: { mode, title: title || null } }))

export async function listDrafts(status?: DraftStatus): Promise<DraftListItem[]> {
  const rows = await api<{ id: number; mode: StudioMode; status: DraftStatus; title: string | null; order_id: number | null; updated_at: string }[]>(
    `/studio${status ? `?status=${status}` : ''}`)
  return rows.map((r) => ({ id: r.id, mode: r.mode, status: r.status, title: r.title, orderId: r.order_id, updatedAt: r.updated_at }))
}

export const getDraft = async (id: number): Promise<Draft> => toDraft(await api<RawDraft>(`/studio/${id}`))

export const patchDraft = async (id: number, patch: DraftPatch): Promise<Draft> =>
  toDraft(await api<RawDraft>(`/studio/${id}`, { method: 'PATCH', body: patch }))

export const undoDraft = async (id: number): Promise<Draft> => toDraft(await api<RawDraft>(`/studio/${id}/undo`, { method: 'POST' }))
export const redoDraft = async (id: number): Promise<Draft> => toDraft(await api<RawDraft>(`/studio/${id}/redo`, { method: 'POST' }))

export async function getRevisions(id: number): Promise<Revision[]> {
  const rows = await api<{ id: number; seq: number; parent_id: number | null; author: 'CUSTOMER' | 'AI'; tool_name: string | null; note: string | null; is_current: boolean; created_at: string }[]>(
    `/studio/${id}/revisions`)
  return rows.map((r) => ({
    id: r.id, seq: r.seq, parentId: r.parent_id, author: r.author, toolName: r.tool_name, note: r.note,
    isCurrent: r.is_current, createdAt: r.created_at,
  }))
}

/** Full check with the workshop's stroke engine (30 per minute). */
export async function checkDraft(id: number): Promise<Check> {
  const c = await api<RawCheck>(`/studio/${id}/check`, { method: 'POST' })
  return { ready: c.ready, problems: c.problems ?? [], estimate: toEstimate(c.estimate), pages: c.pages }
}

/** One page as a JPEG (30 per minute). The endpoint needs the Bearer header, so it is fetched, not used as an `<img src>`. */
export async function fetchDraftPreview(id: number, page: number, signal?: AbortSignal): Promise<Blob> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}/studio/${id}/preview?page=${page}`, {
      signal, headers: { Authorization: `Bearer ${getTokens()?.access ?? ''}` },
    })
  } catch (e) {
    if (signal?.aborted) throw e
    throw new ApiError(0, 'NETWORK', e instanceof Error ? e.message : 'Network error')
  }
  if (!res.ok) {
    let code = `HTTP_${res.status}`
    let message = res.statusText
    try {
      const body = (await res.json()) as { error?: { code?: string; message?: string } }
      code = body.error?.code ?? code
      message = body.error?.message ?? message
    } catch {
      // Not JSON: keep the status text.
    }
    throw new ApiError(res.status, code, message)
  }
  return res.blob()
}

export const abandonDraft = (id: number) => api(`/studio/${id}`, { method: 'DELETE' })

export const submitDraft = (id: number, body: { terms_accepted: boolean; confirm_right_to_use: boolean }) =>
  api<{ draft_id: number; order_id: number }>(`/studio/${id}/submit`, { method: 'POST', body })

// ---------- original photos (RESTORE) ----------

export const STUDIO_UPLOADS = ['image/jpeg', 'image/png', 'application/pdf']

/** Signed link, PUT straight to storage, then confirm (the backend checks the real file type and quality). */
export async function uploadDraftImage(id: number, file: File): Promise<Draft> {
  const ticket = await api<{ image_id: string; upload_url: string; method: string }>(`/studio/${id}/images/upload-url`, {
    method: 'POST', body: { mime_type: file.type, size_bytes: file.size },
  })
  let res: Response
  try {
    res = await fetch(ticket.upload_url, { method: ticket.method || 'PUT', headers: { 'Content-Type': file.type }, body: file })
  } catch (e) {
    throw new ApiError(0, 'NETWORK', e instanceof Error ? e.message : 'Network error')
  }
  if (!res.ok) throw new ApiError(res.status, 'UPLOAD_FAILED', `Upload failed (${res.status})`)
  return toDraft(await api<RawDraft>(`/studio/${id}/images/confirm`, { method: 'POST', body: { image_id: ticket.image_id } }))
}

export const rotateDraftImage = async (id: number, imageId: string, rotation: 0 | 90 | 180 | 270): Promise<Draft> =>
  toDraft(await api<RawDraft>(`/studio/${id}/images/${imageId}`, { method: 'PATCH', body: { rotation_deg: rotation } }))

export const removeDraftImage = async (id: number, imageId: string): Promise<Draft> =>
  toDraft(await api<RawDraft>(`/studio/${id}/images/${imageId}`, { method: 'DELETE' }))

// ---------- assistant ----------

export interface AssistantStatus {
  enabled: boolean
  available: boolean
  providers: string[]
  messagesLeftToday: number
  dailyMessageLimit: number
  sendsPhotos: boolean
}

export interface ChatMessage {
  id: number
  role: string
  content: string
  status: string
  provider: string | null
  model: string | null
  toolCalls: { name: string; ok: boolean; revisionId: number | null }[]
  createdAt: string
}

interface RawMessage {
  id: number; role: string; content: string; status: string; provider: string | null; model: string | null
  tool_calls?: { name: string; ok: boolean; revision_id: number | null }[]; created_at: string
}
const toMessage = (m: RawMessage): ChatMessage => ({
  id: m.id, role: m.role, content: m.content, status: m.status, provider: m.provider, model: m.model,
  toolCalls: (m.tool_calls ?? []).map((c) => ({ name: c.name, ok: c.ok, revisionId: c.revision_id })), createdAt: m.created_at,
})

export async function getAssistantStatus(): Promise<AssistantStatus> {
  const s = await api<{ enabled: boolean; available: boolean; providers: string[]; messages_left_today: number; daily_message_limit: number; sends_photos: boolean }>(
    '/studio/assistant/status')
  return {
    enabled: s.enabled, available: s.available, providers: s.providers, messagesLeftToday: s.messages_left_today,
    dailyMessageLimit: s.daily_message_limit, sendsPhotos: s.sends_photos,
  }
}

export const getDraftMessages = async (id: number): Promise<ChatMessage[]> =>
  (await api<RawMessage[]>(`/studio/${id}/messages`)).map(toMessage)

export async function sendDraftMessage(id: number, text: string, consent: boolean): Promise<{ user: ChatMessage; reply: ChatMessage; draft: Draft }> {
  const r = await api<{ user: RawMessage; reply: RawMessage; draft: RawDraft }>(`/studio/${id}/messages`, {
    method: 'POST', body: { text, ai_consent: consent },
  })
  return { user: toMessage(r.user), reply: toMessage(r.reply), draft: toDraft(r.draft) }
}

// ---------- public verification (U8) ----------

export type VerifyStatus = 'VALID' | 'NOT_PRODUCED' | 'REVOKED'

export interface Verification {
  code: string
  status: VerifyStatus
  statusText: string
  statement: string
  watermarkText: string
  orderType: string
  orderTypeLabel: string
  paperSize: string | null
  pages: number | null
  quantity: number
  issuedAt: string
  productionLockedAt: string | null
  writtenAt: string | null
}

/** Public, no sign-in. The code may have a dash or not and any letter case. */
export async function verifyCode(code: string): Promise<Verification> {
  const v = await api<{
    code: string; status: VerifyStatus; status_text: string; statement: string; watermark_text: string; order_type: string
    order_type_label: string; paper_size: string | null; pages: number | null; quantity: number; issued_at: string
    production_locked_at: string | null; written_at: string | null
  }>(`/verify/${encodeURIComponent(code.trim())}`, { auth: false })
  return {
    code: v.code, status: v.status, statusText: v.status_text, statement: v.statement, watermarkText: v.watermark_text,
    orderType: v.order_type, orderTypeLabel: v.order_type_label, paperSize: v.paper_size, pages: v.pages, quantity: v.quantity,
    issuedAt: v.issued_at, productionLockedAt: v.production_locked_at, writtenAt: v.written_at,
  }
}
