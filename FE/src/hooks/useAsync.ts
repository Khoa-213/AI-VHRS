import { useCallback, useEffect, useRef, useState } from 'react'

export interface Async<T> {
  data: T | null
  error: unknown
  /** True until the first answer (or error) arrives. */
  loading: boolean
  reload: () => Promise<void>
}

/**
 * Runs `load` whenever `deps` change and, with `poll` (milliseconds, or a function of the latest data), keeps asking while the page is open.
 * A late answer for an older request is dropped. The previous data stays visible while it reloads.
 */
export function useAsync<T>(load: () => Promise<T>, deps: unknown[], poll?: number | ((data: T | null) => number | undefined)): Async<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [loading, setLoading] = useState(true)
  const seq = useRef(0)
  const fn = useRef(load)
  fn.current = load

  const run = useCallback(async () => {
    const mine = ++seq.current
    try {
      const d = await fn.current()
      if (mine !== seq.current) return
      setData(d)
      setError(null)
    } catch (e) {
      if (mine !== seq.current) return
      setError(e)
    } finally {
      if (mine === seq.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    setLoading(true)
    void run()
    return () => {
      seq.current++
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  const pollMs = typeof poll === 'function' ? poll(data) : poll
  useEffect(() => {
    if (!pollMs) return
    const h = window.setInterval(() => {
      if (document.visibilityState === 'visible') void run()
    }, pollMs)
    return () => window.clearInterval(h)
  }, [pollMs, run])

  return { data, error, loading, reload: run }
}
