import { useState } from 'react'
import type { Job as JobFn } from '../../services/async'
import { useT } from '../../i18n'
import type { StockChange } from '../../services/manage'
import { errText, orderErrorKey } from '../../services/orders'

/** Shared pieces of the Manager catalog screens (Catalog.tsx, Materials.tsx). */

/** Runs a change with one busy flag and one error line for the whole tab. */
export function useRun(after: () => void) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const run = async (job: JobFn) => {
    if (busy) return false
    setBusy(true)
    setErr('')
    try {
      await job()
      after()
      return true
    } catch (e) {
      setErr(orderErrorKey(e))
      return false
    } finally {
      setBusy(false)
    }
  }
  return { busy, err, run }
}

export function ErrorLine({ err }: { err: string }) {
  const t = useT()
  return err ? <p className="lg-error" role="alert">{errText(t, err)}</p> : null
}

/** Stock change of one row: add or set a level, with the reason the backend audits. */
export function StockForm({ onSend, onCancel, busy }: { onSend: (c: StockChange) => void; onCancel: () => void; busy: boolean }) {
  const t = useT()
  const [mode, setMode] = useState<'ADD' | 'SET'>('ADD')
  const [qty, setQty] = useState('')
  const [reason, setReason] = useState('')
  const n = Number(qty)
  const ok = qty !== '' && Number.isInteger(n) && (mode === 'ADD' || n >= 0) && reason.trim().length > 0
  return (
    <div className="wk-form">
      <label className="vh-label">
        {t('mg.stock.mode')}
        <select className="vh-select" value={mode} onChange={(e) => setMode(e.target.value as 'ADD' | 'SET')}>
          <option value="ADD">{t('mg.stock.add')}</option>
          <option value="SET">{t('mg.stock.set')}</option>
        </select>
      </label>
      <label className="vh-label">
        {t('mg.stock.qty')}
        <input className="vh-input" inputMode="numeric" value={qty} onChange={(e) => setQty(e.target.value.replace(/[^\d-]/g, ''))} />
      </label>
      <label className="vh-label wk-grow">
        {t('mg.stock.reason')}
        <input className="vh-input" value={reason} maxLength={1000} onChange={(e) => setReason(e.target.value)} />
      </label>
      <button className="vh-btn vh-btn--ghost vh-btn--sm" onClick={onCancel}>{t('ov.back')}</button>
      <button className="vh-btn vh-btn--primary vh-btn--sm" disabled={busy || !ok} onClick={() => onSend({ mode, quantity: n, reason: reason.trim() })}>{t('mg.stock.save')}</button>
    </div>
  )
}

export const intOnly = (v: string) => v.replace(/\D/g, '').slice(0, 10)
export const decOnly = (v: string) => v.replace(/[^\d.]/g, '').slice(0, 8)
