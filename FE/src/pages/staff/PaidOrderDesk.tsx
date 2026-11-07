import { useState } from 'react'
import type { Job } from '../../services/async'
import { useAsync } from '../../hooks/useAsync'
import { useLocale, useT } from '../../i18n'
import { errText, orderErrorKey } from '../../services/orders'
import { getWorkshopEta, orderRefunds, setWorkshopEta, workshopCancel, workshopCancelPreview } from '../../services/refunds'
import type { WorkOrder } from '../../services/workshop'
import { useUser } from '../../store/store'
import { fmt } from '../../utils/format'

export const PAID_STATES = ['CONFIRMED', 'AWAITING_ACCEPTANCE', 'AWAITING_FINAL_PAYMENT', 'READY_TO_DELIVER', 'DELIVERING', 'COMPLETED', 'CANCELLED']

/** Workshop view after the deposit: the delivery date and who moved it (UC-30), cancelling for the workshop (FR-19) and the refund rows. */
export default function PaidOrderDesk({ order, onChanged }: { order: WorkOrder; onChanged: Job }) {
  const t = useT()
  const locale = useLocale()
  const user = useUser()
  const canWrite = user?.apiRole === 'STAFF' && order.assignedStaffId === user.id
  const showEta = order.status !== 'CANCELLED'
  const eta = useAsync(() => (showEta ? getWorkshopEta(order.id) : Promise.resolve(null)), [order.id, order.status, showEta], 60000)
  const refunds = useAsync(() => orderRefunds(order.id, true), [order.id, order.status], 30000)
  const [newEta, setNewEta] = useState('')
  const [etaReason, setEtaReason] = useState('')
  const [cancelOpen, setCancelOpen] = useState(false)
  const [cancelReason, setCancelReason] = useState('')
  const preview = useAsync(() => (cancelOpen ? workshopCancelPreview(order.id) : Promise.resolve(null)), [cancelOpen, order.id])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const day = (iso: string) => new Date(iso).toLocaleDateString(locale, { day: 'numeric', month: 'short', year: 'numeric' })

  const run = async (job: Job, after?: () => void) => {
    if (busy) return
    setBusy(true); setErr('')
    try {
      await job()
      after?.()
      await Promise.all([eta.reload(), refunds.reload(), onChanged()])
    } catch (e) {
      setErr(orderErrorKey(e))
    } finally {
      setBusy(false)
    }
  }

  const e = eta.data
  // A cancelled order that never took a deposit has nothing to show here.
  if (order.status === 'CANCELLED' && refunds.data && !refunds.data.length) return null
  const canEditEta = canWrite && ['CONFIRMED', 'AWAITING_ACCEPTANCE', 'AWAITING_FINAL_PAYMENT', 'READY_TO_DELIVER'].includes(order.status)
  const p = preview.data

  return (
    <section className="wk-block" aria-label={t('eta.deskTitle')}>
      <h3>{t('eta.deskTitle')}</h3>
      {err && <p className="lg-error" role="alert">{errText(t, err)}</p>}
      {!!eta.error && <p className="lg-error" role="alert">{errText(t, orderErrorKey(eta.error))}</p>}
      {e && (
        <>
          <dl className="wk-rows">
            <div><dt>{t('eta.current')}</dt><dd>{e.eta ? day(e.eta) : '–'}</dd></div>
            <div><dt>{t('eta.postponedTotal')}</dt><dd>{t('eta.days', { n: e.postponedDays })} / {t('eta.limit', { n: e.thresholdDays })}</dd></div>
            {e.suggestedEta && <div><dt>{t('eta.suggested')}</dt><dd>{day(e.suggestedEta)}</dd></div>}
          </dl>
          {e.canCancelFullRefund && <p className="wk-warn">{t('eta.overLimit', { n: e.thresholdDays })}</p>}
          {e.history.length > 0 && (
            <details>
              <summary>{t('eta.history')}</summary>
              <ul className="eta-history">
                {e.history.map((h) => (
                  <li key={`${h.changedAt}-${h.newEta}`}>
                    <b>{h.oldEta ? `${day(h.oldEta)} → ${day(h.newEta)}` : day(h.newEta)}</b>
                    {h.reason && <span> · {h.reason}</span>}
                    <small> · {h.actorId == null ? t('eta.bySystem') : t('eta.byStaff', { id: h.actorId })} · {new Date(h.changedAt).toLocaleString(locale)}</small>
                  </li>
                ))}
              </ul>
            </details>
          )}
          {canEditEta && (
            <div className="wk-form">
              <label className="vh-label">{t('eta.newDate')}
                <input className="vh-input" type="date" value={newEta} onChange={(ev) => setNewEta(ev.target.value)} />
              </label>
              <label className="vh-label wk-grow">{t('eta.reason')}
                <input className="vh-input" value={etaReason} maxLength={500} onChange={(ev) => setEtaReason(ev.target.value)} />
              </label>
              <button type="button" className="btn acc" disabled={busy || !newEta || !etaReason.trim()}
                onClick={() => void run(() => setWorkshopEta(order.id, newEta, etaReason.trim()), () => { setNewEta(''); setEtaReason('') })}>
                {t('eta.save')}
              </button>
            </div>
          )}
        </>
      )}

      {(refunds.data ?? []).map((r) => (
        <dl key={r.id} className="wk-rows">
          <div><dt>{t(r.status === 'SUCCESS' ? 'rf.doneTitle' : 'rf.pendingTitle', { amount: fmt(r.amount) })}</dt><dd>{r.reason ?? ''}</dd></div>
          {r.account && <div><dt>{t('rf.accName')}</dt><dd>{r.account.bankName} · {r.account.accountNumber} · {r.account.accountName}</dd></div>}
        </dl>
      ))}

      {canWrite && order.status === 'CONFIRMED' && !cancelOpen && (
        <button type="button" className="btn ghost" onClick={() => { setCancelOpen(true); setCancelReason('') }}>{t('eta.workshopCancel')}</button>
      )}
      {canWrite && order.status === 'CONFIRMED' && cancelOpen && (
        <div className="vh-stack" style={{ gap: 10 }}>
          {!!preview.error && <p className="lg-error" role="alert">{errText(t, orderErrorKey(preview.error))}</p>}
          {p && !p.allowed && <p className="wk-warn">{p.errorCode ? t(`rf.err.${p.errorCode}`, { n: p.thresholdDays, d: p.etaPostponedDays }) : p.message}</p>}
          {p?.allowed && (
            <>
              <p className="wk-warn">{t('eta.workshopCancelNote', { amount: fmt(p.refundAmount) })}</p>
              <label className="vh-label">{t('ov.cancelReason')}
                <textarea className="vh-textarea" rows={3} maxLength={500} value={cancelReason} onChange={(ev) => setCancelReason(ev.target.value)} />
              </label>
            </>
          )}
          <div className="or-actions">
            <button type="button" className="vh-btn vh-btn--ghost vh-btn--md" onClick={() => setCancelOpen(false)}>{t('ov.back')}</button>
            {p?.allowed && (
              <button type="button" className="vh-btn vh-btn--white vh-btn--md" disabled={busy || !cancelReason.trim()}
                onClick={() => void run(() => workshopCancel(order.id, cancelReason.trim()), () => setCancelOpen(false))}>
                {t('ov.cancelConfirm')}
              </button>
            )}
          </div>
        </div>
      )}
    </section>
  )
}
