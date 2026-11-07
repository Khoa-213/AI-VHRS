import { useEffect, useSyncExternalStore } from 'react'
import {
  listNotifications, markAllNotificationsRead, markNotificationRead, openNotificationStream,
  type AppNotification,
} from '../services/notifications'

/**
 * The signed-in person's notification list and badge, kept live by the SSE stream. One stream for the whole tab while at
 * least one bell is mounted. A new notification also fires the `onIncoming` listeners, so an open order page can reload.
 */
interface State {
  items: AppNotification[]
  unread: number
  nextBeforeId: number | null
  loaded: boolean
  error: unknown
}

let state: State = { items: [], unread: 0, nextBeforeId: null, loaded: false, error: null }
const listeners = new Set<() => void>()
const incoming = new Set<(n: AppNotification) => void>()
let stop: (() => void) | null = null
let users = 0

const emit = (next: Partial<State>) => {
  state = { ...state, ...next }
  listeners.forEach((l) => l())
}

export async function reloadNotifications() {
  try {
    const p = await listNotifications()
    emit({ items: p.items, unread: p.unreadCount, nextBeforeId: p.nextBeforeId, loaded: true, error: null })
  } catch (error) {
    emit({ error, loaded: true })
  }
}

export async function loadMoreNotifications() {
  if (!state.nextBeforeId) return
  try {
    const p = await listNotifications({ beforeId: state.nextBeforeId })
    const seen = new Set(state.items.map((n) => n.id))
    emit({ items: [...state.items, ...p.items.filter((n) => !seen.has(n.id))], unread: p.unreadCount, nextBeforeId: p.nextBeforeId, error: null })
  } catch (error) {
    emit({ error })
  }
}

export async function readNotification(id: number) {
  const before = state.items.find((n) => n.id === id)
  if (!before || before.isRead) return
  emit({ items: state.items.map((n) => (n.id === id ? { ...n, isRead: true } : n)), unread: Math.max(0, state.unread - 1) })
  try {
    await markNotificationRead(id)
  } catch {
    await reloadNotifications()
  }
}

export async function readAllNotifications() {
  emit({ items: state.items.map((n) => ({ ...n, isRead: true })), unread: 0 })
  try {
    await markAllNotificationsRead()
  } catch {
    await reloadNotifications()
  }
}

function start() {
  stop = openNotificationStream({
    onOpen: () => void reloadNotifications(),
    onReady: (unread) => emit({ unread }),
    onNotification: (n) => {
      if (state.items.some((x) => x.id === n.id)) return
      emit({ items: [n, ...state.items], unread: state.unread + (n.isRead ? 0 : 1) })
      incoming.forEach((fn) => fn(n))
    },
  })
}

function subscribe(cb: () => void) {
  listeners.add(cb)
  return () => { listeners.delete(cb) }
}

/** Mount once per bell: starts the stream for the first one and stops it with the last. */
export function useNotifications(): State {
  useEffect(() => {
    if (users++ === 0) {
      state = { items: [], unread: 0, nextBeforeId: null, loaded: false, error: null }
      start()
    }
    return () => {
      if (--users === 0) {
        stop?.()
        stop = null
      }
    }
  }, [])
  return useSyncExternalStore(subscribe, () => state)
}

/** Runs `fn` whenever a new notification arrives (for example to reload the order that is open). */
export function useOnNotification(fn: (n: AppNotification) => void) {
  useEffect(() => {
    incoming.add(fn)
    return () => { incoming.delete(fn) }
  }, [fn])
}
