import { useState } from 'react'
import type { Job } from '../../services/async'
import SkipLink from '../../components/ui/SkipLink'
import ThemeToggle from '../../components/ui/ThemeToggle'
import LanguageToggle from '../../components/ui/LanguageToggle'
import { useAsync } from '../../hooks/useAsync'
import { useT } from '../../i18n'
import { Link } from '../../router/router'
import { orderErrorKey, errText } from '../../services/orders'
import { approveAdjustment, pendingApprovals, rejectAdjustment } from '../../services/workshop'
import { fmt } from '../../utils/format'
import StaffRail from './StaffRail'
import './dashboard.css'
import './polish.css'
import './workshop.css'

/** Manager only: price adjustments that went past the threshold and wait for a decision (BR-09). */
export default function Approvals() {
  const t = useT()
  const list = useAsync(() => pendingApprovals(), [], 30000)
  const [busy, setBusy] = useState<number | null>(null)
  const [err, setErr] = useState('')
  const [reasons, setReasons] = useState<Record<number, string>>({})
  const items = list.data?.items ?? []

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
    <div className="sd">
      <SkipLink />
      <StaffRail active="approvals" />
      <main className="sd-body" id="main">
        <header className="sd-top">
          <div>
            <h1>{t('wk.approvalsTitle')}</h1>
            <p>{t('wk.approvalsLede')}</p>
          </div>
          <div className="sd-top-right">
            <ThemeToggle className="vh-icon-btn" />
            <LanguageToggle className="vh-icon-btn" />
          </div>
        </header>
        <div className="wk-page">
          {err && <p className="lg-error" role="alert">{errText(t, err)}</p>}
          {!!list.error && <p className="lg-error" role="alert">{errText(t, orderErrorKey(list.error))}</p>}
          {list.loading && !list.data && <p className="sd-sub" role="status">{t('co.loading')}</p>}
          {list.data && !items.length && <p className="sd-sub">{t('wk.approvalsNone')}</p>}
          {items.map((q) => (
            <article key={q.id} className="wk-block">
              <header className="wk-order-head">
                <div>
                  <h3><Link to={`/staff/review/${q.orderId}`} className="vh-link">{t('wk.orderN', { id: q.orderId })}</Link> · {t('ov.quote', { v: q.version })}</h3>
                  <p className="sd-sub">{t('wk.approvalsNote', { pct: q.adjustmentPct ?? 0 })}</p>
                </div>
              </header>
              <dl className="wk-rows">
                <div><dt>{t('wk.computed')}</dt><dd className="vh-mono">{fmt(q.computedTotal)}</dd></div>
                <div><dt>{t('wk.adjusted')}</dt><dd className="vh-mono">{q.adjustedTotal !== null ? fmt(q.adjustedTotal) : '–'}</dd></div>
                <div><dt>{t('wk.adjustReason')}</dt><dd>{q.adjustmentReason ?? '–'}</dd></div>
              </dl>
              <div className="wk-form">
                <label className="vh-label wk-grow">
                  {t('wk.rejectAdjustReason')}
                  <input className="vh-input" value={reasons[q.id] ?? ''} maxLength={500} onChange={(e) => setReasons({ ...reasons, [q.id]: e.target.value })} />
                </label>
                <button className="vh-btn vh-btn--primary vh-btn--md" disabled={busy !== null} onClick={() => void run(q.id, () => approveAdjustment(q.id))}>{t('wk.approveAdjust')}</button>
                <button className="vh-btn vh-btn--ghost vh-btn--md" disabled={busy !== null || !(reasons[q.id] ?? '').trim()} onClick={() => void run(q.id, () => rejectAdjustment(q.id, (reasons[q.id] ?? '').trim()))}>{t('wk.rejectAdjust')}</button>
              </div>
            </article>
          ))}
        </div>
      </main>
    </div>
  )
}
