import { useEffect, useState } from 'react'
import Page from '../../components/layout/Page'
import OrderPreview from '../../components/ui/OrderPreview'
import { MethodLogos } from '../../components/ui/PaymentLogos'
import { ORDER_HREF } from '../../constants'
import { useAsync } from '../../hooks/useAsync'
import { useLocale, useT } from '../../i18n'
import { Link, orderPath } from '../../router/router'
import {
  getGateways, getOrder, listPayments, mockCheckout, orderErrorKey, refreshPayment, startDeposit, type Gateway, type Payment, errText,
} from '../../services/orders'
import type { Job } from '../../services/async'
import { useProfile } from '../../store/store'
import { fmt } from '../../utils/format'
import './order.css'

const GATEWAY_META: Record<Gateway, { logo: string; name: string }> = {
  VNPAY: { logo: 'vnpay', name: 'VNPay' },
  MOMO: { logo: 'momo', name: 'MoMo' },
  PAYOS: { logo: 'vietqr', name: 'VietQR' },
}

const expired = (p: Payment, now: number) => !!p.payUrlExpiresAt && now >= Date.parse(p.payUrlExpiresAt)

/**
 * Pays the deposit. The gateways and their mode come from the backend: a MOCK payment is settled here with the
 * simulated buttons, a real one (SANDBOX or LIVE) sends the customer to the gateway's page, which brings them back to
 * /payment/result. The order only moves when the gateway's webhook reaches the backend.
 */
