import { useState } from 'react'
import Shell from '../../components/ws/Shell'
import type { Job } from '../../services/async'
import { useAsync } from '../../hooks/useAsync'
import { useLocale, useT } from '../../i18n'
import { Link } from '../../router/router'
import { errText, orderErrorKey } from '../../services/orders'
import { confirmRefund, refundOrphan, workshopRefunds, type Orphan, type Refund, type RefundAccount } from '../../services/refunds'
import { useUser } from '../../store/store'
import { fmt } from '../../utils/format'
import { AccountFields } from '../order/PaidOrderPanel'

const EMPTY: RefundAccount = { bankName: '', accountNumber: '', accountName: '' }

/** UC-28: refunds the workshop has to transfer by hand, and money that landed on a cancelled or wrong payment. Manager reads only. */
export default function Refunds() {
  const t = useT()
  const locale = useLocale()
  const user = useUser()
  const manager = user?.apiRole === 'MANAGER'
  const [tab, setTab] = useState<'PENDING' | 'SUCCESS'>('PENDING')
  const list = useAsync(() => workshopRefunds(tab), [tab], 30000)
  const [open, setOpen] = useState<string | null>(null)
  const [ref, setRef] = useState('')
  const [note, setNote] = useState('')
  const [reason, setReason] = useState('')
  const [acc, setAcc] = useState<RefundAccount>(EMPTY)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const act = async (job: Job) => {
    if (busy) return
    setBusy(true); setErr('')
    try {
      await job()
      setOpen(null); setRef(''); setNote(''); setReason(''); setAcc(EMPTY)
      await list.reload()
    } catch (e) {
      setErr(orderErrorKey(e))
    } finally {
      setBusy(false)
    }
  }

  const toggle = (key: string) => { setOpen(open === key ? null : key); setErr('') }
  const hasAny = !!(acc.bankName.trim() || acc.accountNumber.trim() || acc.accountName.trim())
  const accOk = acc.bankName.trim().length >= 2 && /^[0-9]{6,20}$/.test(acc.accountNumber) && acc.accountName.trim().length >= 2

  const refundCard = (r: Refund) => {
    const key = `r${r.id}`
    return (
      <section key={r.id} className="panel" aria-label={t('wk.orderN', { id: r.orderId })}>
        <div className="ph">
          <div>
            <h2><Link to={`/staff/review/${r.orderId}`} className="accent">{t('wk.orderN', { id: r.orderId })}</Link> · {fmt(r.amount)}</h2>
            <p className="sub">{r.rule ? t(`rf.rule.${r.rule}`) : r.reason ?? ''}</p>
          </div>
          <span className={`chip ${r.status === 'SUCCESS' ? 'ok' : 'warn'}`}>{t(`pst.${r.status}`)}</span>
        </div>
        <dl className="kv">
          <div><dt>{t('rf.accName')}</dt><dd>{r.account ? `${r.account.bankName} · ${r.account.accountNumber} · ${r.account.accountName}` : t('rf.noAccountStaff')}</dd></div>
          {r.deduction > 0 && <div><dt>{t('rf.kept', { amount: fmt(r.deduction) })}</dt><dd /></div>}
          {r.reference && <div><dt>{t('rf.reference', { ref: r.reference })}</dt><dd>{r.confirmedAt ? new Date(r.confirmedAt).toLocaleString(locale) : ''}</dd></div>}
        </dl>
        {r.status === 'PENDING' && !manager && (open === key ? (
          <div className="vh-stack" style={{ gap: 10 }}>
            <label className="vh-label">{t('rf.referenceLabel')}<input className="vh-input" value={ref} maxLength={100} onChange={(e) => setRef(e.target.value)} /></label>
            <label className="vh-label">{t('rf.noteLabel')}<input className="vh-input" value={note} maxLength={1000} onChange={(e) => setNote(e.target.value)} /></label>
            {!r.account && (
              <>
                <p className="co-fine">{t('rf.accountOptional')}</p>
                <AccountFields value={acc} onChange={setAcc} disabled={busy} />
              </>
            )}
            <div className="wk-form">
              <button type="button" className="btn ghost" onClick={() => setOpen(null)}>{t('ov.back')}</button>
              <button type="button" className="btn acc" disabled={busy || !ref.trim() || (!r.account && hasAny && !accOk)}
                onClick={() => void act(() => confirmRefund(r.id, { reference: ref.trim(), note: note.trim(), account: !r.account && accOk ? acc : null }))}>
                {t('rf.confirmSent')}
              </button>
            </div>
          </div>
        ) : <button type="button" className="btn acc" onClick={() => toggle(key)}>{t('rf.markSent')}</button>)}
      </section>
    )
  }

  const orphanCard = (o: Orphan) => {
    const key = `o${o.paymentId}`
    return (
      <section key={o.paymentId} className="panel" aria-label={t('wk.orderN', { id: o.orderId })}>
        <div className="ph">
          <div>
            <h2><Link to={`/staff/review/${o.orderId}`} className="accent">{t('wk.orderN', { id: o.orderId })}</Link> · {fmt(o.receivedAmount)}</h2>
            <p className="sub">{o.gateway} · {o.types.join(', ')} · {t(`os.${o.orderStatus}`)}</p>
          </div>
          <span className="chip bad">{t('rf.needsRefund')}</span>
        </div>
        {!manager && (open === key ? (
          <div className="vh-stack" style={{ gap: 10 }}>
            <label className="vh-label">{t('rf.orphanReason')}<input className="vh-input" value={reason} maxLength={500} onChange={(e) => setReason(e.target.value)} /></label>
            <AccountFields value={acc} onChange={setAcc} disabled={busy} />
            <div className="wk-form">
              <button type="button" className="btn ghost" onClick={() => setOpen(null)}>{t('ov.back')}</button>
              <button type="button" className="btn acc" disabled={busy || !reason.trim()}
                onClick={() => void act(() => refundOrphan(o.paymentId, { reason: reason.trim(), account: accOk ? acc : null }))}>
                {t('rf.openRefund')}
              </button>
            </div>
          </div>
        ) : <button type="button" className="btn acc" onClick={() => toggle(key)}>{t('rf.openRefund')}</button>)}
      </section>
    )
  }

  const d = list.data
  return (
    <Shell area={manager ? 'manager' : 'staff'} active="refunds" title={t('rf.pageTitle')} lede={t('rf.pageLede')}>
      <div className="wk-form" role="tablist" aria-label={t('rf.pageTitle')}>
        {(['PENDING', 'SUCCESS'] as const).map((s) => (
          <button key={s} type="button" role="tab" aria-selected={tab === s} className={`btn ${tab === s ? 'acc' : 'ghost'}`} onClick={() => setTab(s)}>{t(`rf.tab.${s}`)}</button>
        ))}
      </div>
      {err && <p className="lg-error" role="alert">{errText(t, err)}</p>}
      {!!list.error && <p className="lg-error" role="alert">{errText(t, orderErrorKey(list.error))}</p>}
      {list.loading && !d && <p className="sub" role="status">{t('co.loading')}</p>}
      {d && !d.refunds.length && !d.orphans.length && <section className="panel"><p className="sub">{t('rf.none')}</p></section>}
      {d?.orphans.map(orphanCard)}
      {d?.refunds.map(refundCard)}
    </Shell>
  )
}
