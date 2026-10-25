import { useSyncExternalStore } from 'react'

/**
 * State of the floating chat: open or not, and which order thread is shown. `ask` is set when a customer opens the chat
 * from an order: the dock then sends that order's card (`ORDER_CARD`) into the thread.
 */
export interface DockState {
  open: boolean
  orderId: number | null
  ask: number | null
}

let state: DockState = { open: false, orderId: null, ask: null }
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

/** Opens the chat. With an order, opens its thread; with `ask`, also shares that order's card, like asking about it. */
export function openChat(orderId?: number, ask = true) {
  if (orderId === undefined) return set({ open: true })
  set({ open: true, orderId, ask: ask ? orderId : null })
}

export const showThread = (orderId: number | null) => set({ orderId })
export const closeChat = () => set({ open: false })
export const doneAsking = () => set({ ask: null })