export default function Deposit({ id }: { id: string | null }) {
  const t = useT()
  const locale = useLocale()
  const profile = useProfile()
  const orderId = Number(id)
  const [payment, setPayment] = useState<Payment | null>(null)
  const [failed, setFailed] = useState(false)
  const pays = useAsync(() => listPayments(orderId), [orderId])
  const open = payment ?? pays.data?.find((p) => p.status === 'PENDING') ?? null
  // While a payment is open the webhook can land at any moment, so the order is asked again until it moves.
  const q = useAsync(() => getOrder(orderId), [orderId], (o) => (open && o?.status === 'AWAITING_DEPOSIT' && !failed ? 4000 : undefined))
  const gws = useAsync(getGateways, [])
  const order = q.data
  const paid = !!order && order.status !== 'AWAITING_DEPOSIT' && order.status !== 'QUOTED' && order.depositAmount !== null
  const enabled = (gws.data ?? []).filter((g) => g.enabled)
  const preferred: Gateway = profile.payMethod === 'momo' ? 'MOMO' : 'VNPAY'
  const [picked, setPicked] = useState<Gateway | null>(null)
  const gateway = picked && enabled.some((g) => g.gateway === picked) ? picked
    : enabled.find((g) => g.gateway === preferred)?.gateway ?? enabled[0]?.gateway ?? null
  const mode = enabled.find((g) => g.gateway === gateway)?.mode
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [checked, setChecked] = useState(false)
  const [copied, setCopied] = useState('')
  const [now, setNow] = useState(() => Date.now())

  // A real payment link has a deadline; the clock only ticks while one is open.
  const deadline = open?.payUrlExpiresAt
  useEffect(() => {
    if (!deadline) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [deadline])

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
          <p className="vh-lede">{q.error ? errText(t, orderErrorKey(q.error)) : t('np.lede')}</p>
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
  const mockOpen = open?.mode === 'MOCK' ? open : null
  // A real payment that is still usable, on the gateway the customer has selected.
  const realOpen = open && open.mode !== 'MOCK' && open.payUrl && open.gateway === gateway && !expired(open, now) ? open : null
  const realExpired = !!open && open.mode !== 'MOCK' && open.gateway === gateway && expired(open, now)
  const refund = pays.data?.some((p) => p.needsRefund)
  const time = (iso: string) => new Date(iso).toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' })
  const left = realOpen?.payUrlExpiresAt ? Math.max(0, Math.ceil((new Date(realOpen.payUrlExpiresAt).getTime() - now) / 60000)) : null

  const start = () =>
    run(async () => {
      if (!gateway) return
      setFailed(false)
      setChecked(false)
      const p = await startDeposit(orderId, gateway)
      if (p.payUrl) {
        // The gateway's own page takes over; it sends the customer back to /payment/result.
        window.location.assign(p.payUrl)
        return
      }
      setPayment(p)
      await pays.reload()
    })

  const finish = (result: 'SUCCESS' | 'FAILED') =>
    run(async () => {
      if (!mockOpen) return
      await mockCheckout(mockOpen.id, result)
      setFailed(result === 'FAILED')
      setPayment(null)
      await Promise.all([q.reload(), pays.reload()])
    })

  // Asks the gateway directly. A late webhook is normal, so an unreachable gateway is not a failed payment.
  const check = () =>
    run(async () => {
      if (!open) return
      try {
        await refreshPayment(open.id)
      } catch (e) {
        if ((e as { code?: string }).code !== 'GATEWAY_UNAVAILABLE') throw e
      }
      setChecked(true)
      setPayment(null)
      await Promise.all([q.reload(), pays.reload()])
    })

  const copy = (label: string, value: string | null) => {
    if (!value) return
    void navigator.clipboard?.writeText(value).then(() => setCopied(label), () => undefined)
  }

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
                {mode === 'MOCK' && (
                  <div className="vh-callout vh-callout--amber" role="note">
                    <b>{t('dp.mockTitle')}</b>
                    <span>{t('dp.mockBody')}</span>
                  </div>
                )}
                {mode === 'SANDBOX' && (
                  <div className="vh-callout vh-callout--amber" role="note">
                    <b>{t('dp.sandboxTitle')}</b>
                    <span>{t('dp.sandboxBody')}</span>
                  </div>
                )}
                {refund && (
                  <div className="vh-callout vh-callout--red" role="alert">
                    <b>{t('dp.refundTitle')}</b>
                    <span>{t('dp.refundBody')}</span>
                  </div>
                )}

                <div className="vh-stack">
                  <h2 className="vh-h2">{t('dp.method')}</h2>
                  <p className="vh-lede">{t('dp.lede')}</p>
                </div>
                {gws.loading && !gws.data && <p className="vh-fine" role="status">{t('co.loading')}</p>}
                {gws.error != null && !gws.data && <p className="lg-error" role="alert">{errText(t, orderErrorKey(gws.error))}</p>}
                {gws.data && !enabled.length && <p className="lg-error" role="alert">{t('dp.noGateway')}</p>}
                {!!enabled.length && (
                  <div className="vh-choice-grid vh-choice-grid--170" role="radiogroup" aria-label={t('dp.method')}>
                    {enabled.map((g) => (
                      <button
                        key={g.gateway}
                        role="radio"
                        aria-checked={gateway === g.gateway}
                        className={`vh-choice${gateway === g.gateway ? ' on' : ''}`}
                        disabled={!!mockOpen || busy}
                        onClick={() => setPicked(g.gateway)}
                      >
                        <MethodLogos id={GATEWAY_META[g.gateway].logo} />
                        <span className="vh-choice-name">{GATEWAY_META[g.gateway].name}</span>
                        <span className="vh-choice-sub">{t(`dp.via.${g.gateway}`)}</span>
                      </button>
                    ))}
                  </div>
                )}

                {err && <p className="lg-error" role="alert">{errText(t, err)}</p>}
                {failed && <p className="lg-error" role="status">{t('dp.failed')}</p>}

                {mockOpen ? (
                  <div className="vh-stack" style={{ gap: 12 }}>
                    <div className="vh-callout vh-callout--teal">
                      <b>{t('dp.mockCheckout')}</b>
                      <span>{t('dp.mockCheckoutBody', { amount: fmt(mockOpen.amount) })}</span>
                    </div>
                    <div className="or-actions">
                      <button className="vh-btn vh-btn--ghost vh-btn--md" disabled={busy} onClick={() => void finish('FAILED')}>{t('dp.simFail')}</button>
                      <button className="vh-btn vh-btn--primary vh-btn--md" disabled={busy} onClick={() => void finish('SUCCESS')}>{t('dp.simPay')}</button>
                    </div>
                  </div>
                ) : realOpen ? (
                  <div className="vh-stack" style={{ gap: 12 }}>
                    <div className="vh-callout vh-callout--teal">
                      <b>{t('dp.openTitle', { gateway: GATEWAY_META[realOpen.gateway].name })}</b>
                      <span>
                        {realOpen.payUrlExpiresAt
                          ? t('dp.openBody', { time: time(realOpen.payUrlExpiresAt), min: left ?? 0 })
                          : t('dp.openBodyNoTime')}
                      </span>
                    </div>
                    {realOpen.bank && (
                      <div className="vh-stack" style={{ gap: 8 }}>
                        <span className="vh-label">{t('dp.bankTitle')}</span>
                        <div className="vh-rows">
                          <div className="vh-row"><span>{t('dp.bankName')}</span><span>{realOpen.bank.accountName ?? '–'}</span></div>
                          <div className="vh-row vh-row--mono">
                            <span style={{ fontFamily: 'inherit' }}>{t('dp.bankAccount')}</span>
                            <span className="dp-copy">
                              {realOpen.bank.accountNumber ?? '–'}
                              <button className="vh-link" onClick={() => copy('account', realOpen.bank?.accountNumber ?? null)}>{t(copied === 'account' ? 'dp.copied' : 'dp.copy')}</button>
                            </span>
                          </div>
                          <div className="vh-row vh-row--mono"><span style={{ fontFamily: 'inherit' }}>{t('dp.bankAmount')}</span><span>{fmt(realOpen.bank.amount)}</span></div>
                          <div className="vh-row vh-row--mono">
                            <span style={{ fontFamily: 'inherit' }}>{t('dp.bankContent')}</span>
                            <span className="dp-copy">
                              {realOpen.bank.content ?? '–'}
                              <button className="vh-link" onClick={() => copy('content', realOpen.bank?.content ?? null)}>{t(copied === 'content' ? 'dp.copied' : 'dp.copy')}</button>
                            </span>
                          </div>
                        </div>
                        <span className="vh-fine">{t('dp.bankExact')}</span>
                      </div>
                    )}
                    <div className="or-actions">
                      <button className="vh-btn vh-btn--ghost vh-btn--md" disabled={busy} onClick={() => void check()}>{t(busy ? 'pay.processing' : 'dp.check')}</button>
                      <button className="vh-btn vh-btn--primary vh-btn--md" disabled={busy} onClick={() => realOpen.payUrl && window.location.assign(realOpen.payUrl)}>
                        {t('dp.continue', { gateway: GATEWAY_META[realOpen.gateway].name })}
                      </button>
                    </div>
                    {checked && <p className="vh-fine" role="status">{t('dp.stillPending')}</p>}
                  </div>
                ) : (
                  <>
                    {realExpired && <p className="vh-fine" role="status">{t('dp.expired')}</p>}
                    <button className="vh-btn vh-btn--primary" disabled={busy || !gateway} onClick={() => void start()}>
                      {t(busy ? 'pay.processing' : realExpired ? 'dp.newLink' : 'dp.start', { amount: fmt(deposit) })}
                    </button>
                  </>
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
                      <span style={{ fontFamily: 'inherit' }}>
                        {GATEWAY_META[p.gateway]?.name ?? p.gateway} · {t(`pst.${p.status}`)}
                        {p.mode === 'MOCK' ? ` · ${t('dp.mockTag')}` : p.mode === 'SANDBOX' ? ` · ${t('dp.sandboxTag')}` : ''}
                        {p.needsRefund ? ` · ${t('dp.refundTag')}` : ''}
                      </span>
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
