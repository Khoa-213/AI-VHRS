import { useState } from 'react'
import type { Job } from '../../services/async'
import { useAsync } from '../../hooks/useAsync'
import { useLocale, useT } from '../../i18n'
import { addressLine, confirmReceipt, customerShipments, webLink } from '../../services/fulfillment'
import { errText, orderErrorKey, type Order } from '../../services/orders'
import { WORKSHOP_TZ } from '../../utils/pickupSlots'

/** Customer tracking never marks the order completed; only the carrier or Staff does that. */
export default function FulfillmentStatus({ order, onChanged }: { order: Order; onChanged: Job }) {
  const t = useT()
  const locale = useLocale()
  const shipments = useAsync(() => order.deliveryMethod === 'DELIVERY' ? customerShipments(order.id) : Promise.resolve([]), [order.id, order.deliveryMethod, order.status], order.status === 'COMPLETED' ? undefined : 15000)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [received, setReceived] = useState(false)
  const stamp = (iso: string | null) => iso ? new Date(iso).toLocaleString(locale, { timeZone: WORKSHOP_TZ, dateStyle: 'medium', timeStyle: 'short' }) : t('sp.unknown')
  const receipt = async () => {
    if (busy) return
    setBusy(true); setError('')
    try { await confirmReceipt(order.id); await onChanged() }
    catch (e) { setError(orderErrorKey(e)); await onChanged() }
    finally { setBusy(false) }
  }
  return <section className="vh-stack" aria-label={t('sp.title')}>
    <h2 className="vh-h2">{t('sp.title')}</h2>
    <p className="vh-fine">{t(order.status === 'COMPLETED' ? 'sp.completed' : order.deliveryMethod === 'PICKUP' ? 'sp.customerPickup' : 'sp.customerDelivery')}</p>
    <dl className="sp-customer-rows">
      <div><dt>{t('sp.method')}</dt><dd>{order.deliveryMethod ? t(`sp.method.${order.deliveryMethod}`) : t('sp.notChosen')}</dd></div>
      <div><dt>{t('sp.receiver')}</dt><dd>{order.deliveryAddress?.receiver || t('sp.unknown')}</dd></div>
      <div><dt>{t('sp.phone')}</dt><dd>{order.deliveryAddress?.phone || t('sp.unknown')}</dd></div>
      {order.deliveryMethod === 'DELIVERY' && <div><dt>{t('sp.address')}</dt><dd>{addressLine(order.deliveryAddress)}</dd></div>}
      {order.deliveryMethod === 'PICKUP' && <>
        <div><dt>{t('sp.workshop')}</dt><dd>{t('ft.campusAddress')}</dd></div>
        <div><dt>{t('sp.pickupStart')}</dt><dd>{stamp(order.pickupStart)}</dd></div>
        <div><dt>{t('sp.pickupEnd')}</dt><dd>{stamp(order.pickupEnd)}</dd></div>
      </>}
      {order.completedAt && <div><dt>{t('sp.completedAt')}</dt><dd>{stamp(order.completedAt)}</dd></div>}
    </dl>
    {shipments.error != null && <p className="lg-error" role="alert">{errText(t, orderErrorKey(shipments.error))}</p>}
    {shipments.loading && !shipments.data && <p role="status">{t('co.loading')}</p>}
    {order.deliveryMethod === 'DELIVERY' && shipments.data?.length === 0 && <p className="vh-fine">{t('sp.customerWait')}</p>}
    {shipments.data?.map((s, index) => <div key={s.id} className="vh-stack sp-customer-shipment">
      <b>{s.carrier} · {s.waybill_code || `#${s.id}`}</b>
      <span>{t(`sp.status.${s.status}`)}{index === 0 ? ` · ${t('sp.latest')}` : ''}</span>
      {s.mode === 'MOCK' && <p className="vh-fine">{t('sp.mockHelp')}</p>}
      <dl className="sp-customer-rows">
        <div><dt>{t('sp.eta')}</dt><dd>{stamp(s.eta)}</dd></div>
        <div><dt>{t('sp.pickedAt')}</dt><dd>{stamp(s.picked_up_at)}</dd></div>
        <div><dt>{t('sp.deliveredAt')}</dt><dd>{stamp(s.delivered_at)}</dd></div>
      </dl>
      {index === 0 && ['FAILED', 'RETURNED'].includes(s.status) && <p className="vh-fine">{t('sp.customerProblem')}</p>}
      {webLink(s.tracking_url) && <a className="vh-link" href={webLink(s.tracking_url)} target="_blank" rel="noopener noreferrer">{t('sp.track')}</a>}
    </div>)}
    <button type="button" className="vh-btn vh-btn--ghost vh-btn--md" disabled={busy} onClick={() => void Promise.all([shipments.reload(), onChanged()])}>{t('sp.refresh')}</button>
    {error && <p className="lg-error" role="alert">{errText(t, error)}</p>}
    {order.receivedConfirmedAt ? <p className="vh-fine" role="status">{t('sp.receiptRecorded', { time: stamp(order.receivedConfirmedAt) })}</p>
      : ['DELIVERING', 'COMPLETED'].includes(order.status) && <>
        <label className="sp-receipt"><input type="checkbox" checked={received} disabled={busy} onChange={(e) => setReceived(e.target.checked)} />{t('sp.receivedCheck')}</label>
        <button type="button" className="vh-btn vh-btn--primary vh-btn--md" disabled={busy || !received} onClick={() => void receipt()}>{t('sp.confirmReceipt')}</button>
        <p className="vh-fine">{t('sp.receiptHelp')}</p>
      </>}
  </section>
}
