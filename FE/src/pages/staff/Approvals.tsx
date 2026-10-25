import { useState } from 'react'
import { ArrowRight } from '@phosphor-icons/react'
import Shell from '../../components/ws/Shell'
import { useAsync } from '../../hooks/useAsync'
import { useT } from '../../i18n'
import { Link } from '../../router/router'
import type { Job } from '../../services/async'
import { errText, orderErrorKey } from '../../services/orders'
import { allPendingApprovals, approveAdjustment, rejectAdjustment } from '../../services/workshop'
import { fmt } from '../../utils/format'

/** Manager only: price adjustments that went past the threshold and wait for a decision (BR-09). */
export default function Approvals() {
  const t = useT()
  const list = useAsync(() => allPendingApprovals(), [], 30000)
  const [busy, setBusy] = useState<number | null>(null)
  const [err, setErr] = useState('')
  const [reasons, setReasons] = useState<Record<number, string>>({})
  const items = list.data ?? []

  const run = async (id: number, job: Job) => {
    if (busy !== null) return
    setBusy(id)
    setErr('')
    try {
      await job()
      await list.reload()
    } catch (e) {
      setErr(orderErrorKey(e))
    } finally {
      setBusy(null)
    }
  }

  return (
    <Shell area="manager" active="approvals" title={t('wk.approvalsTitle')} lede={t('wk.approvalsLede')}>
      {err && <p className="lg-error" role="alert">{errText(t, err)}</p>}
      {!!list.error && <p className="lg-error" role="alert">{errText(t, orderErrorKey(list.error))}</p>}
      {list.loading && !list.data && <p className="sub" role="status">{t('co.loading')}</p>}
      {list.data && !items.length && <section className="panel"><p className="sub">{t('wk.approvalsNone')}</p></section>}
      {items.map((q) => {
        const reason = reasons[q.id] ?? ''
        return (
          <section key={q.id} className="panel" aria-label={t('wk.orderN', { id: q.orderId })}>
            <div className="ph">
              <div>
                <h2><Link to={`/staff/review/${q.orderId}`} className="accent">{t('wk.orderN', { id: q.orderId })}</Link> · {t('ov.quote', { v: q.version })}</h2>
                <p className="sub">{t('wk.approvalsNote', { pct: q.adjustmentPct ?? 0 })}</p>
              </div>
              <span className="chip warn">{t('wk.waitingYou')}</span>
            </div>
            <div className="rule" />
            <div className="cmp">
              <div className="c2"><span className="sub">{t('wk.computed')}</span><b className="mono">{fmt(q.computedTotal)}</b></div>
              <ArrowRight size={26} aria-hidden />
              <div className="c2"><span className="sub">{t('wk.adjusted')}</span><b className="mono accent">{q.adjustedTotal !== null ? fmt(q.adjustedTotal) : '–'}</b></div>
              {q.adjustmentPct !== null && <span className={`chip ${q.adjustmentPct > 0 ? 'bad' : 'info'}`}>{q.adjustmentPct > 0 ? '+' : ''}{q.adjustmentPct}%</span>}
            </div>
            <dl className="kv"><div><dt>{t('wk.adjustReason')}</dt><dd style={{ maxWidth: 520 }}>{q.adjustmentReason ?? '–'}</dd></div></dl>
            <div className="wk-form">
              <label className="vh-label wk-grow">
                {t('wk.rejectAdjustReason')}
                <input className="vh-input" value={reason} maxLength={500} onChange={(e) => setReasons({ ...reasons, [q.id]: e.target.value })} />
              </label>
              <button className="btn acc" disabled={busy !== null} onClick={() => void run(q.id, () => approveAdjustment(q.id))}>{t('wk.approveAdjust')}</button>
              <button className="btn ghost" disabled={busy !== null || !reason.trim()} onClick={() => void run(q.id, () => rejectAdjustment(q.id, reason.trim()))}>{t('wk.rejectAdjust')}</button>
            </div>
          </section>
        )
      })}
    </Shell>
  )
}
