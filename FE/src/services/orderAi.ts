/**
 * The AI assistant of a draft order (`BE/docs/FE_API_GUIDE.md` sections 7r and 7s, proposals since migration 0029).
 *
 * The assistant never changes the order by itself. Every turn that would change the text, the materials, the options or the
 * sketch comes back as a proposal; the order changes only when the customer applies it. The caps and the providers are shared
 * with the studio, hence `/studio/assistant/status`.
 */
import { API_BASE, ApiError, api, apiFile, getTokens, refreshTokens } from './api'

/** The draft the assistant works on (created when the first message is sent) and a reload of what changed on the server. */
export type EnsureOrder = () => Promise<number>
export type ReloadOrder = () => Promise<void>
/** Loads a picture that needs the Bearer header and gives its object URL. */
export type LoadUrl = () => Promise<string>

// ---------- status ----------

export interface AiStatus { enabled: boolean; available: boolean; left: number | null; limit: number | null }

export async function aiStatus(): Promise<AiStatus> {
  const s = await api<{ enabled: boolean; available: boolean; messages_left_today: number | null; daily_message_limit: number | null }>('/studio/assistant/status')
  return { enabled: s.enabled, available: s.available, left: s.messages_left_today, limit: s.daily_message_limit }
}

// ---------- data policy (migration 0031, guide 7s.1) ----------

/** The AI chat data policy in force. The text is the backend's, in Vietnamese only. */
export interface AiPolicy {
  title: string
  version: string
  body: string
  sections: { title: string; body: string }[]
  providers: string[]
  retentionDays: number | null
}

export async function aiChatPolicy(): Promise<AiPolicy> {
  const p = await api<{ title: string; version: string; body: string; sections?: { title: string; body: string }[] | null; providers?: string[] | null; retention_days?: number | null }>('/privacy-policy/ai-chat')
  return { title: p.title, version: p.version, body: p.body, sections: p.sections ?? [], providers: p.providers ?? [], retentionDays: p.retention_days ?? null }
}

/** Records the customer's consent to that version (`409 POLICY_VERSION_CHANGED` when a newer one came out meanwhile). */
export const acceptAiPolicy = (version: string) =>
  api<{ policy_version: string; accepted: boolean }>('/me/assistant/consent', { method: 'POST', body: { policy_version: version } })

// ---------- proposals ----------

export type ProposalStatus = 'PENDING' | 'APPLIED' | 'REJECTED'
/** Why a proposal cannot be applied now. */
export type BlockedReason = 'APPLIED' | 'REJECTED' | 'ORDER_NOT_EDITABLE' | 'ORDER_CHANGED'

/** One line of what a proposal changes. `before` and `after` are scalars, `{id, name}` (materials, styles), layout objects or revision ids. */
export interface AiChange { field: string; before: unknown; after: unknown }

export interface AiProposal {
  id: number
  messageId: number
  /** The pending proposal this one continued. */
  parentId: number | null
  status: ProposalStatus
  applicable: boolean
  blockedReason: BlockedReason | null
  changes: AiChange[]
  /** Estimated price AFTER the proposal is applied. */
  estimate: { priceMin: number; priceMax: number } | null
  /** The sketch the order shows after applying; `null` = the sketch does not change. */
  sketchRevisionId: number | null
  /** The picture to show on the card: the order AFTER applying, drawn with the proposal's paper, pen and ink. `null` = no sketch at all yet. */
  preview: ProposalPreview | null
  createdAt: string
}

export interface ProposalPreview {
  revisionId: number
  pages: number
  /** Path of the JPEG (needs the Bearer header); add `?page=N`. */
  url: string
  /** The proposal draws a new sketch (true) or keeps the current one (false). */
  sketchChanged: boolean
  /** The text changed but the sketch could not be redrawn (the customer edited strokes): it does not match the new text yet. */
  sketchOutdated: boolean
}

interface RawProposal {
  id: number; message_id: number; parent_proposal_id: number | null; status: ProposalStatus
  applicable: boolean; blocked_reason: BlockedReason | null
  changes: { field: string; before: unknown; after: unknown }[]
  estimate: { price_min: number; price_max: number } | null
  sketch_revision_id: number | null
  preview?: { revision_id: number; pages: number; preview_url: string; sketch_changed: boolean; sketch_outdated: boolean } | null
  created_at: string
}
const toProposal = (p: RawProposal): AiProposal => ({
  id: p.id, messageId: p.message_id, parentId: p.parent_proposal_id, status: p.status, applicable: p.applicable,
  blockedReason: p.blocked_reason, changes: p.changes ?? [], sketchRevisionId: p.sketch_revision_id, createdAt: p.created_at,
  preview: p.preview
    ? { revisionId: p.preview.revision_id, pages: p.preview.pages, url: p.preview.preview_url, sketchChanged: p.preview.sketch_changed, sketchOutdated: p.preview.sketch_outdated }
    : null,
  estimate: p.estimate ? { priceMin: p.estimate.price_min, priceMax: p.estimate.price_max } : null,
})

