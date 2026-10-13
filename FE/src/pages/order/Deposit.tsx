import { useEffect, useRef, useState } from 'react'
import Page from '../../components/layout/Page'
import { NoOrder } from '../../components/ui/OrderParts'
import PaperSheet from '../../components/ui/PaperSheet'
import PaymentMethods, { EMPTY_CARD, methodReady, type CardFields } from '../../components/ui/PaymentMethods'
import { PAY_METHODS } from '../../constants/catalog'
import { useT, useTn } from '../../i18n'
import { Link, orderPath } from '../../router/router'
import { setStatus, useOrder } from '../../store/store'
import { depositOf, fmt } from '../../utils/format'
import './order.css'

export default function Deposit({ id }: { id: string | null }) {
  const t = useT()
  const tn = useTn()
  const order = useOrder(id)
  const [method, setMethod] = useState<string | null>(null)
  const [card, setCard] = useState<CardFields>(EMPTY_CARD)
  const [busy, setBusy] = useState(false)
  const timer = useRef<number | undefined>(undefined)
  useEffect(() => () => window.clearTimeout(timer.current), [])

  if (!order) return <NoOrder label="Deposit" />

  const paid = !['Accepted', 'Pending', 'Rejected', 'Sketching'].includes(order.status)
  const deposit = depositOf(order.total)
  const m = PAY_METHODS.find((x) => x.id === (paid ? order.depositMethod : method))
  const ready = methodReady(method, card)

  const pay = () => {
    if (!ready || busy) return
    setBusy(true)
    timer.current = window.setTimeout(() => {
      setStatus(order.id, 'Queued', { depositMethod: method ?? undefined })
      setBusy(false)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    }, 1400)
  }

  const payLabel = busy
    ? t('pay.processing')
    : !m ? t('pay.select')
    : m.kind === 'qr' ? t('pay.transferred', { amount: fmt(deposit) })
    : m.kind === 'wallet' ? t('pay.payWith', { amount: fmt(deposit), name: tn(m.name) })
    : t('pay.pay', { amount: fmt(deposit) })

  return (
    <Page label="Deposit" width={1200}>
      <div className="ov">
      <div className="vh-head-text">
        <span className="vh-eyebrow">{t('dp.eyebrow', { id: order.id })}</span>
        <h1 className="vh-h1">{t(paid ? 'dp.title.paid' : 'dp.title')}</h1>
      </div>

      <div className="vh-cols">
        <section className="vh-col vh-panel" style={{ flex: '999 1 520px' }}>
          {!paid ? (
            <>
              <div className="vh-stack">
                <h2 className="vh-h2">{t('dp.method')}</h2>
                <p className="vh-lede">{t('dp.lede')}</p>
              </div>
              <PaymentMethods
                method={method}
                onPick={setMethod}
                card={card}
                onCard={setCard}
                orderId={order.id}
                noteSuffix="COC"
                amountLabel={fmt(deposit)}
              />
              <button className="vh-btn vh-btn--primary" disabled={!ready || busy} onClick={pay}>{payLabel}</button>
              <span className="vh-fine">{t('dp.refund')}</span>
            </>
          ) : (
            <div className="pay-done">
              <span className="pay-done-icon">
                <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M20 6 9 17l-5-5" />
                </svg>
              </span>
              <h2>{t('dp.received')}</h2>
              <p>{t('dp.receivedBody', { amount: fmt(deposit), method: m ? tn(m.name) : t('dp.yourMethod'), id: order.id })}</p>
              <div className="pay-done-actions">
                <Link to={orderPath(order.id, 'review')} className="vh-btn vh-btn--white vh-btn--md">{t('dp.viewOrder')}</Link>
                <Link to="/" className="vh-btn vh-btn--ghost vh-btn--md">{t('dp.home')}</Link>
              </div>
            </div>
          )}
        </section>

        <aside className="vh-aside" style={{ flex: '1 1 320px' }}>
          <div className="pay-preview">
            <PaperSheet spec={order.spec} height={order.spec.land ? '50%' : '86%'} maxWidth="88%" shadow="0 14px 24px var(--sh-5)" />
          </div>
          <div className="ov-rail-body">
          <span className="ov-rail-title">{tn(order.title)}</span>
          <div className="vh-rows">
            <div className="vh-row vh-row--mono"><span style={{ fontFamily: 'inherit' }}>{t('dp.orderTotal')}</span><span>{fmt(order.total)}</span></div>
            <div className="vh-row vh-row--mono"><span style={{ fontFamily: 'inherit' }}>{t('dp.dueDelivery')}</span><span>{fmt(order.total - deposit)}</span></div>
          </div>
          <div className="vh-total-row">
            <span>{t('dp.depositRow')}</span>
            <span>{fmt(deposit)}</span>
          </div>
          </div>
        </aside>
      </div>
      </div>
    </Page>
  )
}
