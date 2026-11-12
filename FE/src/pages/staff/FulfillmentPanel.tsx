import { useState } from 'react'
import { CaretDown } from '@phosphor-icons/react'
import type { Job } from '../../services/async'
import { useAsync } from '../../hooks/useAsync'
import { useLocale, useT } from '../../i18n'
import { errText, orderErrorKey } from '../../services/orders'
import { type WorkOrder, orderPayments } from '../../services/workshop'
import {
  ACTIVE_SHIPMENTS, MOCK_MOVES, addressLine, cancelShipment, confirmPickup, createShipment,
  mockShipmentEvent, webLink, workshopShipments, type ShipmentStatus,
} from '../../services/fulfillment'
import { useUser } from '../../store/store'
import { fmt } from '../../utils/format'
import { WORKSHOP_TZ } from '../../utils/pickupSlots'

export const FULFILLMENT_STATES = ['AWAITING_FINAL_PAYMENT', 'READY_TO_DELIVER', 'DELIVERING', 'COMPLETED']

/** Shipping and pickup use distinct backend actions. Only the assigned Staff can mutate either. */
export default function FulfillmentPanel({ order, onChanged }: { order: WorkOrder; onChanged: Job }) {
  const t = useT()
  const locale = useLocale()
  const user = useUser()
  const canWrite = user?.apiRole === 'STAFF' && order.assignedStaffId === user.id
  const shipments = useAsync(() => order.deliveryMethod === 'DELIVERY' ? workshopShipments(order.id) : Promise.resolve([]), [order.id, order.deliveryMethod, order.status], 15000)
  const payments = useAsync(() => orderPayments(order.id), [order.id, order.status], 20000)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [note, setNote] = useState('')
  const [packed, setPacked] = useState(false)
  const [phone, setPhone] = useState('')
  const [code, setCode] = useState('')
  const [handed, setHanded] = useState(false)
  const [cancelId, setCancelId] = useState<number | null>(null)
  const [reason, setReason] = useState('')
  const [event, setEvent] = useState<ShipmentStatus>('PICKED_UP')
  const [eventReason, setEventReason] = useState('')
  const [demoConfirmed, setDemoConfirmed] = useState(false)
  const rows = shipments.data ?? []
  const latest = rows[0]
  const paid = ['READY_TO_DELIVER', 'DELIVERING', 'COMPLETED'].includes(order.status)
  const address = order.deliveryAddress
  const moves = latest ? MOCK_MOVES[latest.status] : []
  const nextEvent = moves.includes(event) ? event : moves[0]
  const canCreate = canWrite && order.deliveryMethod === 'DELIVERY' && ['READY_TO_DELIVER', 'DELIVERING'].includes(order.status)
    && !!order.shippingCarrier && !!order.shippingService && !shipments.loading && !shipments.error && shipments.data !== null
    && (!latest || !ACTIVE_SHIPMENTS.includes(latest.status))
  const stamp = (iso: string | null) => iso ? new Date(iso).toLocaleString(locale, { timeZone: WORKSHOP_TZ, dateStyle: 'medium', timeStyle: 'short' }) : t('sp.unknown')
  const refresh = async () => { await Promise.all([shipments.reload(), payments.reload(), onChanged()]) }
  const run = async (action: Job, message: string) => {
    if (busy) return
    setBusy(true); setError(''); setNotice('')
    try {
      await action()
      setNotice(message); setPacked(false); setHanded(false); setPhone(''); setCode(''); setCancelId(null); setReason(''); setDemoConfirmed(false)
    } catch (e) { setError(orderErrorKey(e)) }
    finally { await refresh(); setBusy(false) }
  }
  const paidRows = (payments.data ?? []).filter((p) => p.status === 'SUCCESS')
  const needsRefund = payments.data?.some((p) => p.needsRefund)
  return <details className="wk-block fulfillment sp-disclosure" open aria-label={t('sp.title')}>
    <summary className="sp-fold-summary">
      <h3>{t('sp.title')}</h3>
      <span className="sp-fold-toggle"><span className="sp-fold-closed">{t('sp.expand')}</span><span className="sp-fold-open">{t('sp.collapse')}</span><CaretDown size={18} aria-hidden /></span>
    </summary>
    <div className="sp-fold-body">
    <div className="sp-heading"><button type="button" className="vh-btn vh-btn--ghost vh-btn--sm" disabled={busy} onClick={() => void refresh()}>{t('sp.refresh')}</button></div>
    <p className={paid ? 'sp-notice' : 'wk-warn'}>{t(paid ? order.status === 'COMPLETED' ? 'sp.completed' : 'sp.paid' : 'sp.awaitingPayment')}</p>
    {!canWrite && <p className="sd-sub">{t('sp.readOnly')}</p>}
    <dl className="wk-rows">
      <div><dt>{t('wk.assignee')}</dt><dd>{order.assignedStaffId === null ? t('wk.unclaimed') : canWrite ? t('wk.mine') : `#${order.assignedStaffId}`}</dd></div>
      <div><dt>{t('sp.method')}</dt><dd>{order.deliveryMethod ? t(`sp.method.${order.deliveryMethod}`) : t('sp.notChosen')}</dd></div>
      <div><dt>{t('sp.receiver')}</dt><dd>{address?.receiver || order.customerName || t('sp.unknown')}</dd></div>
      <div><dt>{t('sp.phone')}</dt><dd>{address?.phone || t('sp.unknown')}</dd></div>
      {order.deliveryMethod === 'DELIVERY' && <>
        <div><dt>{t('sp.address')}</dt><dd>{addressLine(address) || t('sp.unknown')}</dd></div>
        <div><dt>{t('sp.carrier')}</dt><dd>{order.shippingCarrier || t('sp.notChosen')}</dd></div>
        <div><dt>{t('sp.service')}</dt><dd>{order.shippingService || t('sp.notChosen')}</dd></div>
        <div><dt>{t('sp.eta')}</dt><dd>{stamp(order.shippingEta)}</dd></div>
      </>}
      {order.deliveryMethod === 'PICKUP' && <>
        <div><dt>{t('sp.workshop')}</dt><dd>{t('ft.campusAddress')}</dd></div>
        <div><dt>{t('sp.pickupStart')}</dt><dd>{stamp(order.pickupStart)}</dd></div>
        <div><dt>{t('sp.pickupEnd')}</dt><dd>{stamp(order.pickupEnd)}</dd></div>
      </>}
      {order.completedAt && <div><dt>{t('sp.completedAt')}</dt><dd>{stamp(order.completedAt)}</dd></div>}
      {order.receivedConfirmedAt && <div><dt>{t('sp.receivedAt')}</dt><dd>{stamp(order.receivedConfirmedAt)}</dd></div>}
    </dl>
    <div className="sp-payment">
      <h4>{t('sp.payment')}</h4>
      {needsRefund && <p className="wk-warn">{t('dp.refundBody')}</p>}
      {payments.loading && !payments.data && <p role="status">{t('co.loading')}</p>}
      {payments.error != null && <p className="lg-error" role="alert">{errText(t, orderErrorKey(payments.error))}</p>}
      <dl className="wk-rows">
        {(['DEPOSIT', 'FINAL', 'SHIPPING'] as const).map((type) => <div key={type}><dt>{t(`sp.payment.${type}`)}</dt><dd>{payments.data ? fmt(paidRows.filter((p) => p.type === type).reduce((sum, p) => sum + p.amount, 0)) : t('sp.unknown')}</dd></div>)}
      </dl>
      <p className="sd-sub">{t('sp.paymentHelp')}</p>
    </div>
    {error && <p className="lg-error" role="alert">{errText(t, error)}</p>}
    {notice && <p className="sp-notice" role="status">{notice}</p>}
    {shipments.error != null && <p className="lg-error" role="alert">{errText(t, orderErrorKey(shipments.error))}</p>}
    {order.deliveryMethod === 'PICKUP' && <>
      <p className="sd-sub">{t('sp.pickupHelp')}</p>
      {canWrite && order.status === 'READY_TO_DELIVER' && <fieldset disabled={busy} className="sp-form">
        <legend>{t('sp.pickupConfirm')}</legend>
        <label className="vh-label">{t('sp.verifyCode')}<input className="vh-input" value={code} onChange={(e) => setCode(e.target.value)} autoComplete="off" /></label>
        <label className="vh-label">{t('sp.verifyPhone')}<input className="vh-input" type="tel" maxLength={20} value={phone} onChange={(e) => setPhone(e.target.value)} autoComplete="off" /></label>
        <label className="wk-check"><input type="checkbox" checked={handed} onChange={(e) => setHanded(e.target.checked)} />{t('sp.handedCheck')}</label>
        <button type="button" className="vh-btn vh-btn--primary vh-btn--md" disabled={!handed || code.trim() !== order.code || !/^(0|\+84)\d{9}$/.test(phone.trim())} onClick={() => void run(() => confirmPickup(order.id, phone), t('sp.pickupDone'))}>{t('sp.pickupConfirm')}</button>
      </fieldset>}
    </>}
    {order.deliveryMethod === 'DELIVERY' && <>
      <p className="sd-sub">{t('sp.shippingHelp')}</p>
      {shipments.loading && !shipments.data && <p role="status">{t('co.loading')}</p>}
      {!shipments.loading && !shipments.error && !rows.length && <p className="sd-sub">{t('sp.noShipment')}</p>}
      {latest && ['FAILED', 'RETURNED'].includes(latest.status) && <p className="wk-warn" role="status">{t('sp.problem')}</p>}
      {canCreate && <fieldset className="sp-form" disabled={busy}>
        <legend>{t(latest ? 'sp.recreate' : 'sp.create')}</legend>
        <label className="vh-label">{t('sp.note')}<textarea className="vh-textarea" maxLength={300} rows={2} value={note} onChange={(e) => setNote(e.target.value)} /></label>
        <label className="wk-check"><input type="checkbox" checked={packed} onChange={(e) => setPacked(e.target.checked)} />{t('sp.packed')}</label>
        <button type="button" className="vh-btn vh-btn--primary vh-btn--md" disabled={!packed} onClick={() => void run(() => createShipment(order.id, note), t('sp.created'))}>{t(latest ? 'sp.recreate' : 'sp.create')}</button>
      </fieldset>}
      <details className="sp-history sp-disclosure">
        <summary className="sp-fold-summary">
          <h4>{t('sp.shipments')}<span className="sp-fold-count">{rows.length}</span></h4>
          <span className="sp-fold-toggle"><span className="sp-fold-closed">{t('sp.expand')}</span><span className="sp-fold-open">{t('sp.collapse')}</span><CaretDown size={18} aria-hidden /></span>
        </summary>
        <div className="sp-history-body">
        <p className="sd-sub">{t('sp.newestFirst')}</p>
      {rows.map((s, index) => <article key={s.id} className="sp-shipment">
        <div className="sp-heading"><h4>{s.waybill_code || `#${s.id}`}</h4><span className="chip mute">{t(`sp.status.${s.status}`)}</span></div>
        {index === 0 && <span className="sd-sub">{t('sp.latest')}</span>}
        <dl className="wk-rows">
          <div><dt>{t('sp.carrier')}</dt><dd>{s.carrier}</dd></div>
          <div><dt>{t('sp.service')}</dt><dd>{s.service_code || t('sp.unknown')}</dd></div>
          <div><dt>{t('sp.mode')}</dt><dd>{s.mode === 'MOCK' ? t('sp.mock') : s.mode}</dd></div>
          <div><dt>{t('sp.fee')}</dt><dd>{fmt(Number(s.fee))}</dd></div>
          <div><dt>{t('sp.package')}</dt><dd>{s.package_type || t('sp.unknown')}</dd></div>
          <div><dt>{t('sp.weight')}</dt><dd>{s.weight_g === null ? t('sp.unknown') : t('sp.grams', { n: s.weight_g })}</dd></div>
          <div><dt>{t('sp.receiver')}</dt><dd>{String(s.to_address.receiver ?? '') || t('sp.unknown')}</dd></div>
          <div><dt>{t('sp.phone')}</dt><dd>{String(s.to_address.phone ?? '') || t('sp.unknown')}</dd></div>
          <div><dt>{t('sp.address')}</dt><dd>{addressLine(s.to_address) || t('sp.unknown')}</dd></div>
          <div><dt>{t('sp.createdAt')}</dt><dd>{stamp(s.created_at)}</dd></div>
          <div><dt>{t('sp.pickedAt')}</dt><dd>{stamp(s.picked_up_at)}</dd></div>
          <div><dt>{t('sp.deliveredAt')}</dt><dd>{stamp(s.delivered_at)}</dd></div>
          <div><dt>{t('sp.eta')}</dt><dd>{stamp(s.eta)}</dd></div>
          {s.carrier_status_raw && <div><dt>{t('sp.rawStatus')}</dt><dd>{s.carrier_status_raw}</dd></div>}
          {s.created_by !== null && <div><dt>{t('sp.createdBy')}</dt><dd>#{s.created_by}</dd></div>}
        </dl>
        {s.is_fallback_fee && <p className="sd-sub">{t('sp.fallback')}</p>}
        <div className="wk-actions">
          {webLink(s.label_link) ? <a className="vh-btn vh-btn--ghost vh-btn--md" href={webLink(s.label_link)} target="_blank" rel="noopener noreferrer">{t('sp.label')}</a> : <span className="sd-sub">{t('sp.noLabel')}</span>}
          {webLink(s.tracking_url) && <a className="vh-btn vh-btn--ghost vh-btn--md" href={webLink(s.tracking_url)} target="_blank" rel="noopener noreferrer">{t('sp.track')}</a>}
          {canWrite && s.status === 'CREATED' && <button type="button" className="vh-btn vh-btn--ghost vh-btn--md" disabled={busy} onClick={() => { setCancelId(s.id); setReason('') }}>{t('sp.cancel')}</button>}
        </div>
        {cancelId === s.id && <fieldset className="sp-form" disabled={busy}>
          <legend>{t('sp.cancel')}</legend>
          <p className="sd-sub">{t('sp.cancelHelp')}</p>
          <label className="vh-label">{t('sp.cancelReason')}<textarea className="vh-textarea" rows={2} maxLength={1000} value={reason} onChange={(e) => setReason(e.target.value)} /></label>
          <div className="wk-actions"><button type="button" className="vh-btn vh-btn--ghost vh-btn--md" onClick={() => setCancelId(null)}>{t('ov.back')}</button><button type="button" className="vh-btn vh-btn--primary vh-btn--md" disabled={!reason.trim()} onClick={() => void run(() => cancelShipment(s.id, reason), t('sp.cancelled'))}>{t('sp.cancelConfirm')}</button></div>
        </fieldset>}
      </article>)}
        </div>
      </details>
      {canWrite && latest?.mode === 'MOCK' && moves.length !== 0 && nextEvent && order.status !== 'COMPLETED' && <fieldset className="sp-form sp-demo" disabled={busy}>
        <legend>{t('sp.mockTitle')}</legend>
        <p className="wk-warn">{t('sp.mockHelp')}</p>
        <label className="vh-label">{t('sp.nextEvent')}<select className="vh-select" value={nextEvent} onChange={(e) => { setEvent(e.target.value as ShipmentStatus); setDemoConfirmed(false) }}>{moves.map((s) => <option key={s} value={s}>{t(`sp.status.${s}`)}</option>)}</select></label>
        <label className="vh-label">{t('sp.eventReason')}<textarea className="vh-textarea" rows={2} maxLength={300} value={eventReason} onChange={(e) => setEventReason(e.target.value)} /></label>
        <label className="wk-check"><input type="checkbox" checked={demoConfirmed} onChange={(e) => setDemoConfirmed(e.target.checked)} />{t('sp.demoConfirm')}</label>
        <button type="button" className="vh-btn vh-btn--primary vh-btn--md" disabled={!demoConfirmed || (['FAILED', 'RETURNED'].includes(nextEvent) && !eventReason.trim())} onClick={() => void run(() => mockShipmentEvent(latest.id, nextEvent, eventReason), t('sp.eventSent'))}>{t('sp.sendEvent')}</button>
      </fieldset>}
    </>}
    </div>
  </details>
}