/** The customer applies a proposal: the order, its materials, its price and its sketch change on the server. */
export async function applyProposal(orderId: number, id: number): Promise<AiProposal> {
  const r = await api<{ proposal: RawProposal }>(`/orders/${orderId}/assistant/proposals/${id}/apply`, { method: 'POST', body: {} })
  return toProposal(r.proposal)
}

export async function rejectProposal(orderId: number, id: number): Promise<AiProposal> {
  return toProposal(await api<RawProposal>(`/orders/${orderId}/assistant/proposals/${id}/reject`, { method: 'POST', body: {} }))
}

/** `PROPOSAL_STALE` carries the reason in `details.reason` (ORDER_CHANGED, MATERIAL_UNAVAILABLE, TEMPLATE_UNAVAILABLE, REVISION_MISSING). */
export const staleReason = (e: unknown): string | null =>
  e instanceof ApiError && e.code === 'PROPOSAL_STALE' && e.details && typeof e.details === 'object'
    ? String((e.details as { reason?: unknown }).reason ?? '') || null
    : null

// ---------- conversation ----------

export interface AiToolCall { name: string; ok: boolean; revisionId: number | null }
export interface AiMessage {
  id: number
  role: string
  content: string
  status: string
  toolCalls: AiToolCall[]
  createdAt: string
  /** The proposal this reply made (assistant messages only). */
  proposal: AiProposal | null
}

interface RawMessage {
  id: number; role: string; content: string; status: string; created_at: string
  tool_calls?: { name: string; ok: boolean; revision_id: number | null }[]
  proposal?: RawProposal | null
}
const toMessage = (m: RawMessage): AiMessage => ({
  id: m.id, role: m.role.toUpperCase(), content: m.content, status: m.status, createdAt: m.created_at,
  toolCalls: (m.tool_calls ?? []).map((c) => ({ name: c.name, ok: c.ok, revisionId: c.revision_id })),
  proposal: m.proposal ? toProposal(m.proposal) : null,
})

/** One conversation of an order (migration 0031: an order can have up to 20; a new one does not remember the others). */
export interface AiSession {
  id: number
  orderId: number
  /** The customer's name for it, or its first message. */
  title: string | null
  /** The last message, at most 140 characters. */
  preview: string | null
  messageCount: number
  createdAt: string
  lastMessageAt: string | null
  /** The order can still change: the customer can keep chatting. */
  canChat: boolean
  /** The order is still a draft: the conversation can be deleted. */
  canDelete: boolean
}
interface RawSession {
  id: number; order_id: number; title: string | null; preview: string | null; message_count: number
  created_at: string; last_message_at: string | null; can_chat: boolean; can_delete: boolean
}
const toSession = (s: RawSession): AiSession => ({
  id: s.id, orderId: s.order_id, title: s.title, preview: s.preview, messageCount: s.message_count,
  createdAt: s.created_at, lastMessageAt: s.last_message_at, canChat: s.can_chat, canDelete: s.can_delete,
})

/** One conversation of the order; without `sessionId` the one used last. `sessionId` is null when the order has none yet. */
export async function aiConversation(orderId: number, sessionId?: number | null): Promise<{ consented: boolean; sessionId: number | null; messages: AiMessage[] }> {
  const q = sessionId ? `?session_id=${sessionId}` : ''
  const c = await api<{ consented_at: string | null; session: { id: number } | null; messages: RawMessage[] }>(`/orders/${orderId}/assistant/messages${q}`)
  return { consented: !!c.consented_at, sessionId: c.session?.id ?? null, messages: c.messages.map(toMessage) }
}

/** The conversations of the order, the one used last first. */
export const aiSessions = async (orderId: number): Promise<AiSession[]> =>
  (await api<RawSession[]>(`/orders/${orderId}/assistant/sessions`)).map(toSession)

/** Deletes a conversation for good (draft orders only, `can_delete`). */
export const deleteAiSession = (orderId: number, sessionId: number) =>
  api<void>(`/orders/${orderId}/assistant/sessions/${sessionId}`, { method: 'DELETE' })

/** The proposals still waiting for the customer: they lock the form and the sending of the order. */
export const openProposals = (messages: AiMessage[]): AiProposal[] =>
  messages.flatMap((m) => (m.proposal && m.proposal.status === 'PENDING' && m.proposal.applicable ? [m.proposal] : []))

