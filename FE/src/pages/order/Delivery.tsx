import { useEffect, useMemo, useState } from 'react'
import Page from '../../components/layout/Page'
import OrderPreview from '../../components/ui/OrderPreview'
import { ORDER_HREF } from '../../constants'
import { useAsync } from '../../hooks/useAsync'
import { useDebounced } from '../../hooks/useDebounced'
import { useLocale, useT } from '../../i18n'
import { Link, orderPath } from '../../router/router'
import { getDistricts, getProvinces, getWards, type Place } from '../../services/locations'
import {
  chooseDelivery, errText, getDeliveryQuote, getOrder, orderErrorKey, previewDeliveryQuote,
  type DeliveryAddress, type DeliveryMethod, type Order, type ShippingService,
} from '../../services/orders'
import type { Job } from '../../services/async'
import { useProfile } from '../../store/store'
import { fmt } from '../../utils/format'
import { WORKSHOP_TZ, dayOf, noonOf, pickupDays, slotsOn } from '../../utils/pickupSlots'
import './order.css'

const PHONE = /^(0|\+84)\d{9}$/
// The order moved on the server (paid, or no longer at this step): the page has to catch up.
const RELOAD_ON = ['FINAL_ALREADY_PAID', 'FINAL_PAYMENT_NOT_EXPECTED']

interface Form {
  receiver: string
  phone: string
  street: string
  province: string
  district: string
  ward: string
}

const EMPTY: Form = { receiver: '', phone: '', street: '', province: '', district: '', ward: '' }

/** The address form starts from the address saved on the order, else from the account. */
const formOf = (order: Order, name: string, phone: string): Form => {
  const a = order.deliveryMethod === 'DELIVERY' ? order.deliveryAddress : null
  return {
    receiver: a?.receiver ?? name, phone: a?.phone ?? phone, street: a?.street ?? '',
    province: a?.province_code ?? '', district: a?.district_code ?? '', ward: a?.ward_code ?? '',
  }
}

const nameOf = (list: Place[] | null, code: string) => (code ? list?.find((p) => p.code === code)?.name : undefined)
const isService = (s: ShippingService, carrier?: string | null, code?: string | null) => s.carrier === carrier && s.code === code

/**
 * How the customer receives the order, once they accepted the product: delivery by a carrier service they pick
 * (priced live for the address they type) or pick-up at the workshop at a time they book. Saving only records the
 * choice; the final payment, (G − D) plus shipping, comes after it.
 */
