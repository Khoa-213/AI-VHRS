import { useEffect, useRef, useState } from 'react'
import Page from '../../components/layout/Page'
import { NoOrder } from '../../components/ui/OrderParts'
import PaperSheet from '../../components/ui/PaperSheet'
import PaymentMethods, { EMPTY_CARD, methodReady, type CardFields } from '../../components/ui/PaymentMethods'
import { CITIES, PAY_METHODS, PROMOS } from '../../constants/catalog'
import { useT, useTn } from '../../i18n'
import { Link, orderPath } from '../../router/router'
import { setStatus, useOrder } from '../../store/store'
import type { ShipTo } from '../../types'
import { depositOf, fmt } from '../../utils/format'
import './order.css'

export default function FinalPayment({ id }: { id: string | null }) {
  const t = useT()
  const tn = useTn()
  const order = useOrder(id)
  const [method, setMethod] = useState<string | null>(null)
  const [card, setCard] = useState<CardFields>(EMPTY_CARD)
  const [busy, setBusy] = useState(false)
  const [ship, setShip] = useState<ShipTo>(() => {
    const a = order?.shipTo
    return {
      name: a?.name ?? order?.name ?? '',
      phone: a?.phone ?? order?.phone ?? '',
      street: a?.street ?? order?.address ?? '',
      ward: a?.ward ?? '',
      city: a?.city ?? 'TP. Hồ Chí Minh',
      note: a?.note ?? '',
    }
  })
  const [promo, setPromo] = useState('')
  const [applied, setApplied] = useState<string | null>(null)
  const [promoErr, setPromoErr] = useState(false)
  const timer = useRef<number | undefined>(undefined)
  useEffect(() => () => window.clearTimeout(timer.current), [])

  if (!order) return <NoOrder label="Final Payment" />

  const paid = ['Shipped', 'Delivered'].includes(order.status)
  const sp = order.spec

  const total = order.total
  const deposit = depositOf(total)
  const P = applied ? PROMOS[applied] : undefined
  const shipFee = P?.kind === 'ship' || total >= 500000 ? 0 : 30000
  const disc = P?.kind === 'pct' ? Math.round(((total - deposit) * (P.v ?? 0)) / 1000) * 1000 : 0
  const due = total - deposit + shipFee - disc
  const vat = Math.round(total - total / 1.08)

  const addrOk = !!(ship.name.trim() && ship.phone.replace(/\D/g, '').length >= 9 && ship.street.trim().length >= 4)
  const ready = addrOk && methodReady(method, card)
  const m = PAY_METHODS.find((x) => x.id === method)
  const missing = !addrOk
    ? t('fp.missAddr')
    : !m ? t('fp.missMethod')
    : !ready ? t('fp.missCard')
    : ''

  const set = (patch: Partial<ShipTo>) => setShip((s) => ({ ...s, ...patch }))

  const pay = () => {
    if (!ready || busy) return
    setBusy(true)
    timer.current = window.setTimeout(() => {
      setStatus(order.id, 'Shipped', { finalMethod: method ?? undefined, finalPaid: due, promo: applied, shipTo: ship })
      setBusy(false)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    }, 1400)
  }

  const applyPromo = () => {
    const c = promo.trim().toUpperCase()
    if (!c) return
    if (PROMOS[c]) {
      setApplied(c)
      setPromoErr(false)
      setPromo(c)
    } else {
      setPromoErr(true)
    }
  }

  const payLabel = busy
    ? t('pay.processing')
    : !m ? t('pay.select')
    : m.kind === 'qr' ? t('pay.transferred', { amount: fmt(due) })
    : m.kind === 'wallet' ? t('pay.payWith', { amount: fmt(due), name: tn(m.name) })
    : t('pay.pay', { amount: fmt(due) })

  const lines = [
    { k: t('fp.subtotal'), v: fmt(total), c: 'var(--t2)' },
    { k: t('fp.vat'), v: fmt(vat), c: 'var(--t5)' },
    { k: t('fp.depositPaid'), v: '−' + fmt(deposit), c: 'var(--good)' },
    { k: t('fp.shipping'), v: shipFee ? fmt(shipFee) : t('fp.free'), c: 'var(--t2)' },
    ...(disc ? [{ k: t('fp.promoLine', { code: applied ?? '' }), v: '−' + fmt(disc), c: 'var(--good)' }] : []),
  ]

  const addrShort = [ship.street, ship.ward, ship.city].filter((x) => x.trim()).join(', ')
  const specLine = [sp.type, sp.paper, sp.pen, sp.ink].filter(Boolean).map(tn).concat(t('fp.pcs', { n: sp.qty || 1 })).join(' · ')

  return (
    <Page label="Final Payment" width={1200}>
      <div className="vh-head-text">
        <span className="vh-eyebrow">{t('fp.eyebrow', { id: order.id })}</span>
        <h1 className="vh-h1">{t(paid ? 'fp.title.paid' : 'fp.title')}</h1>
      </div>

      <div className="vh-cols">
        <div className="vh-col" style={{ flex: '999 1 560px' }}>
          {!paid ? (
            <>
              <section className="vh-panel vh-panel--md">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 12 }}>
                  <h2 className="vh-h2 vh-h2--sm">{t('fp.yourOrder')}</h2>
                  <Link to={orderPath(order.id, 'result')} className="vh-link">{t('fp.viewPhotos')}</Link>
                </div>
                <div className="pay-order">
                  <div className="pay-thumb">
                    <PaperSheet spec={sp} height={sp.land ? '50%' : '86%'} maxWidth="84%" shadow="0 8px 14px var(--sh-5)" />
                  </div>
                  <div className="pay-order-text">
                    <span className="pay-order-title">{tn(order.title)}</span>
                    <span className="pay-order-spec">{specLine}</span>
                    <span className="vh-chip vh-chip--good pay-tag">{t('fp.writtenTag')}</span>
                  </div>
                  <span className="pay-order-total">{fmt(total)}</span>
                </div>
              </section>

              <section className="vh-panel vh-panel--md">
                <div className="vh-stack" style={{ gap: 4 }}>
                  <h2 className="vh-h2 vh-h2--sm">{t('fp.addrTitle')}</h2>
                  <span style={{ fontSize: 14, color: 'var(--t5)' }}>{t('fp.addrLede')}</span>
                </div>
                <div className="vh-form-grid">
                  <label className="vh-label">{t('fp.fullName')}
                    <input className="vh-input" placeholder="Nguyễn Văn A" autoComplete="name" value={ship.name} onChange={(e) => set({ name: e.target.value })} />
                  </label>
                  <label className="vh-label">{t('fp.phone')}
                    <input className="vh-input" placeholder="0901 234 567" inputMode="tel" autoComplete="tel" value={ship.phone} onChange={(e) => set({ phone: e.target.value })} />
                  </label>
                </div>
                <label className="vh-label">{t('fp.street')}
                  <input className="vh-input" placeholder={t('fp.streetPh')} autoComplete="street-address" value={ship.street} onChange={(e) => set({ street: e.target.value })} />
                </label>
                <div className="vh-form-grid vh-form-grid--160">
                  <label className="vh-label">{t('fp.ward')}
                    <input className="vh-input" placeholder="Phường / Xã" value={ship.ward} onChange={(e) => set({ ward: e.target.value })} />
                  </label>
                  <label className="vh-label">{t('fp.city')}
                    <select className="vh-select" value={ship.city} onChange={(e) => set({ city: e.target.value })}>
                      {CITIES.map((c) => <option key={c} value={c}>{tn(c)}</option>)}
                    </select>
                  </label>
                </div>
                <label className="vh-label">{t('fp.note')}
                  <input className="vh-input" placeholder={t('fp.notePh')} value={ship.note} onChange={(e) => set({ note: e.target.value })} />
                </label>
              </section>

              <section className="vh-panel vh-panel--md">
                <div className="vh-stack" style={{ gap: 4 }}>
                  <h2 className="vh-h2 vh-h2--sm">{t('fp.methodTitle')}</h2>
                  <span style={{ fontSize: 14, color: 'var(--t5)' }}>{t('fp.methodLede')}</span>
                </div>
                <PaymentMethods
                  method={method}
                  onPick={setMethod}
                  card={card}
                  onCard={setCard}
                  orderId={order.id}
                  noteSuffix="TT"
                  amountLabel={fmt(due)}
                />
              </section>
            </>
          ) : (
            <section className="vh-panel vh-panel--md">
              <div className="pay-done">
                <span className="pay-done-icon">
                  <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M20 6 9 17l-5-5" />
                  </svg>
                </span>
                <h2>{t('fp.done')}</h2>
                <p>
                  {t('fp.doneBody', {
                    amount: fmt(order.finalPaid ?? due),
                    method: tn(PAY_METHODS.find((x) => x.id === order.finalMethod)?.name ?? '') || t('dp.yourMethod'),
                    id: order.id,
                    addr: addrShort || t('fp.yourAddress'),
                    phone: ship.phone || t('fp.yourPhone'),
                  })}
                </p>
                <div className="pay-done-actions">
                  <Link to={orderPath(order.id, 'tracking')} className="vh-btn vh-btn--white vh-btn--md">{t('fp.trackIt')}</Link>
                  <Link to={orderPath(order.id, 'result')} className="vh-btn vh-btn--ghost vh-btn--md">{t('dp.viewOrder')}</Link>
                </div>
              </div>
            </section>
          )}
        </div>

        <aside className="vh-aside" style={{ flex: '1 1 340px', padding: 24, borderRadius: 24, boxShadow: '0 30px 60px var(--sh-35)' }}>
          <div className="vh-stack" style={{ gap: 10 }}>
            <span style={{ fontSize: 15, fontWeight: 800, color: 'var(--t1)' }}>{t('fp.promo')}</span>
            <div className="pay-promo">
              <input
                className="vh-input"
                placeholder={t('fp.promoPh')}
                value={promo}
                style={promoErr ? { borderColor: 'var(--danger)' } : undefined}
                onChange={(e) => {
                  setPromo(e.target.value)
                  setPromoErr(false)
                }}
              />
              <button className="vh-btn vh-btn--ghost vh-btn--sm" style={{ height: 48, borderRadius: 12 }} disabled={!promo.trim()} onClick={applyPromo}>
                {t('fp.apply')}
              </button>
            </div>
            {(promoErr || P) && (
              <span className="pay-msg" style={{ color: promoErr ? 'var(--danger)' : 'var(--good)' }}>
                {promoErr ? t('fp.promoBad') : t('fp.promoOk', { code: applied ?? '', label: tn(P?.label ?? '') })}
              </span>
            )}
          </div>

          <div className="pay-lines">
            {lines.map((l) => (
              <div key={l.k} className="pay-line"><span>{l.k}</span><span style={{ color: l.c }}>{l.v}</span></div>
            ))}
          </div>
          <div className="pay-due"><span>{t('fp.totalDue')}</span><span>{fmt(due)}</span></div>
          <span style={{ marginTop: -10, fontSize: 12, color: 'var(--t6)', textAlign: 'right' }}>{t('fp.vatIncl')}</span>

          {!paid && (
            <>
              <button className="vh-btn vh-btn--primary" disabled={!ready || busy} onClick={pay}>{payLabel}</button>
              {missing && <span className="pay-warn">{missing}</span>}
              <span className="vh-fine">
                {t('fp.terms', { terms: t('fp.termsLink'), privacy: t('fp.privacyLink') })}
              </span>
            </>
          )}
        </aside>
      </div>
    </Page>
  )
}
