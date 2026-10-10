import { useEffect, useSyncExternalStore, type AnchorHTMLAttributes, type MouseEvent } from 'react'

/**
 * Tiny history-API router. There is no router dependency in this project, and
 * the app has a handful of fixed routes, so this is all it needs.
 */

const listeners = new Set<() => void>()
const emit = () => listeners.forEach((l) => l())

function subscribe(cb: () => void) {
  listeners.add(cb)
  window.addEventListener('popstate', cb)
  return () => {
    listeners.delete(cb)
    window.removeEventListener('popstate', cb)
  }
}

const getPath = () => window.location.pathname

export function usePath() {
  return useSyncExternalStore(subscribe, getPath)
}

export function navigate(to: string) {
  const url = new URL(to, window.location.href)
  const same = url.pathname === window.location.pathname
  window.history.pushState(null, '', url.pathname + url.search + url.hash)
  emit()
  if (url.hash) {
    // Wait a frame so the new page has rendered its anchors.
    requestAnimationFrame(() => {
      const el = document.getElementById(url.hash.slice(1))
      if (el) el.scrollIntoView()
      else if (!same) window.scrollTo({ top: 0 })
    })
  } else if (!same) {
    window.scrollTo({ top: 0 })
  }
}

interface LinkProps extends Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href'> {
  to: string
}

export function Link({ to, onClick, ...rest }: LinkProps) {
  const handle = (e: MouseEvent<HTMLAnchorElement>) => {
    onClick?.(e)
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
    e.preventDefault()
    navigate(to)
  }
  return <a href={to} onClick={handle} {...rest} />
}

/** Turns plain same-origin `<a href="/…">` clicks (e.g. on the landing page) into SPA navigations. */
export function useInterceptLinks() {
  useEffect(() => {
    const onClick = (e: globalThis.MouseEvent) => {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
      const a = (e.target as Element | null)?.closest?.('a')
      if (!a || a.target || a.hasAttribute('download')) return
      const href = a.getAttribute('href')
      if (!href || !href.startsWith('/') || href.startsWith('//')) return
      e.preventDefault()
      navigate(href)
    }
    document.addEventListener('click', onClick)
    return () => document.removeEventListener('click', onClick)
  }, [])
}

/** Matches `/orders/:id/<page>` and returns the id. */
export function matchOrderRoute(path: string, page: string): string | null {
  const m = new RegExp(`^/orders/([^/]+)/${page}/?$`).exec(path)
  return m ? decodeURIComponent(m[1]) : null
}

export const orderPath = (id: string, page: 'review' | 'deposit' | 'result' | 'final-payment') =>
  `/orders/${encodeURIComponent(id)}/${page}`