export default function Delivery({ id }: { id: string | null }) {
  const t = useT()
  const locale = useLocale()
  const profile = useProfile()
  const orderId = Number(id)
  const q = useAsync(() => getOrder(orderId), [orderId])
  const order = q.data
  const open = order?.status === 'AWAITING_FINAL_PAYMENT'
  const quote = useAsync(() => (open ? getDeliveryQuote(orderId) : Promise.resolve(null)), [orderId, open])

  const [method, setMethod] = useState<DeliveryMethod | null>(null)
  const [form, setForm] = useState<Form | null>(null)
  const [picked, setPicked] = useState<{ carrier: string; code: string } | null>(null)
  const [day, setDay] = useState('')
  const [slot, setSlot] = useState(0)
  const [pickupPhone, setPickupPhone] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [saved, setSaved] = useState(false)
  // What the customer saw when they pressed save, to tell them if the carrier priced it differently.
  const [seen, setSeen] = useState<number | null>(null)

  // The form starts from what the order already holds, once it arrives.
  useEffect(() => {
    if (!order || form) return
    setForm(formOf(order, profile.fullName, profile.phone))
    if (order.pickupStart) {
      setDay(dayOf(order.pickupStart))
      setSlot(Date.parse(order.pickupStart))
    }
    setPickupPhone((order.deliveryMethod === 'PICKUP' ? order.deliveryAddress?.phone : null) ?? profile.phone)
  }, [order, form, profile.fullName, profile.phone])

  const f = form ?? EMPTY
  const set = (patch: Partial<Form>) => {
    setForm({ ...f, ...patch })
    setSaved(false)
  }

  const provinces = useAsync(getProvinces, [])
  const districts = useAsync(() => (f.province ? getDistricts(f.province) : Promise.resolve([])), [f.province])
  const wards = useAsync(() => (f.district ? getWards(f.district) : Promise.resolve([])), [f.district])
  const placesErr = provinces.error ?? districts.error ?? wards.error

  const provinceName = nameOf(provinces.data, f.province)
  const districtName = nameOf(districts.data, f.district)
  const wardName = nameOf(wards.data, f.ward)
  const phoneOk = PHONE.test(f.phone.trim())
  const address: DeliveryAddress | null = f.receiver.trim() && phoneOk && f.street.trim() && provinceName && districtName && wardName
    ? {
        receiver: f.receiver.trim(), phone: f.phone.trim(), street: f.street.trim(),
        province_code: f.province, district_code: f.district, ward_code: f.ward,
        province_name: provinceName, district_name: districtName, ward_name: wardName,
      }
    : null

  // The carriers are asked once the address has stopped changing for a moment.
  const addressKey = address ? JSON.stringify(address) : ''
  const asked = useDebounced(addressKey, 500)
  const preview = useAsync(
    () => (open && asked ? previewDeliveryQuote(orderId, JSON.parse(asked) as DeliveryAddress) : Promise.resolve(null)),
    [orderId, open, asked],
  )
  const fresh = !!addressKey && asked === addressKey && !preview.loading
  const services = fresh ? preview.data?.services ?? [] : []
  const savedService = quote.data?.chosenService
  const cheapest: ShippingService | null = [...services].sort((a, b) => a.fee - b.fee)[0] ?? null
  const service = services.find((s) => picked && isService(s, picked.carrier, picked.code))
    ?? services.find((s) => savedService && isService(s, savedService.carrier, savedService.code))
    ?? cheapest

  const days = useMemo(() => pickupDays(), [])
  const activeDay = days.includes(day) ? day : days[0] ?? ''
  const slots = activeDay ? slotsOn(activeDay) : []
  const chosenSlot = slots.find((s) => Date.parse(s.start) === slot) ?? null
  const pickupPhoneOk = PHONE.test(pickupPhone.trim())

  const current: DeliveryMethod = method ?? quote.data?.chosen ?? 'DELIVERY'
  const canSave = current === 'DELIVERY' ? !!address && !!service : !!chosenSlot && pickupPhoneOk

  const qd = quote.data
  const fee = current === 'PICKUP' ? 0 : service?.fee ?? null
  const total = current === 'PICKUP' ? qd?.options.PICKUP.totalDue ?? null : service?.totalDue ?? null
  // The total of the choice saved on the order, priced again now. A saved service the carrier no longer offers has none.
  const savedGone = qd?.chosen === 'DELIVERY' && !qd.chosenService
  const savedTotal = qd?.chosen === 'PICKUP' ? qd.options.PICKUP.totalDue : qd?.chosenService?.totalDue ?? null
  const willChange = !saved && savedTotal !== null && total !== null && total !== savedTotal
  const feeChanged = saved && seen !== null && savedTotal !== null && savedTotal !== seen
  // Once saved, the summary shows what the server priced the saved choice at.
  const shown = saved && savedTotal !== null ? savedTotal : total
  const shownFee = saved && savedTotal !== null ? (qd?.chosen === 'PICKUP' ? 0 : qd?.chosenService?.fee ?? fee) : fee

  const run = async (job: Job) => {
    if (busy) return
    setBusy(true)
    setErr('')
    try {
      await job()
    } catch (e) {
      setErr(orderErrorKey(e))
      const code = (e as { code?: string }).code ?? ''
      if (code === 'SERVICE_NOT_AVAILABLE') {
        setPicked(null)
        await preview.reload()
      }
      if (RELOAD_ON.includes(code)) await q.reload()
    } finally {
      setBusy(false)
    }
  }

  const save = () =>
    run(async () => {
      setSeen(total)
      if (current === 'DELIVERY') {
        if (!address || !service) return
        await chooseDelivery(orderId, { method: 'DELIVERY', address, carrier: service.carrier, service_code: service.code })
      } else {
        if (!chosenSlot) return
        await chooseDelivery(orderId, {
          method: 'PICKUP', pickup_slot_start: chosenSlot.start, pickup_slot_end: chosenSlot.end,
          contact_phone: pickupPhone.trim(), ...(f.receiver.trim() ? { receiver: f.receiver.trim() } : {}),
        })
      }
      await Promise.all([q.reload(), quote.reload()])
      setSaved(true)
    })

  if (!id || Number.isNaN(orderId) || (q.error && !order)) {
    return (
      <Page label="Delivery" width={720}>
        <div className="vh-panel" style={{ alignItems: 'flex-start' }}>
          <span className="vh-eyebrow">{t('np.eyebrow')}</span>
          <h1 className="vh-h1">{t('np.title')}</h1>
          <p className="vh-lede">{q.error ? errText(t, orderErrorKey(q.error)) : t('np.lede')}</p>
          <Link to={ORDER_HREF} className="vh-btn vh-btn--primary">{t('np.cta')}</Link>
        </div>
      </Page>
    )
  }
  if (!order) {
    return (
      <Page label="Delivery" width={720}>
        <p className="vh-lede" role="status">{t('co.loading')}</p>
      </Page>
    )
  }

  const dayLabel = (d: string) => noonOf(d).toLocaleDateString(locale, { weekday: 'short', day: 'numeric', month: 'short', timeZone: WORKSHOP_TZ })
  const hm = (iso: string) => new Date(iso).toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit', timeZone: WORKSHOP_TZ })
  const date = (iso: string) => new Date(iso).toLocaleDateString(locale, { weekday: 'short', day: 'numeric', month: 'short' })
  const simulated = [...services, ...(qd?.services ?? [])].some((s) => s.mode === 'MOCK')
  const deliveryFrom = cheapest?.fee ?? qd?.options.DELIVERY.fee ?? null
  const fallback = current === 'DELIVERY' && (service ? service.fallback : !!qd?.fallback)

  return (
    <Page label="Delivery" width={1200}>
      <div className="ov">
        <div className="vh-head-text">
          <span className="vh-eyebrow">{t('dl.eyebrow', { id: order.code })}</span>
          <h1 className="vh-h1">{t('dl.title')}</h1>
        </div>

        <div className="vh-cols">
          <section className="vh-col vh-panel" style={{ flex: '999 1 520px' }}>
            {!open ? (
              <div className="vh-stack">
                <div className="vh-callout vh-callout--amber"><b>{t('dl.notOpen')}</b><span>{t('dl.notOpenBody')}</span></div>
                <Link to={orderPath(order.id, 'review')} className="vh-btn vh-btn--white vh-btn--md">{t('dl.viewOrder')}</Link>
              </div>
            ) : (
              <>
                <p className="vh-lede">{t('dl.lede')}</p>
                {quote.error != null && !qd && <p className="lg-error" role="alert">{errText(t, orderErrorKey(quote.error))}</p>}
                {savedGone && !saved && (
                  <div className="vh-callout vh-callout--amber" role="alert"><span>{t('dl.savedGone')}</span></div>
                )}

                <div className="vh-stack" style={{ gap: 10 }}>
                  <h2 className="vh-h2">{t('dl.method')}</h2>
                  <div className="vh-choice-grid" role="radiogroup" aria-label={t('dl.method')}>
                    {(['DELIVERY', 'PICKUP'] as const).map((m) => (
                      <button
                        key={m}
                        role="radio"
                        aria-checked={current === m}
                        className={`vh-choice${current === m ? ' on' : ''}`}
                        disabled={busy}
                        onClick={() => { setMethod(m); setSaved(false) }}
                      >
                        <span className="vh-choice-name">{t(`dl.m.${m}`)}</span>
                        <span className="vh-choice-sub">
                          {m === 'PICKUP' ? t('dl.free') : deliveryFrom !== null ? t('dl.fromFee', { fee: fmt(deliveryFrom) }) : '–'}
                        </span>
                      </button>
                    ))}
                  </div>
                </div>

                <div className="vh-stack" style={{ gap: 12 }}>
                  <h2 className="vh-h2">{t(current === 'DELIVERY' ? 'dl.address' : 'dl.pickup')}</h2>
                  <div className="vh-form-grid">
                    <label className="vh-stack" style={{ gap: 6 }}>
                      <span className="vh-label">{t('dl.receiver')}</span>
                      <input className="vh-input" autoComplete="name" maxLength={150} value={f.receiver} onChange={(e) => set({ receiver: e.target.value })} />
                    </label>
                    {current === 'DELIVERY' ? (
                      <label className="vh-stack" style={{ gap: 6 }}>
                        <span className="vh-label">{t('dl.phone')}</span>
                        <input className="vh-input" type="tel" autoComplete="tel" value={f.phone} onChange={(e) => set({ phone: e.target.value })} />
                      </label>
                    ) : (
                      <label className="vh-stack" style={{ gap: 6 }}>
                        <span className="vh-label">{t('dl.pickupPhone')}</span>
                        <input className="vh-input" type="tel" autoComplete="tel" value={pickupPhone} onChange={(e) => { setPickupPhone(e.target.value); setSaved(false) }} />
                      </label>
                    )}
                  </div>
                  {(current === 'DELIVERY' ? f.phone.trim() && !phoneOk : pickupPhone.trim() && !pickupPhoneOk) && (
                    <span className="lg-error" role="alert">{t('dl.phoneInvalid')}</span>
                  )}

                  {current === 'DELIVERY' ? (
                    <>
                      <label className="vh-stack" style={{ gap: 6 }}>
                        <span className="vh-label">{t('dl.street')}</span>
                        <input className="vh-input" autoComplete="street-address" maxLength={255} value={f.street} onChange={(e) => set({ street: e.target.value })} />
                      </label>
                      <div className="vh-form-grid vh-form-grid--160">
                        <label className="vh-stack" style={{ gap: 6 }}>
                          <span className="vh-label">{t('dl.province')}</span>
                          <select className="vh-select" value={f.province} disabled={!provinces.data} onChange={(e) => set({ province: e.target.value, district: '', ward: '' })}>
                            <option value="">{t('dl.pickProvince')}</option>
                            {provinces.data?.map((p) => <option key={p.code} value={p.code}>{p.name}</option>)}
                          </select>
                        </label>
                        <label className="vh-stack" style={{ gap: 6 }}>
                          <span className="vh-label">{t('dl.district')}</span>
                          <select className="vh-select" value={f.district} disabled={!f.province || !districts.data?.length} onChange={(e) => set({ district: e.target.value, ward: '' })}>
                            <option value="">{t('dl.pickDistrict')}</option>
                            {districts.data?.map((p) => <option key={p.code} value={p.code}>{p.name}</option>)}
                          </select>
                        </label>
                        <label className="vh-stack" style={{ gap: 6 }}>
                          <span className="vh-label">{t('dl.ward')}</span>
                          <select className="vh-select" value={f.ward} disabled={!f.district || !wards.data?.length} onChange={(e) => set({ ward: e.target.value })}>
                            <option value="">{t('dl.pickWard')}</option>
                            {wards.data?.map((p) => <option key={p.code} value={p.code}>{p.name}</option>)}
                          </select>
                        </label>
                      </div>
                      {placesErr != null && (
                        <div className="vh-callout vh-callout--red" role="alert">
                          <span>{t('dl.placesErr')}</span>
                          <button className="vh-btn vh-btn--ghost vh-btn--md" onClick={() => void Promise.all([provinces.reload(), districts.reload(), wards.reload()])}>
                            {t('dl.retry')}
                          </button>
                        </div>
                      )}

                      <div className="vh-stack" style={{ gap: 8 }}>
                        <span className="vh-label">{t('dl.services')}</span>
                        {!address ? (
                          <span className="vh-fine">{t('dl.servicesHint')}</span>
                        ) : !fresh ? (
                          <span className="vh-fine" role="status">{t('dl.servicesLoading')}</span>
                        ) : preview.error != null ? (
                          <p className="lg-error" role="alert">{errText(t, orderErrorKey(preview.error))}</p>
                        ) : !services.length ? (
                          <span className="vh-fine">{t('dl.noServices')}</span>
                        ) : (
                          <div className="ov-opts" role="radiogroup" aria-label={t('dl.services')}>
                            {services.map((s) => {
                              const on = !!service && isService(service, s.carrier, s.code)
                              return (
                                <button
                                  key={`${s.carrier}:${s.code}`}
                                  role="radio"
                                  aria-checked={on}
                                  className={`ov-opt${on ? ' on' : ''}`}
                                  disabled={busy}
                                  onClick={() => { setPicked({ carrier: s.carrier, code: s.code }); setSaved(false) }}
                                >
                                  <span className="ov-opt-name">{s.carrier} · {s.name}</span>
                                  <span className="ov-opt-sub">
                                    {s.fallback ? t('dl.fallback') : s.eta ? t('dl.eta', { date: date(s.eta) }) : t('dl.noEta')}
                                  </span>
                                  <span className="vh-mono">{fmt(s.fee)}</span>
                                </button>
                              )
                            })}
                          </div>
                        )}
                        {simulated && <span className="vh-fine">{t('dl.mockNote')}</span>}
                      </div>
                    </>
                  ) : (
                    <>
                      <span className="vh-fine">{t('dl.pickupLede')}</span>
                      <label className="vh-stack" style={{ gap: 6 }}>
                        <span className="vh-label">{t('dl.day')}</span>
                        <select className="vh-select" value={activeDay} onChange={(e) => { setDay(e.target.value); setSlot(0); setSaved(false) }}>
                          {days.map((d) => <option key={d} value={d}>{dayLabel(d)}</option>)}
                        </select>
                      </label>
                      <div className="vh-stack" style={{ gap: 6 }}>
                        <span className="vh-label">{t('dl.time')}</span>
                        {slots.length ? (
                          <div className="vh-choice-grid" role="radiogroup" aria-label={t('dl.time')}>
                            {slots.map((s) => {
                              const on = Date.parse(s.start) === slot
                              return (
                                <button
                                  key={s.start}
                                  role="radio"
                                  aria-checked={on}
                                  className={`vh-choice${on ? ' on' : ''}`}
                                  disabled={busy}
                                  onClick={() => { setSlot(Date.parse(s.start)); setSaved(false) }}
                                >
                                  <span className="vh-choice-name">{t('dl.slotRange', { start: hm(s.start), end: hm(s.end) })}</span>
                                </button>
                              )
                            })}
                          </div>
                        ) : (
                          <span className="vh-fine">{t('dl.noSlots')}</span>
                        )}
                      </div>
                    </>
                  )}
                </div>

                {err && <p className="lg-error" role="alert">{errText(t, err)}</p>}
                {willChange && (
                  <div className="vh-callout vh-callout--amber" role="status">
                    <b>{t('dl.willChange', { before: fmt(savedTotal), after: fmt(total) })}</b>
                    <span>{t('dl.willChangeBody')}</span>
                  </div>
                )}
                {saved && (
                  <div className={`vh-callout vh-callout--${feeChanged ? 'amber' : 'green'}`} role="status">
                    <b>{t('dl.saved')}</b>
                    <span>
                      {feeChanged && seen !== null && savedTotal !== null
                        ? t('dl.feeChanged', { before: fmt(seen), after: fmt(savedTotal) })
                        : t('dl.savedBody')}
                    </span>
                  </div>
                )}
                <div className="or-actions">
                  <Link to={orderPath(order.id, 'review')} className="vh-btn vh-btn--ghost vh-btn--md">{t('dl.viewOrder')}</Link>
                  {saved && <Link to={orderPath(order.id, 'payment')} className="vh-btn vh-btn--primary vh-btn--md">{t('fp.continue')}</Link>}
                  <button className="vh-btn vh-btn--primary vh-btn--md" disabled={busy || !canSave} onClick={() => void save()}>
                    {t(busy ? 'dl.saving' : 'dl.save')}
                  </button>
                </div>
              </>
            )}
          </section>

          <aside className="vh-aside" style={{ flex: '1 1 320px' }}>
            <div className="pay-preview">
              <OrderPreview order={order} />
            </div>
            <div className="ov-rail-body">
              <span className="ov-rail-title">{t('dl.summary')}</span>
              <div className="vh-rows">
                <div className="vh-row vh-row--mono"><span style={{ fontFamily: 'inherit' }}>{t('dl.balance')}</span><span>{qd ? fmt(qd.balance) : '–'}</span></div>
                <div className="vh-row vh-row--mono"><span style={{ fontFamily: 'inherit' }}>{t('dl.shipping')}</span><span>{shownFee !== null ? fmt(shownFee) : '–'}</span></div>
              </div>
              <div className="vh-total-row">
                <span>{t('dl.total')}</span>
                <span style={{ fontSize: 24 }}>{shown !== null ? fmt(shown) : '–'}</span>
              </div>
              {fallback && <span className="vh-fine">{t('dl.fallbackNote')}</span>}
            </div>
          </aside>
        </div>
      </div>
    </Page>
  )
}
