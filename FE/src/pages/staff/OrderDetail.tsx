import { ChatCircleDots } from '@phosphor-icons/react'
import { useState } from 'react'
import type { Job } from '../../services/async'
import OrderPreview from '../../components/ui/OrderPreview'
import { STATUS_COLOR } from '../../constants/orderStatus'
import { useAsync } from '../../hooks/useAsync'
import { useMaterials } from '../../hooks/useMaterials'
import { useLocale, useT } from '../../i18n'
import { Link } from '../../router/router'
import { orderErrorKey, errText } from '../../services/orders'
import {
  REJECT_REASONS, acceptOrder, assignStaff, getStaffDirectory, getWork, orderJobs, orderPayments, rejectOrder, requestInfo,
  type RejectReason,
} from '../../services/workshop'
import { openChat } from '../../store/chatDock'
import { useUser } from '../../store/store'
import { fmt } from '../../utils/format'
import ChangeRequests from './ChangeRequests'
import { isManagerRole } from './RequireStaff'
import QuotationPanel from './QuotationPanel'
import SketchPanel from './SketchPanel'

const AFTER_QUOTE = ['AWAITING_PRIVACY', 'QUOTED', 'AWAITING_DEPOSIT', 'CONFIRMED', 'AWAITING_ACCEPTANCE', 'AWAITING_FINAL_PAYMENT', 'READY_TO_DELIVER', 'DELIVERING', 'COMPLETED']

