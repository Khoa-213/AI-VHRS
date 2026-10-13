import { useCallback, useEffect, useState } from 'react'
import { GHN_LIVE, fetchLogs, isFinal } from '../services/ghn'
import { applyShipLogs } from '../store/store'
import type { Order } from '../types'

const POLL_MS = 30_000

/**
 * Keeps an order's GHN scans fresh. With the real proxy it polls while the page
 * is open (the backend webhook is the source, this is only the read side).
 * With the scripted courier the store already holds the scans, so it is a no-op.
 */
export function useShipmentSync(order: Order | null) {
  const code = order?.shipment?.ghnCode
  const id = order?.id
  const last = order?.shipment?.logs[order.shipment.logs.length - 1]?.status
  const finished = !!last && isFinal(last)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [syncedAt, setSyncedAt] = useState<Date | null>(null)

  const refresh = useCallback(async () => {
    if (!GHN_LIVE || !code || !id) return
    setBusy(true)
    try {
      applyShipLogs(id, await fetchLogs(code))
      setError(null)
      setSyncedAt(new Date())
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not reach GHN')
    } finally {
      setBusy(false)
    }
  }, [code, id])

  useEffect(() => {
    if (!GHN_LIVE || !code || finished) return
    void refresh()
    const t = window.setInterval(() => void refresh(), POLL_MS)
    return () => window.clearInterval(t)
  }, [code, finished, refresh])

  return { live: GHN_LIVE, busy, error, syncedAt, refresh }
}