// ---------- one message, with progress ----------

/** What the customer picked on the sketch: the assistant may change only that part. */
export interface AiSelection { stroke_ids: string[]; word_ids: string[]; line_ids: string[]; paragraph_ids: string[] }
export const emptySelection = (): AiSelection => ({ stroke_ids: [], word_ids: [], line_ids: [], paragraph_ids: [] })
export const selectionSize = (s: AiSelection): number => s.stroke_ids.length + s.word_ids.length + s.line_ids.length + s.paragraph_ids.length

export interface AiTurnBody {
  text: string
  /** Not sent from Create Order: the customer accepts the policy in its dialog before the chat opens. */
  ai_consent?: boolean
  base_revision_id?: number
  selection?: AiSelection
  /** Continue this pending proposal (the backend continues the latest one when this is left out). */
  base_proposal_id?: number
  /** Start from the order as it is now and ignore the pending proposals. */
  from_order?: boolean
  /** Start a new conversation (never together with `session_id`). */
  new_session?: boolean
  /** Continue this conversation; without it (and without `new_session`) the one used last. */
  session_id?: number
  client_ref: string
}
export interface AiTurn { user: AiMessage; reply: AiMessage; proposal: AiProposal | null; sessionId: number | null }
export type AiEvent =
  | { type: 'tool'; name: string; ok: boolean }
  | { type: 'failover' }

/**
 * Sends one message through the stream route and resolves with the turn. Progress (`tool`, `failover`) goes to `onEvent`.
 * A refusal before the model is called comes back as an ordinary HTTP error (`ApiError`); one during the turn as an `error` event.
 */
