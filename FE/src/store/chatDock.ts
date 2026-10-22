import { useSyncExternalStore } from 'react'

/**
 * State of the floating chat (customer side): open or not, which order thread is shown, and the order cards the
 * customer attached by opening the chat from an order. Cards live only in this tab until the backend stores them as
 * messages (planned `ORDER_CARD` message kind).
 */
export interface DockState {
  open: boolean
  orderId: number | null
  cards: Record<number, string>
}

let state: DockState = { open: false, orderId: null, cards: {} }
const listeners = new Set<() => void>()
const set = (patch: Partial<DockState>) => {
  state = { ...state, ...patch }
  listeners.forEach((l) => l())
}

export const useChatDock = () =>
  useSyncExternalStore(
    (cb) => {
      listeners.add(cb)
      return () => listeners.delete(cb)
    },
    () => state,
  )

/** Opens the chat. With an order, opens its thread and drops that order's card at the bottom, like asking about it. */
export function openChat(orderId?: number, attach = true) {
  if (orderId === undefined) return set({ open: true })
  set({ open: true, orderId, cards: attach ? { ...state.cards, [orderId]: new Date().toISOString() } : state.cards })
}

export const showThread = (orderId: number | null) => set({ orderId })
export const closeChat = () => set({ open: false })
