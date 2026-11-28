import { useState } from 'react'
import { useAsync } from '../../hooks/useAsync'
import { useT } from '../../i18n'
import { ApiError } from '../../services/api'
import type { Job } from '../../services/async'
import { closeOrderByManager, managerClosePreview } from '../../services/managerOps'
import { errText, orderErrorKey } from '../../services/orders'
import { workshopCancel } from '../../services/refunds'
import type { WorkOrder } from '../../services/workshop'
import { useUser } from '../../store/store'
import { fmt } from '../../utils/format'
import { isManagerRole } from './RequireStaff'

/** Orders a Manager may close: the product exists but the order will not complete by itself. */
const CLOSABLE = ['AWAITING_FINAL_PAYMENT', 'READY_TO_DELIVER', 'DELIVERING']
const CANCEL_REASON_MIN = 5       // backend: POST /workshop/orders/{id}/cancel on an ACCEPTED order
const CLOSE_REASON_MIN = 10       // backend: POST /manager/orders/{id}/close

/**
 * Ways out of an order that would otherwise stay open for ever (audit 2026-11-27, D04 and D08):
 * - the Staff in charge cancel an ACCEPTED order (nothing was paid yet), with a reason the customer reads;
 * - a Manager closes an order stuck after production (balance never paid, never collected, parcel came back) and says how
 *   much of what was paid is given back. That only opens a refund request; the Staff pay it out by hand as usual.
 * The backend decides what is allowed; this panel shows its answer (`close-preview`) before offering the form.
 */
export default function OrderExits({ order, onChanged }: { order: WorkOrder; onChanged: Job }) {
  const t = useT()
  const user = useUser()
  const manager = isManagerRole(user?.apiRole)
  const inCharge = user?.apiRole === 'STAFF' && order.assignedStaffId === user.id
  const canCancel = inCharge && order.status === 'ACCEPTED'
  const canClose = manager && CLOSABLE.includes(order.status)
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [amount, setAmount] = useState('0')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [notice, setNotice] = useState('')
  const preview = useAsync(() => (open && canClose ? managerClosePreview(order.id) : Promise.resolve(null)), [open, canClose, order.id, order.status])

  if (!canCancel && !canClose) return notice ? <p className="sp-notice" role="status">{notice}</p> : null

  const run = async (job: Job, done: string) => {
    if (busy) return
    setBusy(true); setErr('')
    try {
      await job()
      setNotice(done); setOpen(false); setReason(''); setAmount('0')
    } catch (e) {
      setErr(orderErrorKey(e))
    } finally {
      await onChanged()
      setBusy(false)
    }
  }

  const p = preview.data
  const max = p?.refundable ?? 0
  const give = Number(amount)
  const amountOk = /^\d+$/.test(amount.trim()) && max - give >= 0        // digits only, so never negative
  const text = reason.trim()

  const close = () => {
    if (!amountOk || text.length < CLOSE_REASON_MIN) return
    if (!window.confirm(t('ox.close.ask', { code: order.code, amount: fmt(give) }))) return
    void run(() => closeOrderByManager(order.id, text, give), give > 0 ? t('ox.close.done', { amount: fmt(give) }) : t('ox.close.doneNoRefund'))
  }

  return (
    <section className="wk-block" aria-label={t(canCancel ? 'ox.cancel.title' : 'ox.close.title')}>
      <h3>{t(canCancel ? 'ox.cancel.title' : 'ox.close.title')}</h3>
      {notice && <p className="sp-notice" role="status">{notice}</p>}
      {err && <p className="lg-error" role="alert">{errText(t, err)}</p>}
      {!open && (
        <button type="button" className="btn ghost" onClick={() => { setOpen(true); setErr(''); setNotice('') }}>
          {t(canCancel ? 'ox.cancel.open' : 'ox.close.open')}
        </button>
      )}

      {open && canCancel && (
        <div className="vh-stack" style={{ gap: 10 }}>
          <p className="wk-warn">{t('ox.cancel.note')}</p>
          <label className="vh-label">{t('ox.cancel.reason')}
            <textarea className="vh-textarea" rows={3} maxLength={500} value={reason} onChange={(ev) => setReason(ev.target.value)} />
          </label>
          <div className="or-actions">
            <button type="button" className="vh-btn vh-btn--ghost vh-btn--md" disabled={busy} onClick={() => setOpen(false)}>{t('ov.back')}</button>
            <button type="button" className="vh-btn vh-btn--white vh-btn--md" disabled={busy || text.length < CANCEL_REASON_MIN}
              onClick={() => void run(() => workshopCancel(order.id, text), t('ox.cancel.done'))}>
              {t('ox.cancel.confirm')}
            </button>
          </div>
        </div>
      )}

      {open && canClose && (
        <div className="vh-stack" style={{ gap: 10 }}>
          {preview.loading && !p && <p className="sd-sub" role="status">{t('co.loading')}</p>}
          {!!preview.error && <p className="lg-error" role="alert">{errText(t, orderErrorKey(preview.error))}</p>}
          {p && !p.allowed && <p className="wk-warn">{errText(t, orderErrorKey(new ApiError(409, p.errorCode ?? '', p.message ?? '')))}</p>}
          {p?.allowed && (
            <>
              <p className="wk-warn">{t('ox.close.note')}</p>
              <dl className="wk-rows">
                <div><dt>{t('ox.close.refundable')}</dt><dd>{fmt(max)}</dd></div>
              </dl>
              <label className="vh-label">{t('ox.close.amount')}
                <input className="vh-input" inputMode="numeric" value={amount} aria-invalid={!amountOk} onChange={(ev) => setAmount(ev.target.value.replace(/[^\d]/g, ''))} />
              </label>
              <p className="sd-sub">{t('ox.close.amountHelp', { max: fmt(max) })}</p>
              {max > 0 && give !== max && (
                <button type="button" className="vh-link" onClick={() => setAmount(String(max))}>{t('ox.close.all')}</button>
              )}
              <label className="vh-label">{t('ox.close.reason')}
                <textarea className="vh-textarea" rows={3} maxLength={1000} value={reason} onChange={(ev) => setReason(ev.target.value)} />
              </label>
            </>
          )}
          <div className="or-actions">
            <button type="button" className="vh-btn vh-btn--ghost vh-btn--md" disabled={busy} onClick={() => setOpen(false)}>{t('ov.back')}</button>
            {p?.allowed && (
              <button type="button" className="vh-btn vh-btn--white vh-btn--md" disabled={busy || !amountOk || text.length < CLOSE_REASON_MIN} onClick={close}>
                {t('ox.close.confirm')}
              </button>
            )}
          </div>
        </div>
      )}
    </section>
  )
}
