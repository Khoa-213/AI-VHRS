import { useState } from 'react'
import type { Job } from '../../services/async'
import { useAsync } from '../../hooks/useAsync'
import { useLocale, useT } from '../../i18n'
import { errText, orderErrorKey, type Order } from '../../services/orders'
import {
  cancelPaidOrder, cancelPreview, getEta, orderRefunds, setRefundAccount, type Refund, type RefundAccount,
} from '../../services/refunds'
import { fmt } from '../../utils/format'

const EMPTY: RefundAccount = { bankName: '', accountNumber: '', accountName: '' }
const accountOk = (a: RefundAccount) => a.bankName.trim().length >= 2 && /^[0-9]{6,20}$/.test(a.accountNumber.trim()) && a.accountName.trim().length >= 2

export function AccountFields({ value, onChange, disabled }: { value: RefundAccount; onChange: (a: RefundAccount) => void; disabled?: boolean }) {
  const t = useT()
  return (
    <div className="vh-stack" style={{ gap: 8 }}>
      <label className="vh-label">{t('rf.bank')}
        <input className="vh-input" value={value.bankName} maxLength={100} disabled={disabled} onChange={(e) => onChange({ ...value, bankName: e.target.value })} />
      </label>
      <label className="vh-label">{t('rf.accNumber')}
        <input className="vh-input" inputMode="numeric" value={value.accountNumber} maxLength={20} disabled={disabled} onChange={(e) => onChange({ ...value, accountNumber: e.target.value.replace(/\D/g, '') })} />
      </label>
      <label className="vh-label">{t('rf.accName')}
        <input className="vh-input" value={value.accountName} maxLength={100} disabled={disabled} onChange={(e) => onChange({ ...value, accountName: e.target.value })} />
      </label>
    </div>
  )
}

