import { useState } from 'react'
import Page from '../../components/layout/Page'
import OrderPreview from '../../components/ui/OrderPreview'
import { MethodLogos } from '../../components/ui/PaymentLogos'
import { ORDER_HREF } from '../../constants'
import { useAsync } from '../../hooks/useAsync'
import { useT } from '../../i18n'
import { Link, orderPath } from '../../router/router'
import {
  getOrder, listPayments, mockCheckout, orderErrorKey, startDeposit, type Gateway, type Payment,
} from '../../services/orders'
import type { Job } from '../../services/async'
import { useProfile } from '../../store/store'
import { fmt } from '../../utils/format'
import './order.css'

const GATEWAYS: { id: Gateway; logo: string; name: string }[] = [
  { id: 'VNPAY', logo: 'vnpay', name: 'VNPay' },
  { id: 'MOMO', logo: 'momo', name: 'MoMo' },
]

/** Pays the deposit. The gateway is a mock: it moves no money, and the backend labels every payment `MOCK`. */
export default function Deposit({ id }: { id: string | null }) {
  const t = useT()
  const profile = useProfile()
  const orderId = Number(id)
  const [payment, setPayment] = useState<Payment | null>(null)
  const [failed, setFailed] = useState(false)
  // After a successful mock payment the webhook lands first, so the order is asked again until it is confirmed.
  const q = useAsync(() => getOrder(orderId), [orderId], (o) => (payment && o?.status === 'AWAITING_DEPOSIT' && !failed ? 3000 : undefined))
  const pays = useAsync(() => listPayments(orderId), [orderId])
  const order = q.data
  const paid = !!order && order.status !== 'AWAITING_DEPOSIT' && order.status !== 'QUOTED' && order.depositAmount !== null
  const [gateway, setGateway] = useState<Gateway>(profile.payMethod === 'momo' ? 'MOMO' : 'VNPAY')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const run = async (job: Job) => {
    if (busy) return
    setBusy(true)
    setErr('')
    try {
      await job()
    } catch (e) {
      setErr(orderErrorKey(e))
    } finally {
      setBusy(false)
    }
  }

  if (!id || Number.isNaN(orderId) || (q.error && !order)) {
    return (
      <Page label="Deposit" width={720}>
        <div className="vh-panel" style={{ alignItems: 'flex-start' }}>
          <span className="vh-eyebrow">{t('np.eyebrow')}</span>
          <h1 className="vh-h1">{t('np.title')}</h1>
          <p className="vh-lede">{q.error ? t(orderErrorKey(q.error)) : t('np.lede')}</p>
          <Link to={ORDER_HREF} className="vh-btn vh-btn--primary">{t('np.cta')}</Link>
        </div>
      </Page>
    )
  }
  if (!order) {
    return (
      <Page label="Deposit" width={720}>
        <p className="vh-lede" role="status">{t('co.loading')}</p>
      </Page>
    )
  }

  const total = order.total ?? 0
  const deposit = order.depositAmount ?? 0
  const waiting = order.status === 'AWAITING_DEPOSIT'
  const pending = payment ?? pays.data?.find((p) => p.status === 'PENDING') ?? null

  const start = () =>
    run(async () => {
      setFailed(false)
      setPayment(await startDeposit(orderId, gateway))
      await pays.reload()
    })

  const finish = (result: 'SUCCESS' | 'FAILED') =>
    run(async () => {
      if (!pending) return
      await mockCheckout(pending.id, result)
      setFailed(result === 'FAILED')
      setPayment(null)
      await Promise.all([q.reload(), pays.reload()])
    })

  return (
    <Page label="Deposit" width={1200}>
      <div className="ov">
        <div className="vh-head-text">
          <span className="vh-eyebrow">{t('dp.eyebrow', { id: order.code })}</span>
          <h1 className="vh-h1">{t(paid ? 'dp.title.paid' : 'dp.title')}</h1>
        </div>

        <div className="vh-cols">
          <section className="vh-col vh-panel" style={{ flex: '999 1 520px' }}>
            {waiting ? (
              <>
                <div className="vh-callout vh-callout--amber" role="note">
                  <b>{t('dp.mockTitle')}</b>
                  <span>{t('dp.mockBody')}</span>
                </div>

                <div className="vh-stack">
                  <h2 className="vh-h2">{t('dp.method')}</h2>
                  <p className="vh-lede">{t('dp.lede')}</p>
                </div>
                <div className="vh-choice-grid vh-choice-grid--170" role="radiogroup" aria-label={t('dp.method')}>
                  {GATEWAYS.map((g) => (
                    <button
                      key={g.id}
                      role="radio"
                      aria-checked={gateway === g.id}
                      className={`vh-choice${gateway === g.id ? ' on' : ''}`}
                      disabled={!!pending || busy}
                      onClick={() => setGateway(g.id)}
                    >
                      <MethodLogos id={g.logo} />
                      <span className="vh-choice-name">{g.name}</span>
                    </button>
                  ))}
                </div>

                {err && <p className="lg-error" role="alert">{t(err)}</p>}
                {failed && <p className="lg-error" role="status">{t('dp.failed')}</p>}

                {!pending ? (
                  <button className="vh-btn vh-btn--primary" disabled={busy} onClick={() => void start()}>
                    {t(busy ? 'pay.processing' : 'dp.start', { amount: fmt(deposit) })}
                  </button>
                ) : (
                  <div className="vh-stack" style={{ gap: 12 }}>
                    <div className="vh-callout vh-callout--teal">
                      <b>{t('dp.mockCheckout')}</b>
                      <span>{t('dp.mockCheckoutBody', { amount: fmt(pending.amount) })}</span>
                    </div>
                    <div className="or-actions">
                      <button className="vh-btn vh-btn--ghost vh-btn--md" disabled={busy} onClick={() => void finish('FAILED')}>{t('dp.simFail')}</button>
                      <button className="vh-btn vh-btn--primary vh-btn--md" disabled={busy} onClick={() => void finish('SUCCESS')}>{t('dp.simPay')}</button>
                    </div>
                  </div>
                )}
                <span className="vh-fine">{t('dp.refund')}</span>
              </>
            ) : paid ? (
              <div className="pay-done">
                <span className="pay-done-icon">
                  <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M20 6 9 17l-5-5" />
                  </svg>
                </span>
                <h2>{t('dp.received')}</h2>
                <p>{t('dp.receivedBody', { amount: fmt(deposit), id: order.code })}</p>
                <div className="pay-done-actions">
                  <Link to={orderPath(order.id, 'review')} className="vh-btn vh-btn--white vh-btn--md">{t('dp.viewOrder')}</Link>
                  <Link to="/" className="vh-btn vh-btn--ghost vh-btn--md">{t('dp.home')}</Link>
                </div>
              </div>
            ) : (
              <div className="vh-stack">
                <p className="vh-lede">{t('dp.notReady')}</p>
                <Link to={orderPath(order.id, 'review')} className="vh-btn vh-btn--white vh-btn--md">{t('dp.viewOrder')}</Link>
              </div>
            )}

            {!!pays.data?.length && (
              <div className="vh-stack" style={{ gap: 8 }}>
                <span className="vh-label">{t('dp.history')}</span>
                <div className="vh-rows">
                  {pays.data.map((p) => (
                    <div key={p.id} className="vh-row vh-row--mono">
                      <span style={{ fontFamily: 'inherit' }}>{p.gateway} · {t(`pst.${p.status}`)} · {t('dp.mockTag')}</span>
                      <span>{fmt(p.amount)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>

          <aside className="vh-aside" style={{ flex: '1 1 320px' }}>
            <div className="pay-preview">
              <OrderPreview order={order} />
            </div>
            <div className="ov-rail-body">
              <span className="ov-rail-title">{order.code}</span>
              <div className="vh-rows">
                <div className="vh-row vh-row--mono"><span style={{ fontFamily: 'inherit' }}>{t('dp.orderTotal')}</span><span>{fmt(total)}</span></div>
                <div className="vh-row vh-row--mono"><span style={{ fontFamily: 'inherit' }}>{t('dp.dueDelivery')}</span><span>{fmt(Math.max(0, total - deposit))}</span></div>
              </div>
              <div className="vh-total-row">
                <span>{t('dp.depositRow')}{order.depositPct !== null ? ` · ${order.depositPct}%` : ''}</span>
                <span>{fmt(deposit)}</span>
              </div>
            </div>
          </aside>
        </div>
      </div>
    </Page>
  )
}
