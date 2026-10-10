import { useSyncExternalStore } from 'react'

export type Theme = 'dark' | 'light'

const KEY = 'aivhrs-theme'
const listeners = new Set<() => void>()

function read(): Theme {
  try {
    return localStorage.getItem(KEY) === 'light' ? 'light' : 'dark'
  } catch {
    return 'dark'
  }
}

let theme: Theme = read()

function apply() {
  document.documentElement.setAttribute('data-theme', theme)
}
apply()

export function setTheme(next: Theme) {
  theme = next
  apply()
  try {
    localStorage.setItem(KEY, next)
  } catch {
    /* storage blocked: the choice lasts for this visit only */
  }
  listeners.forEach((l) => l())
}

export const toggleTheme = () => setTheme(theme === 'dark' ? 'light' : 'dark')

export function useTheme(): Theme {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb)
      return () => {
        listeners.delete(cb)
      }
    },
    () => theme,
  )
}
