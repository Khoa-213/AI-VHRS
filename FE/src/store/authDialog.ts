import { useSyncExternalStore } from 'react'

type AuthDialog = { mode: 'login' | 'register'; next?: string } | null
let current: AuthDialog = null
const listeners = new Set<() => void>()
const subscribe = (listener: () => void) => {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}
export function openAuth(mode: 'login' | 'register' = 'login', next?: string) {
  current = { mode, next }
  listeners.forEach((listener) => listener())
}
export function closeAuth() {
  current = null
  listeners.forEach((listener) => listener())
}
export function useAuthDialog() {
  return useSyncExternalStore(subscribe, () => current)
}
