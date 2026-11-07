import { API_BASE, api, getTokens, refreshTokens } from './api'

/** `GET /me/notifications` family (FR-27, contract in `BE/docs/FE_API_GUIDE.md` 7j). Titles and bodies are Vietnamese text written by the backend. */

export type NotificationType =
  | 'ORDER_REJECTED' | 'QUOTATION_AVAILABLE' | 'QUOTATION_EXPIRED' | 'ETA_POSTPONED' | 'PRODUCT_COMPLETED'
  | 'DELIVERING' | 'PAYMENT' | 'ORDER_STATUS_CHANGED' | 'PRODUCTION_STATUS_CHANGED' | 'NEW_MESSAGE' | 'SYSTEM'
  | (string & {})

export interface AppNotification {
  id: number
  orderId: number | null
  type: NotificationType
  msgCode: string | null
  title: string
  body: string
  isRead: boolean
  readAt: string | null
  createdAt: string
}

interface RawNotification {
  id: number
  order_id: number | null
  type: string
  msg_code: string | null
  title: string
  body: string
  is_read: boolean
  read_at: string | null
  created_at: string
}

export const toNotification = (n: RawNotification): AppNotification => ({
  id: n.id,
  orderId: n.order_id,
  type: n.type,
  msgCode: n.msg_code,
  title: n.title,
  body: n.body,
  isRead: n.is_read,
  readAt: n.read_at,
  createdAt: n.created_at,
})

export interface NotificationPage {
  items: AppNotification[]
  unreadCount: number
  /** Pass as `beforeId` for the next page; null when there is no more. */
  nextBeforeId: number | null
}

export async function listNotifications(opts: { unreadOnly?: boolean; beforeId?: number | null; limit?: number } = {}): Promise<NotificationPage> {
  const q = new URLSearchParams({ limit: String(opts.limit ?? 20) })
  if (opts.unreadOnly) q.set('unread_only', 'true')
  if (opts.beforeId) q.set('before_id', String(opts.beforeId))
  const r = await api<{ items: RawNotification[]; unread_count: number; next_before_id: number | null }>(`/me/notifications?${q}`)
  return { items: r.items.map(toNotification), unreadCount: r.unread_count, nextBeforeId: r.next_before_id }
}

export const notificationUnreadCount = async () =>
  (await api<{ unread_count: number }>('/me/notifications/unread-count')).unread_count

export const markNotificationRead = async (id: number) =>
  toNotification(await api<RawNotification>(`/me/notifications/${id}/read`, { method: 'POST' }))

export const markAllNotificationsRead = async () =>
  (await api<{ updated: number }>('/me/notifications/read-all', { method: 'POST' })).updated

/**
 * Server-Sent Events from `GET /me/notifications/stream`. The backend wants the Bearer header (never a token in the URL),
 * so this reads the response with `fetch` instead of `EventSource`. Reconnects after 5 seconds (the server closes the
 * stream every 30 minutes) and refreshes the token once on a 401. Returns a function that stops it.
 */
export function openNotificationStream(handlers: {
  onReady: (unread: number) => void
  onNotification: (n: AppNotification) => void
  /** Called on every (re)connection, so the caller can reload what it missed. */
  onOpen?: () => void
}): () => void {
  const ctrl = new AbortController()
  let stopped = false

  const connect = async (retried = false): Promise<void> => {
    const token = getTokens()?.access
    if (!token) return
    const res = await fetch(`${API_BASE}/me/notifications/stream`, {
      headers: { Accept: 'text/event-stream', Authorization: `Bearer ${token}` },
      signal: ctrl.signal,
    })
    if (res.status === 401 && !retried && (await refreshTokens())) return connect(true)
    if (!res.ok || !res.body) throw new Error(`stream ${res.status}`)
    handlers.onOpen?.()

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    for (;;) {
      const { done, value } = await reader.read()
      if (done) return
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
        try {
          const json = JSON.parse(data.join('\n')) as unknown
          if (event === 'ready') handlers.onReady((json as { unread_count: number }).unread_count)
          else if (event === 'notification') handlers.onNotification(toNotification(json as RawNotification))
        } catch {
          // A malformed event is skipped; the list endpoint stays the source of truth.
        }
      }
    }
  }

  void (async () => {
    while (!stopped) {
      try {
        await connect()
      } catch {
        // Offline or the server restarted: wait and try again.
      }
      if (stopped) return
      await new Promise((r) => window.setTimeout(r, 5000))
    }
  })()

  return () => {
    stopped = true
    ctrl.abort()
  }
}