function RefundRow({ order, refund, onChanged }: { order: Order; refund: Refund; onChanged: Job }) {
  const t = useT()
  const locale = useLocale()
  const [edit, setEdit] = useState(false)
  const [acc, setAcc] = useState<RefundAccount>(EMPTY)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const pending = refund.status === 'PENDING'

  const save = async () => {
    setBusy(true); setErr('')
    try {
      await setRefundAccount(order.id, refund.id, acc)
      setEdit(false)
      await onChanged()
    } catch (e) {
      setErr(orderErrorKey(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="vh-callout vh-callout--teal" style={{ gap: 6 }}>
      <b>{t(pending ? 'rf.pendingTitle' : 'rf.doneTitle', { amount: fmt(refund.amount) })}</b>
      {refund.rule && <span>{t(`rf.rule.${refund.rule}`)}</span>}
      {refund.deduction > 0 && <span>{t('rf.kept', { amount: fmt(refund.deduction) })}</span>}
      {refund.account
        ? <span>{t('rf.toAccount', { bank: refund.account.bankName, number: refund.account.accountNumber, name: refund.account.accountName })}</span>
        : pending && <span>{t('rf.noAccount')}</span>}
      {!pending && refund.reference && <span>{t('rf.reference', { ref: refund.reference })}</span>}
      {!pending && refund.confirmedAt && <span className="co-fine">{new Date(refund.confirmedAt).toLocaleString(locale)}</span>}
      {pending && !edit && <button type="button" className="vh-link" onClick={() => setEdit(true)}>{t(refund.account ? 'rf.changeAccount' : 'rf.addAccount')}</button>}
      {pending && edit && (
        <div className="vh-stack" style={{ gap: 10 }}>
          <AccountFields value={acc} onChange={setAcc} disabled={busy} />
          {err && <p className="lg-error" role="alert">{errText(t, err)}</p>}
          <div className="or-actions">
            <button type="button" className="vh-btn vh-btn--ghost vh-btn--md" disabled={busy} onClick={() => setEdit(false)}>{t('ov.back')}</button>
            <button type="button" className="vh-btn vh-btn--primary vh-btn--md" disabled={busy || !accountOk(acc)} onClick={() => void save()}>{t('rf.saveAccount')}</button>
          </div>
        </div>
      )}
    </div>
  )
}

/**
 * After the deposit: the expected delivery date and its postponements (FR-26), the refund rows, and, while the order is
 * `CONFIRMED`, the cancel flow with the refund the backend computed (UC-21, BR-14, BR-16).
 */
export default function PaidOrderPanel({ order, onChanged }: { order: Order; onChanged: Job }) {
  const t = useT()
  const locale = useLocale()
  const eta = useAsync(() => getEta(order.id), [order.id, order.status], 60000)
  const refunds = useAsync(() => orderRefunds(order.id), [order.id, order.status], 30000)
  const canCancel = order.status === 'CONFIRMED'
  const [open, setOpen] = useState(false)
  const preview = useAsync(() => (open && canCancel ? cancelPreview(order.id) : Promise.resolve(null)), [open, canCancel, order.id])
  const [reason, setReason] = useState('')
  const [acc, setAcc] = useState<RefundAccount>(EMPTY)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const p = preview.data
  const needAccount = !!p?.accountRequired && (p?.refundAmount ?? 0) > 0
  const day = (iso: string) => new Date(iso).toLocaleDateString(locale, { day: 'numeric', month: 'short', year: 'numeric' })

  const submit = async () => {
    setBusy(true); setErr('')
    try {
      await cancelPaidOrder(order.id, reason.trim(), needAccount ? acc : null)
      setOpen(false)
      await Promise.all([refunds.reload(), onChanged()])
    } catch (e) {
      setErr(orderErrorKey(e))
    } finally {
      setBusy(false)
    }
  }

  const e = eta.data
  return (
    <div className="vh-stack" style={{ gap: 12 }}>
      {e && order.status !== 'CANCELLED' && (e.eta || e.history.length > 0) && (
        <div className="vh-callout" style={{ gap: 6 }}>
          <b>{e.eta ? t('eta.expected', { date: day(e.eta) }) : t('eta.none')}</b>
          {e.postponedDays > 0 && <span>{t('eta.postponed', { n: e.postponedDays })}</span>}
          {e.canCancelFullRefund && canCancel && <span>{t('eta.fullRefund', { n: e.thresholdDays })}</span>}
          {e.history.length > 0 && (
            <details>
              <summary>{t('eta.history')}</summary>
              <ul className="eta-history">
                {e.history.map((h) => (
                  <li key={`${h.changedAt}-${h.newEta}`}>
                    <b>{h.oldEta ? `${day(h.oldEta)} → ${day(h.newEta)}` : day(h.newEta)}</b>
                    {h.reason && <span> · {h.reason}</span>}
                    <small> · {new Date(h.changedAt).toLocaleString(locale)}</small>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}

      {(refunds.data ?? []).map((r) => <RefundRow key={r.id} order={order} refund={r} onChanged={async () => { await refunds.reload() }} />)}

      {canCancel && !open && <button type="button" className="vh-link" onClick={() => { setOpen(true); setReason(''); setErr('') }}>{t('ov.cancel')}</button>}
      {canCancel && open && (
        <div className="vh-stack" style={{ gap: 10 }}>
          {preview.loading && !p && <p className="sub" role="status">{t('co.loading')}</p>}
          {!!preview.error && <p className="lg-error" role="alert">{errText(t, orderErrorKey(preview.error))}</p>}
          {p && !p.allowed && (
            <div className="vh-callout vh-callout--amber">
              <b>{t('rf.notAllowed')}</b>
              <span>{p.errorCode ? t(`rf.err.${p.errorCode}`, { n: p.thresholdDays, d: p.etaPostponedDays }) : p.message}</span>
            </div>
          )}
          {p && p.allowed && (
            <div className="vh-callout vh-callout--amber" style={{ gap: 4 }}>
              <b>{t('rf.willRefund', { amount: fmt(p.refundAmount) })}</b>
              {p.rule && <span>{t(`rf.rule.${p.rule}`)}</span>}
              <span>{t('rf.paid', { amount: fmt(p.paid) })}</span>
              {p.deduction > 0 && <span>{t('rf.kept', { amount: fmt(p.deduction) })}</span>}
            </div>
          )}
          {p?.allowed && (
            <>
              <label className="vh-label" htmlFor="pc-reason">{t('ov.cancelReason')}</label>
              <textarea id="pc-reason" className="vh-textarea" rows={3} maxLength={500} value={reason} onChange={(ev) => setReason(ev.target.value)} />
              {needAccount && (
                <>
                  <p className="co-fine">{t('rf.accountNeeded')}</p>
                  <AccountFields value={acc} onChange={setAcc} disabled={busy} />
                </>
              )}
            </>
          )}
          {err && <p className="lg-error" role="alert">{errText(t, err)}</p>}
          <div className="or-actions">
            <button type="button" className="vh-btn vh-btn--ghost vh-btn--md" disabled={busy} onClick={() => setOpen(false)}>{t('ov.back')}</button>
            {p?.allowed && (
              <button type="button" className="vh-btn vh-btn--white vh-btn--md" disabled={busy || !reason.trim() || (needAccount && !accountOk(acc))} onClick={() => void submit()}>
                {t('ov.cancelConfirm')}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
