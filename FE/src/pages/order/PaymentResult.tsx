import { useEffect, useState } from 'react'
import Page from '../../components/layout/Page'
import { useT } from '../../i18n'
import { Link, orderPath } from '../../router/router'
import { errText, getOrder, listPayments, orderErrorKey, refreshPayment, type Order } from '../../services/orders'
import { openAuth } from '../../store/authDialog'
import { useUser } from '../../store/store'
import { fmt } from '../../utils/format'
import './order.css'

/** Statuses that wait for a payment; any other status means the payment went through. */
const PAYING = ['AWAITING_DEPOSIT', 'AWAITING_FINAL_PAYMENT']
const EVERY_MS = 2500
const GIVE_UP_MS = 60_000
/** After this long the gateway is asked directly, once, in case its webhook is late. */
const REFRESH_AFTER_MS = 10_000

type State = 'checking' | 'paid' | 'failed' | 'slow' | 'error'

/**
 * Where VNPay, MoMo and payOS send the customer back (`?order_id=<id>`, payOS adds `cancelled=1`). The gateway's own
 * query parameters are never trusted: the page only reads the order and its payments until the backend, told by the
 * gateway's webhook, has moved the order on.
 */
export default function PaymentResult() {
  const t = useT()
  const user = useUser()
  const params = new URLSearchParams(window.location.search)
  const orderId = Number(params.get('order_id'))
  const cancelled = params.get('cancelled') === '1' || params.get('cancel') === 'true'
  const [state, setState] = useState<State>('checking')
  const [order, setOrder] = useState<Order | null>(null)
  const [err, setErr] = useState('')

  useEffect(() => {
    if (!orderId || !user) return
    let stop = false
    let refreshed = false
    const began = Date.now()
    const tick = async () => {
      try {
        const o = await getOrder(orderId)
        if (stop) return
        setOrder(o)
        if (!PAYING.includes(o.status)) return setState('paid')
        const pays = await listPayments(orderId)
        if (stop) return
        const last = [...pays].sort((a, b) => b.createdAt.localeCompare(a.createdAt))[0]
        if (last && (last.status === 'FAILED' || last.status === 'CANCELLED')) return setState('failed')
        const waited = Date.now() - began
        if (last?.status === 'PENDING' && last.mode !== 'MOCK' && !refreshed && (cancelled || waited >= REFRESH_AFTER_MS)) {
          refreshed = true
          // An unreachable gateway is not a failed payment: the webhook still decides.
          await refreshPayment(last.id).catch(() => undefined)
          if (!stop) window.setTimeout(() => void tick(), 0)
          return
        }
        if (cancelled && refreshed) return setState('failed')
        if (waited >= GIVE_UP_MS) return setState('slow')
        window.setTimeout(() => void tick(), EVERY_MS)
      } catch (e) {
        if (stop) return
        setErr(orderErrorKey(e))
        setState('error')
      }
    }
    void tick()
    return () => {
      stop = true
    }
  }, [orderId, user, cancelled])

  if (!orderId) {
    return (
      <Page label="Payment" width={720}>
        <div className="vh-panel" style={{ alignItems: 'flex-start' }}>
          <h1 className="vh-h1">{t('pr.noOrder')}</h1>
          <Link to="/account/orders" className="vh-btn vh-btn--primary">{t('pr.myOrders')}</Link>
        </div>
      </Page>
    )
  }

  if (!user) {
    return (
      <Page label="Payment" width={720}>
        <div className="vh-panel" style={{ alignItems: 'flex-start' }}>
          <h1 className="vh-h1">{t('pr.signIn')}</h1>
          <p className="vh-lede">{t('pr.signInBody')}</p>
          <button className="vh-btn vh-btn--primary" onClick={() => openAuth('login', window.location.pathname + window.location.search)}>{t('pr.signInBtn')}</button>
        </div>
      </Page>
    )
  }

  const deposit = order?.status === 'CONFIRMED' || order?.status === 'AWAITING_DEPOSIT'
  const back = order && PAYING.includes(order.status)
    ? (order.status === 'AWAITING_DEPOSIT' ? orderPath(orderId, 'deposit') : orderPath(orderId, 'review'))
    : orderPath(orderId, 'review')

  return (
    <Page label="Payment" width={720}>
      <div className="vh-panel" style={{ alignItems: 'flex-start' }}>
        {order && <span className="vh-eyebrow">{order.code}</span>}

        {state === 'checking' && (
          <div className="vh-stack" role="status" aria-live="polite">
            <h1 className="vh-h1">{t('pr.checking')}</h1>
            <p className="vh-lede">{t('pr.checkingBody')}</p>
          </div>
        )}

        {state === 'paid' && order && (
          <div className="pay-done">
            <span className="pay-done-icon">
              <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                <path d="M20 6 9 17l-5-5" />
              </svg>
            </span>
            <h2>{t(deposit ? 'dp.received' : 'pr.paid')}</h2>
            <p>{deposit ? t('dp.receivedBody', { amount: fmt(order.depositAmount ?? 0), id: order.code }) : t('pr.paidBody', { id: order.code })}</p>
            <div className="pay-done-actions">
              <Link to={orderPath(orderId, 'review')} className="vh-btn vh-btn--white vh-btn--md">{t('dp.viewOrder')}</Link>
            </div>
          </div>
        )}

        {state === 'failed' && (
          <div className="vh-stack">
            <h1 className="vh-h1">{t(cancelled ? 'pr.cancelled' : 'pr.failed')}</h1>
            <p className="vh-lede">{t('pr.failedBody')}</p>
            <Link to={back} className="vh-btn vh-btn--primary">{t('pr.tryAgain')}</Link>
          </div>
        )}

        {state === 'slow' && (
          <div className="vh-stack">
            <h1 className="vh-h1">{t('pr.slow')}</h1>
            <p className="vh-lede">{t('pr.slowBody')}</p>
            <Link to={orderPath(orderId, 'review')} className="vh-btn vh-btn--primary">{t('dp.viewOrder')}</Link>
          </div>
        )}

        {state === 'error' && (
          <div className="vh-stack">
            <h1 className="vh-h1">{t('pr.error')}</h1>
            <p className="lg-error" role="alert">{errText(t, err)}</p>
            <Link to={orderPath(orderId, 'review')} className="vh-btn vh-btn--primary">{t('dp.viewOrder')}</Link>
          </div>
        )}
      </div>
    </Page>
  )
}
