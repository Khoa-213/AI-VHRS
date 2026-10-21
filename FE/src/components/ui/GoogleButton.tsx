import { useEffect, useRef, useState } from 'react'
import { useLang } from '../../i18n'

import { GOOGLE_CLIENT_ID } from '../../services/google'

interface Gis {
  accounts: {
    id: {
      initialize: (o: { client_id: string; callback: (r: { credential?: string }) => void; ux_mode?: string }) => void
      renderButton: (el: HTMLElement, o: Record<string, unknown>) => void
    }
  }
}

const SRC = 'https://accounts.google.com/gsi/client'
let loading: Promise<Gis> | null = null

function loadGis(): Promise<Gis> {
  const have = (window as unknown as { google?: Gis }).google
  if (have?.accounts) return Promise.resolve(have)
  loading ??= new Promise<Gis>((resolve, reject) => {
    const s = document.createElement('script')
    s.src = SRC
    s.async = true
    s.onload = () => resolve((window as unknown as { google: Gis }).google)
    s.onerror = () => {
      loading = null
      reject(new Error('GOOGLE_UNAVAILABLE'))
    }
    document.head.appendChild(s)
  })
  return loading
}

/**
 * "Continue with Google" using Google Identity Services. Google hands back an ID token (`credential`) which the backend
 * verifies at `POST /auth/google`; the page never sends a self-declared email or name.
 */
export default function GoogleButton({ onToken, onError, disabled }: { onToken: (idToken: string) => void; onError: () => void; disabled?: boolean }) {
  const host = useRef<HTMLDivElement>(null)
  const lang = useLang()
  const cb = useRef(onToken)
  const fail = useRef(onError)
  useEffect(() => {
    cb.current = onToken
    fail.current = onError
  })
  const [width, setWidth] = useState(0)

  useEffect(() => {
    const el = host.current
    if (!el) return
    // A dialog is initially hidden; observe it so opening it supplies the real width.
    const measure = () => setWidth(Math.min(400, Math.floor(el.getBoundingClientRect().width)))
    const observer = new ResizeObserver(measure)
    observer.observe(el)
    measure()
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (!GOOGLE_CLIENT_ID || !host.current || !width) return
    const el = host.current
    let dead = false
    loadGis().then((g) => {
      if (dead) return
      g.accounts.id.initialize({ client_id: GOOGLE_CLIENT_ID, callback: (r) => r.credential && cb.current(r.credential) })
      el.replaceChildren()
      g.accounts.id.renderButton(el, { type: 'standard', theme: 'outline', size: 'large', shape: 'pill', text: 'continue_with', width, locale: lang })
    }, () => fail.current())
    return () => {
      dead = true
    }
  }, [width, lang])

  if (!GOOGLE_CLIENT_ID) return null
  // Google's light iframe needs a matching color scheme to keep its outside corners transparent.
  return <div ref={host} style={{ colorScheme: 'light', display: 'flex', justifyContent: 'center', minHeight: 44, opacity: disabled ? 0.5 : 1, pointerEvents: disabled ? 'none' : undefined }} />
}