export async function sendAiMessage(orderId: number, body: AiTurnBody, onEvent: (e: AiEvent) => void, retried = false): Promise<AiTurn> {
  const token = getTokens()?.access
  const res = await fetch(`${API_BASE}/orders/${orderId}/assistant/messages/stream`, {
    method: 'POST',
    headers: { Accept: 'text/event-stream', 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify(body),
  }).catch((e: unknown) => {
    throw new ApiError(0, 'NETWORK', e instanceof Error ? e.message : 'Network error')
  })
  if (res.status === 401 && !retried && (await refreshTokens())) return sendAiMessage(orderId, body, onEvent, true)
  if (!res.ok || !res.body) {
    let code = `HTTP_${res.status}`
    let message = res.statusText
    let details: unknown
    try {
      const data = (await res.json()) as { error?: { code?: string; message?: string; details?: unknown } }
      code = data.error?.code ?? code
      message = data.error?.message ?? message
      details = data.error?.details
    } catch {
      // Not JSON: keep the status text.
    }
    throw new ApiError(res.status, code, message, details)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  let turn: AiTurn | null = null
  let failure: ApiError | null = null
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
    let end: number
    while ((end = buf.indexOf('\n\n')) >= 0) {
      const block = buf.slice(0, end)
      buf = buf.slice(end + 2)
      let event = 'message'
      const data: string[] = []
      for (const line of block.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
      }
      if (!data.length) continue
      let json: Record<string, unknown>
      try {
        json = JSON.parse(data.join('\n')) as Record<string, unknown>
      } catch {
        continue
      }
      if (event === 'tool') onEvent({ type: 'tool', name: String(json.name ?? ''), ok: !!json.ok })
      else if (event === 'failover') onEvent({ type: 'failover' })
      else if (event === 'reply') {
        const r = json as unknown as { user: RawMessage; reply: RawMessage; proposal?: RawProposal | null; session_id?: number | null }
        const reply = toMessage(r.reply)
        turn = { user: toMessage(r.user), reply, proposal: r.proposal ? toProposal(r.proposal) : reply.proposal, sessionId: r.session_id ?? null }
      } else if (event === 'error') {
        failure = new ApiError(409, String(json.code ?? 'INTERNAL_ERROR'), String(json.message ?? ''))
      }
    }
  }
  if (turn) return turn
  throw failure ?? new ApiError(0, 'NETWORK', 'Stream closed')
}

// ---------- the working sketch ----------

/** One page of the `vhrs-sketch/2` document, in millimetres, origin at the top left, y down. */
export interface SketchStroke { id: string; kind: string; points: [number, number][]; word: string | null }
export interface SketchWord { id: string; strokeIds: string[]; bbox: [number, number, number, number]; text: string | null }
export interface SketchLine { id: string; wordIds: string[]; bbox: [number, number, number, number]; paragraph: string | null }
export interface SketchParagraph { id: string; lineIds: string[]; bbox: [number, number, number, number] }
export interface SketchPage {
  no: number
  width: number
  height: number
  strokes: SketchStroke[]
  words: SketchWord[]
  lines: SketchLine[]
  paragraphs: SketchParagraph[]
}

export interface SketchInfo {
  revisionId: number
  pages: number
  /** The sketch history of the order: an applied proposal is a normal revision, so it can be undone and redone. */
  canUndo: boolean
  canRedo: boolean
  /** The text or the paper changed after this sketch was drawn: it has to be drawn again before the order is sent. */
  inputsChanged: boolean
  /** The strokes, words, lines and paragraphs the customer can pick for the assistant. */
  document: SketchPage[]
}

interface RawBox { bbox: [number, number, number, number] }
interface RawSketch {
  revision: { id: number }
  can_undo: boolean
  can_redo: boolean
  inputs_changed: boolean
  document: {
    pages: {
      no: number; width_mm: number; height_mm: number
      strokes?: SketchStroke[]
      words?: (RawBox & { id: string; stroke_ids: string[]; text?: string | null })[]
      lines?: (RawBox & { id: string; word_ids: string[]; paragraph?: string | null })[]
      paragraphs?: (RawBox & { id: string; line_ids: string[] })[]
    }[]
  }
}
const toInfo = (s: RawSketch): SketchInfo => {
  const pages = s.document?.pages ?? []
  return {
    revisionId: s.revision.id,
    pages: pages.length || 1,
    canUndo: s.can_undo,
    canRedo: s.can_redo,
    inputsChanged: s.inputs_changed,
    document: pages.map((p) => ({
      no: p.no, width: p.width_mm, height: p.height_mm,
      strokes: (p.strokes ?? []).map((x) => ({ id: x.id, kind: x.kind, points: x.points, word: x.word ?? null })),
      words: (p.words ?? []).map((w) => ({ id: w.id, strokeIds: w.stroke_ids, bbox: w.bbox, text: w.text ?? null })),
      lines: (p.lines ?? []).map((l) => ({ id: l.id, wordIds: l.word_ids, bbox: l.bbox, paragraph: l.paragraph ?? null })),
      paragraphs: (p.paragraphs ?? []).map((g) => ({ id: g.id, lineIds: g.line_ids, bbox: g.bbox })),
    })),
  }
}

/** The current sketch of the order, or `null` when none has been drawn yet. */
export async function getSketchInfo(orderId: number): Promise<SketchInfo | null> {
  try {
    return toInfo(await api<RawSketch>(`/orders/${orderId}/sketch`))
  } catch (e) {
    if (e instanceof ApiError && e.code === 'SKETCH_NOT_GENERATED') return null
    throw e
  }
}

/** Draws the sketch again from the form (the customer's own action; the assistant's drawings come as proposals). */
export const redrawSketch = async (orderId: number, discardEdits = false): Promise<SketchInfo> =>
  toInfo(await api<RawSketch>(`/orders/${orderId}/sketch/generate`, { method: 'POST', body: discardEdits ? { discard_edits: true } : {} }))

/**
 * Undo / redo of the sketch. Moving to a revision of another drawing brings the form back to what it was then (the caller
 * reloads the order). `UNDRAWN_INPUT_CHANGES` means form changes made since the last drawing would be lost: ask, then send `discard`.
 */
const move = async (orderId: number, dir: 'undo' | 'redo', discard: boolean): Promise<SketchInfo> =>
  toInfo(await api<RawSketch>(`/orders/${orderId}/sketch/${dir}`, { method: 'POST', body: discard ? { discard_input_changes: true } : {} }))
export const undoSketch = (orderId: number, discard = false) => move(orderId, 'undo', discard)
export const redoSketch = (orderId: number, discard = false) => move(orderId, 'redo', discard)

/** JPEG of one page of a proposal's preview as an object URL. The backend gives the path with the `/api/v1` prefix, which `apiFile` adds itself. */
export async function proposalPreviewUrl(previewUrl: string, page = 1): Promise<string> {
  const { blob } = await apiFile(`${previewUrl.replace(/^\/api\/v1/, '')}?page=${page}`)
  return URL.createObjectURL(blob)
}

/** JPEG of one page of one revision as an object URL (the endpoint needs the Bearer header, so it cannot be an `<img src>`). */
export async function sketchPreviewUrl(orderId: number, revisionId: number, page = 1): Promise<string> {
  const { blob } = await apiFile(`/orders/${orderId}/sketch/preview?page=${page}&revision_id=${revisionId}`)
  return URL.createObjectURL(blob)
}