/** One order for the workshop: what the customer sent, intake decisions, sketch, quotation, payments, jobs and chat. */
export default function OrderDetail({ id, onChanged }: { id: number; onChanged: () => void }) {
  const t = useT()
  const locale = useLocale()
  const user = useUser()
  const manager = isManagerRole(user?.apiRole)
  const q = useAsync(() => getWork(id), [id], 20000)
  const order = q.data
  const mats = useMaterials({ paperId: order?.paperId ?? null, penId: order?.penId ?? null, inkId: order?.inkId ?? null })
  const staff = useAsync(() => (manager ? getStaffDirectory() : Promise.resolve([])), [manager])
  const payments = useAsync(() => (order && AFTER_QUOTE.includes(order.status) ? orderPayments(id) : Promise.resolve([])), [id, order?.status])
  const jobs = useAsync(() => (order && ['CONFIRMED', 'AWAITING_ACCEPTANCE'].includes(order.status) ? orderJobs(id) : Promise.resolve([])), [id, order?.status])

  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [panel, setPanel] = useState<'' | 'info' | 'reject'>('')
  const [note, setNote] = useState('')
  const [reason, setReason] = useState<RejectReason>('OTHER')
  const [staffId, setStaffId] = useState<number | null>(null)

  const run = async (job: Job) => {
    if (busy) return
    setBusy(true)
    setErr('')
    try {
      await job()
      setPanel('')
      setNote('')
      await q.reload()
      onChanged()
    } catch (e) {
      setErr(orderErrorKey(e))
      if ((e as { code?: string }).code === 'STATE_CONFLICT') await q.reload()
    } finally {
      setBusy(false)
    }
  }

  if (q.error && !order) return <p className="lg-error" role="alert">{errText(t, orderErrorKey(q.error))}</p>
  if (!order) return <p className="sd-sub" role="status">{t('co.loading')}</p>

  const day = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString(locale, { day: 'numeric', month: 'short', year: 'numeric' }) : '–')
  const mine = order.assignedStaffId !== null && order.assignedStaffId === user?.id
  const assignee = staff.data?.find((s) => s.id === order.assignedStaffId)
  const unassigned = order.assignedStaffId === null
  // A Manager acts on a pool order only after choosing the Staff who will own it.
  const chosen = unassigned && manager ? (staffId ?? staff.data?.[0]?.id ?? null) : null
  // A Staff who decides on an unclaimed order claims it in the same step.
  const canDecide = order.status === 'SUBMITTED' && (manager ? !unassigned || chosen !== null : mine || unassigned)
  const withStaff = chosen ?? undefined
  const inputs = order.inputs
  const blurry = inputs.some((i) => i.kind === 'ORIGINAL_IMAGE' && i.qualityWarning)
  const canvas = inputs.find((i) => i.kind === 'CANVAS')
  const text = inputs.find((i) => i.kind === 'TEXT_CONTENT')

  const rows: [string, string][] = [
    [t('ov.type'), t(`ot.${order.type}`)],
    [t('or.qty'), String(order.quantity)],
    [t('or.paper'), order.workshopSuggest && !mats.paper ? t('co.sum.suggest') : mats.paper?.name ?? '–'],
    [t('or.pen'), mats.pen?.name ?? '–'],
    [t('or.ink'), mats.ink?.name ?? '–'],
    [t('wk.chars'), order.charCount !== null ? String(order.charCount) : '–'],
    [t(order.total !== null ? 'or.total' : 'ov.estimate'), order.total !== null ? fmt(order.total) : order.estMax !== null ? (order.estMin === order.estMax ? fmt(order.estMax) : `${fmt(order.estMin ?? 0)} – ${fmt(order.estMax)}`) : '–'],
    [t('wk.submitted'), day(order.submittedAt)],
    [t('wk.assignee'), unassigned ? t('wk.unclaimed') : mine ? t('wk.mine') : assignee?.fullName ?? `#${order.assignedStaffId}`],
  ]

  return (
    <div className="wk-order">
      <header className="wk-order-head">
        <div>
          <h2>{order.code}</h2>
          <p className="sd-sub">{order.customerName}</p>
        </div>
        <span className="vh-chip" style={{ color: STATUS_COLOR[order.status] }}>{t(`os.${order.status}`)}</span>
      </header>

      <section className="wk-block" aria-label={t('wk.content')}>
        <h3>{t('wk.content')}</h3>
        <OrderPreview order={order} inkColor={mats.ink?.hex} />
        {text?.text && <p className="wk-text">{text.text}</p>}
        {blurry && <p className="wk-warn">{t('wk.qualityWarn')}</p>}
        {!!order.warnings.length && order.warnings.map((w) => <p key={w} className="wk-warn">{w}</p>)}
        {canvas?.canvas && <p className="sd-sub">{t('co.strokes', { n: canvas.canvas.strokes.length })}</p>}
      </section>

      <section className="wk-block" aria-label={t('or.details')}>
        <h3>{t('or.details')}</h3>
        <dl className="wk-rows">
          {rows.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
          {order.note && <div><dt>{t('co.sum.note')}</dt><dd>{order.note}</dd></div>}
          {order.infoRequestNote && <div><dt>{t('wk.infoAsked')}</dt><dd>{order.infoRequestNote}</dd></div>}
          {order.rejectReason && <div><dt>{t('or.rejectedTitle')}</dt><dd>{t(`rr.${order.rejectReason}`)}{order.rejectNote ? `: ${order.rejectNote}` : ''}</dd></div>}
        </dl>
      </section>

      {order.status !== 'SUBMITTED' && order.status !== 'NEED_INFO' && <ChangeRequests order={order} />}

      {err && <p className="lg-error" role="alert">{errText(t, err)}</p>}

      {order.status === 'SUBMITTED' && (
        <section className="wk-block" aria-label={t('wk.intake')}>
          <h3>{t('wk.intake')}</h3>
          {unassigned && !manager && <p className="sd-sub">{t('wk.decideClaims')}</p>}
          {manager && unassigned && (
            <label className="vh-label">
              {t('wk.pickStaff')}
              <select className="vh-select" value={chosen ?? ''} onChange={(e) => setStaffId(Number(e.target.value))}>
                {(staff.data ?? []).map((s) => <option key={s.id} value={s.id}>{s.fullName} · {t('wk.openOrders', { n: s.openOrders })}</option>)}
              </select>
            </label>
          )}
          {canDecide && panel === '' && (
            <div className="wk-actions">
              <button className="vh-btn vh-btn--primary vh-btn--md" disabled={busy} onClick={() => void run(() => acceptOrder(id, withStaff))}>{t('wk.accept')}</button>
              <button className="vh-btn vh-btn--ghost vh-btn--md" disabled={busy} onClick={() => setPanel('info')}>{t('wk.askInfo')}</button>
              <button className="vh-btn vh-btn--ghost vh-btn--md" disabled={busy} onClick={() => setPanel('reject')}>{t('wk.reject')}</button>
            </div>
          )}
          {canDecide && panel === 'info' && (
            <div className="vh-stack" style={{ gap: 10 }}>
              <label className="vh-label" htmlFor="wk-note">{t('wk.infoLabel')}</label>
              <textarea id="wk-note" className="vh-textarea" rows={3} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} />
              <div className="wk-actions">
                <button className="vh-btn vh-btn--ghost vh-btn--md" onClick={() => setPanel('')}>{t('ov.back')}</button>
                <button className="vh-btn vh-btn--primary vh-btn--md" disabled={busy || !note.trim()} onClick={() => void run(() => requestInfo(id, note.trim(), withStaff))}>{t('wk.sendInfo')}</button>
              </div>
            </div>
          )}
          {canDecide && panel === 'reject' && (
            <div className="vh-stack" style={{ gap: 10 }}>
              <label className="vh-label">
                {t('wk.rejectReason')}
                <select className="vh-select" value={reason} onChange={(e) => setReason(e.target.value as RejectReason)}>
                  {REJECT_REASONS.map((r) => <option key={r} value={r}>{t(`rr.${r}`)}</option>)}
                </select>
              </label>
              <label className="vh-label">
                {t('wk.rejectNote')}
                <textarea className="vh-textarea" rows={2} maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)} />
              </label>
              <div className="wk-actions">
                <button className="vh-btn vh-btn--ghost vh-btn--md" onClick={() => setPanel('')}>{t('ov.back')}</button>
                <button className="vh-btn vh-btn--white vh-btn--md" disabled={busy} onClick={() => void run(() => rejectOrder(id, reason, note, withStaff))}>{t('wk.rejectConfirm')}</button>
              </div>
            </div>
          )}
          {manager && !unassigned && (
            <label className="vh-label">
              {t('wk.reassign')}
              <select className="vh-select" value={order.assignedStaffId ?? ''} disabled={busy} onChange={(e) => void run(() => assignStaff(id, Number(e.target.value)))}>
                {(staff.data ?? []).map((s) => <option key={s.id} value={s.id}>{s.fullName} · {t('wk.openOrders', { n: s.openOrders })}</option>)}
              </select>
            </label>
          )}
        </section>
      )}

      {order.status === 'NEED_INFO' && <p className="sd-sub">{t('wk.waitingInfo')}</p>}

      {order.status === 'ACCEPTED' && (
        <>
          <SketchPanel order={order} onChanged={() => { void q.reload(); onChanged() }} />
          <QuotationPanel order={order} onChanged={() => { void q.reload(); onChanged() }} />
        </>
      )}

      {AFTER_QUOTE.includes(order.status) && <QuotationPanel order={order} readOnly onChanged={() => { void q.reload(); onChanged() }} />}

      {!!payments.data?.length && (
        <section className="wk-block" aria-label={t('dp.history')}>
          <h3>{t('dp.history')}</h3>
          <dl className="wk-rows">
            {payments.data.map((p) => (
              <div key={p.id}>
                <dt>
                  {p.gateway} · {t(`pst.${p.status}`)}
                  {p.mode === 'MOCK' ? ` · ${t('dp.mockTag')}` : p.mode === 'SANDBOX' ? ` · ${t('dp.sandboxTag')}` : ''}
                  {p.needsRefund ? ` · ${t('dp.refundTag')}` : ''}
                </dt>
                <dd>{fmt(p.amount)}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      {!!jobs.data?.length && (
        <section className="wk-block" aria-label={t('wk.jobs')}>
          <h3>{t('wk.jobs')}</h3>
          <dl className="wk-rows">
            {jobs.data.map((j) => (
              <div key={j.id}>
                <dt>{j.robotCode} · {j.technicianName} · {t(`js.${j.status}`)}</dt>
                <dd>{new Date(j.slotStart).toLocaleString(locale, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}
      {manager && order.production === 'PENDING_SCHEDULE' && (
        <Link to={`/staff/schedule/${order.id}`} className="vh-btn vh-btn--primary vh-btn--md wk-link">{t('wk.goSchedule')}</Link>
      )}

      {order.status !== 'DRAFT' && (
        <button type="button" className="vh-btn vh-btn--ghost vh-btn--md wk-link" onClick={() => openChat(order.id, false)}>
          <ChatCircleDots size={18} aria-hidden />
          {t('cd.ws.ask')}
        </button>
      )}
    </div>
  )
}
