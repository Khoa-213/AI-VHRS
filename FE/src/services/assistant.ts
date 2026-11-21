/**
 * The AI assistant of a draft order (V2 Phase C, `BE/docs/FE_API_GUIDE.md` section 7s). Only the create-order editor
 * uses it, and only while the order is a draft; the backend refuses other statuses.
 * The caps and the providers are shared with the backend's studio, hence `/studio/assistant/status`.
 */
import { ApiError, API_BASE, api, getTokens, refreshTokens } from './api'
import type { Selection } from './sketch'

export interface ToolCall { name: string; ok: boolean; revisionId: number | null }
export interface AssistantMessage {
  id: number
  role: 'user' | 'assistant' | string
  content: string
  status: 'OK' | 'FAILED' | string
  toolCalls: ToolCall[]
  createdAt: string
}
export interface AssistantStatus { enabled: boolean; available: boolean; left: number | null; limit: number | null }

interface RawMessage {
  id: number; role: string; content: string; status: string; created_at: string
  tool_calls?: { name: string; ok: boolean; revision_id: number | null }[]
}
const toMessage = (m: RawMessage): AssistantMessage => ({
  id: m.id, role: m.role, content: m.content, status: m.status, createdAt: m.created_at,
  toolCalls: (m.tool_calls ?? []).map((c) => ({ name: c.name, ok: c.ok, revisionId: c.revision_id })),
})

export async function assistantStatus(): Promise<AssistantStatus> {
  const s = await api<{ enabled: boolean; available: boolean; messages_left_today: number | null; daily_message_limit: number | null }>('/studio/assistant/status')
  return { enabled: s.enabled, available: s.available, left: s.messages_left_today, limit: s.daily_message_limit }
}

export async function conversation(orderId: number): Promise<{ consented: boolean; messages: AssistantMessage[] }> {
  const c = await api<{ consented_at: string | null; messages: RawMessage[] }>(`/orders/${orderId}/assistant/messages`)
  return { consented: !!c.consented_at, messages: c.messages.map(toMessage) }
}

export interface TurnBody {
  text: string
  ai_consent: boolean
  base_revision_id?: number
  selection?: Selection
  client_ref: string
}
export interface Turn { user: AssistantMessage; reply: AssistantMessage; sketchRevisionId: number | null }

export type StreamEvent =
  | { type: 'provider'; provider: string }
  | { type: 'tool'; name: string; ok: boolean; revisionId: number | null }
  | { type: 'failover'; provider: string }

/**
 * Sends one message through the stream route and resolves with the turn. Progress (`provider`, `tool`, `failover`) is
 * reported to `onEvent`. Errors raised before the model is called come back as ordinary HTTP errors (`ApiError`).
 */
export async function sendTurn(orderId: number, body: TurnBody, onEvent: (e: StreamEvent) => void, retried = false): Promise<Turn> {
  const token = getTokens()?.access
  const res = await fetch(`${API_BASE}/orders/${orderId}/assistant/messages/stream`, {
    method: 'POST',
    headers: { Accept: 'text/event-stream', 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify(body),
  }).catch((e: unknown) => {
    throw new ApiError(0, 'NETWORK', e instanceof Error ? e.message : 'Network error')
  })
  if (res.status === 401 && !retried && (await refreshTokens())) return sendTurn(orderId, body, onEvent, true)
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
      // Not JSON.
    }
    throw new ApiError(res.status, code, message, details)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  let turn: Turn | null = null
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
      if (event === 'provider') onEvent({ type: 'provider', provider: String(json.provider ?? '') })
      else if (event === 'failover') onEvent({ type: 'failover', provider: String(json.provider ?? '') })
      else if (event === 'tool') onEvent({ type: 'tool', name: String(json.name ?? ''), ok: !!json.ok, revisionId: (json.revision_id as number | null) ?? null })
      else if (event === 'reply') {
        const r = json as unknown as { user: RawMessage; reply: RawMessage; sketch_revision_id: number | null }
        turn = { user: toMessage(r.user), reply: toMessage(r.reply), sketchRevisionId: r.sketch_revision_id }
      } else if (event === 'error') {
        failure = new ApiError(409, String(json.code ?? 'INTERNAL_ERROR'), String(json.message ?? ''))
      }
    }
  }
  if (turn) return turn
  throw failure ?? new ApiError(0, 'NETWORK', 'Stream closed')
}

/** The sketch revision an assistant turn proposes: the last successful edit that made one. */
export const proposalOf = (m: AssistantMessage): number | null =>
  [...m.toolCalls].reverse().find((c) => c.ok && c.revisionId)?.revisionId ?? null
