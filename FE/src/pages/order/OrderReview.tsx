import { useEffect, useRef, useState } from 'react'
import Page from '../../components/layout/Page'
import Chat from '../../components/ui/Chat'
import OrderPreview from '../../components/ui/OrderPreview'
import { OrderTimeline, SpecRows } from '../../components/ui/OrderParts'
import { ORDER_HREF } from '../../constants'
import { STATUS_COLOR, STATUS_STEP, STEP_KEYS } from '../../constants/orderStatus'
import { useAsync } from '../../hooks/useAsync'
import { useLocale, useT } from '../../i18n'
import { Link, navigate, orderPath } from '../../router/router'
import {
  WAITING, approveQuotation, cancelOrder, decidePrivacy, getInks, getOrder, getPapers, getPens, getPrivacyPolicy, getQuotation,
  orderErrorKey, requestChanges, type Order, errText } from '../../services/orders'
import type { Job } from '../../services/async'
import { fmt } from '../../utils/format'
import MockWorkshopBar from './MockWorkshopBar'
import PrivacyDialog from './PrivacyDialog'
import './order.css'

const HAS_QUOTE = ['QUOTED', 'AWAITING_DEPOSIT', 'CONFIRMED']

export default function OrderReview({ id }: { id: string | null }) {
  const t = useT()
  const locale = useLocale()
  const orderId = Number(id)
  // Statuses that move on their own (the workshop works, the payment lands) are checked every 20 seconds.
  const q = useAsync(() => getOrder(orderId), [orderId], (o) => (o && WAITING.includes(o.status) ? 20000 : undefined))
  const order = q.data
  const status = order?.status

  const papers = useAsync(getPapers, [])
  const pens = useAsync(() => getPens(), [])
  const inks = useAsync(() => (order?.penId ? getInks(order.penId) : Promise.resolve([])), [order?.penId])
  const quote = useAsync(() => (status && HAS_QUOTE.includes(status) ? getQuotation(orderId) : Promise.resolve(null)), [orderId, status])
  const policy = useAsync(() => (status === 'AWAITING_PRIVACY' ? getPrivacyPolicy(orderId) : Promise.resolve(null)), [status])

  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [panel, setPanel] = useState<'' | 'changes' | 'cancel' | 'decline'>('')
  const [text, setText] = useState('')
  const [option, setOption] = useState<number | null>(null)
  const [pct, setPct] = useState<number | null>(null)
  const [policyOpen, setPolicyOpen] = useState(false)
  const autoOpened = useRef(false)

  // The policy opens by itself the first time the order lands on the privacy step.
  useEffect(() => {
    if (status !== 'AWAITING_PRIVACY') autoOpened.current = false
    else if (policy.data && !autoOpened.current) {
      autoOpened.current = true
      setPolicyOpen(true)
    }
  }, [status, policy.data])

  const run = async (job: Job, after?: () => void) => {
    if (busy) return
    setBusy(true)
    setErr('')
    try {
      await job()
      setPanel('')
      setText('')
      after?.()
      await q.reload()
    } catch (e) {
      setErr(orderErrorKey(e))
      if ((e as { code?: string }).code === 'STATE_CONFLICT') await q.reload()
    } finally {
      setBusy(false)
    }
  }

  if (!id || Number.isNaN(orderId) || (q.error && !order)) {
    return (
      <Page label="Order" width={720}>
        <div className="vh-panel" style={{ alignItems: 'flex-start' }}>
          <span className="vh-eyebrow">{t('np.eyebrow')}</span>
          <h1 className="vh-h1">{t('np.title')}</h1>
          <p className="vh-lede">{q.error ? errText(t, orderErrorKey(q.error)) : t('np.lede')}</p>
          <Link to={ORDER_HREF} className="vh-btn vh-btn--primary">{t('np.cta')}</Link>
        </div>
      </Page>
    )
  }
  if (!order || !status) {
    return (
      <Page label="Order" width={720}>
        <p className="vh-lede" role="status">{t('co.loading')}</p>
      </Page>
    )
  }

  const quotation = quote.data
  const multi = (quotation?.options.length ?? 0) > 1
  const chosen = multi ? (option ?? quotation?.chosenOption ?? quotation?.options[0]?.option ?? null) : null
  const quoteTotal = multi ? (quotation?.options.find((o) => o.option === chosen)?.total ?? 0) : (quotation?.finalTotal ?? 0)
  const minPct = quotation?.minDepositPct ?? 50
  const depositPct = Math.min(100, Math.max(minPct, pct ?? minPct))
  const depositNow = Math.round((quoteTotal * depositPct) / 100)
  const day = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString(locale, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }) : '–')
  const daysLeft = quotation?.validUntil ? Math.max(0, Math.ceil((new Date(quotation.validUntil).getTime() - Date.now()) / 864e5)) : null

  const paper = papers.data?.find((p) => p.id === order.paperId)
  const pen = pens.data?.find((p) => p.id === order.penId)
  const ink = inks.data?.find((i) => i.id === order.inkId)
  const money = (o: Order) =>
    o.total !== null ? fmt(o.total)
    : o.estMax !== null ? (o.estMin === o.estMax ? fmt(o.estMax) : `${fmt(o.estMin ?? 0)} – ${fmt(o.estMax)}`)
    : '–'

  const text0 = order.inputs.find((i) => i.kind === 'TEXT_CONTENT')?.text?.trim()
  const photos = order.inputs.filter((i) => i.kind === 'ORIGINAL_IMAGE').length
  const content = text0 ? (text0.length > 48 ? text0.slice(0, 48) + '…' : text0) : photos ? t(photos === 1 ? 'co.sum.photo' : 'co.sum.photos', { n: photos }) : order.inputs.some((i) => i.kind === 'CANVAS') ? t('dr.drawing') : '–'

  const rows = [
    { k: t('ov.type'), v: t(`ot.${order.type}`) },
    { k: t('or.contentRow'), v: content },
    { k: t('or.paper'), v: order.workshopSuggest && !paper ? t('co.sum.suggest') : paper?.name ?? '–' },
    { k: t('or.pen'), v: pen?.name ?? '–' },
    { k: t('or.ink'), v: ink?.name ?? '–' },
    { k: t('or.qty'), v: String(order.quantity) },
    ...(order.note ? [{ k: t('co.sum.note'), v: order.note }] : []),
    { k: t(order.total !== null ? 'or.total' : 'ov.estimate'), v: money(order) },
    ...(order.eta ? [{ k: t('ov.eta'), v: day(order.eta) }] : []),
  ]

  const confirmBox = (kind: 'cancel' | 'changes', label: string, onSend: () => void, danger = false) => (
    <div className="vh-stack" style={{ gap: 10 }}>
      <label className="vh-label" htmlFor="ov-reason">{label}</label>
      <textarea id="ov-reason" className="vh-textarea" rows={3} maxLength={kind === 'cancel' ? 500 : 2000} value={text} onChange={(e) => setText(e.target.value)} />
      <div className="or-actions">
        <button className="vh-btn vh-btn--ghost vh-btn--md" disabled={busy} onClick={() => { setPanel(''); setText('') }}>{t('ov.back')}</button>
        <button className={`vh-btn vh-btn--md ${danger ? 'vh-btn--white' : 'vh-btn--primary'}`} disabled={busy || !text.trim()} onClick={onSend}>
          {t(kind === 'cancel' ? 'ov.cancelConfirm' : 'ov.changesSend')}
        </button>
      </div>
    </div>
  )

  const cancelBlock = panel === 'cancel'
    ? confirmBox('cancel', t('ov.cancelReason'), () => void run(() => cancelOrder(orderId, text.trim())), true)
    : <button className="vh-link" onClick={() => { setPanel('cancel'); setText('') }}>{t('ov.cancel')}</button>

  return (
    <Page label="Order Review">
      {import.meta.env.DEV && <MockWorkshopBar order={order} onChange={() => void q.reload()} />}
      <div className="ov">
        <div className="vh-head">
          <div className="vh-head-text">
            <span className="vh-eyebrow">{order.code} · <span style={{ color: STATUS_COLOR[status] }}>{t(`os.${status}`)}</span></span>
            <h1 className="vh-h1">{t(`ov.title.${status}`)}</h1>
          </div>
          {status !== 'CANCELLED' && status !== 'REJECTED' && <OrderTimeline labels={STEP_KEYS.map((k) => t(k))} idx={STATUS_STEP[status]} />}
        </div>

        <div className="vh-cols">
          <section className="vh-col" style={{ flex: '999 1 560px', gap: 20 }}>
            <div className="or-stage">
              <OrderPreview order={order} sketchUrls={quotation?.sketch?.previewUrls} inkColor={ink?.hex} />
            </div>

            {quotation?.sketch && (
              <div className="vh-stack" style={{ gap: 6 }}>
                <span className="vh-label">{t('ov.sketch', { v: quotation.sketch.version })}</span>
                {quotation.sketch.approachNote && <p className="or-copy">{quotation.sketch.approachNote}</p>}
                {quotation.sketch.estimatedWritingSec !== null && (
                  <p className="or-copy">{t('ov.writingTime', { min: Math.max(1, Math.round(quotation.sketch.estimatedWritingSec / 60)) })}</p>
                )}
              </div>
            )}

            {status === 'QUOTED' && quotation && (
              <div className="vh-stack" style={{ gap: 14 }}>
                <span className="vh-label">{t('ov.quote', { v: quotation.version })}</span>
                {multi && (
                  <div className="ov-opts" role="radiogroup" aria-label={t('ov.options')}>
                    {quotation.options.map((o) => (
                      <button key={o.option} role="radio" aria-checked={o.option === chosen} className={`ov-opt${o.option === chosen ? ' on' : ''}`} onClick={() => setOption(o.option)}>
                        <span className="ov-opt-name">{t('ov.optionN', { n: o.option })}</span>
                        <span className="ov-opt-sub">{o.paper} · {o.pen} · {o.ink}</span>
                        <span className="vh-mono">{fmt(o.total)}</span>
                      </button>
                    ))}
                  </div>
                )}
                <div className="vh-rows">
                  {quotation.lines.filter((l) => !multi || l.option === chosen).map((l, i) => (
                    <div key={i} className="vh-row">
                      <span>{l.item}{l.calc ? <small className="ov-calc"> {l.calc}</small> : null}</span>
                      <span className="vh-mono">{fmt(l.amount)}</span>
                    </div>
                  ))}
                </div>
                <p className="or-copy">{quotation.note}</p>
              </div>
            )}
            {status !== 'DRAFT' && <Chat orderId={orderId} closed={['REJECTED', 'CANCELLED', 'COMPLETED'].includes(status)} />}
          </section>

          <aside className="vh-aside">
            <div className="ov-rail-body">
              <span className="ov-rail-title">{t('or.details')}</span>
              <SpecRows rows={rows} />

              {err && <p className="lg-error" role="alert">{errText(t, err)}</p>}

              {status === 'DRAFT' && (
                <Link to={`/create-order/draft/${order.id}`} className="vh-btn vh-btn--primary">{t('dr.continue')}</Link>
              )}

              {status === 'SUBMITTED' && (
                <>
                  <div className="vh-callout vh-callout--amber"><b>{t('or.pendingTitle')}</b><span>{t('or.pendingBody')}</span></div>
                  {cancelBlock}
                </>
              )}

              {status === 'NEED_INFO' && (
                <>
                  <div className="vh-callout vh-callout--amber">
                    <b>{t('co.needInfo')}</b>
                    <span>{order.infoRequestNote ?? ''}</span>
                  </div>
                  <Link to={`/create-order/draft/${order.id}`} className="vh-btn vh-btn--primary">{t('ov.editOrder')}</Link>
                  {cancelBlock}
                </>
              )}

              {status === 'REJECTED' && (
                <>
                  <div className="vh-callout vh-callout--red">
                    <b>{t('or.rejectedTitle')}</b>
                    <span>{order.rejectReason ? t(`rr.${order.rejectReason}`) : t('or.noReason')}</span>
                    {order.rejectNote && <span>{order.rejectNote}</span>}
                  </div>
                  <Link to={ORDER_HREF} className="vh-btn vh-btn--primary">{t('or.newOrder')}</Link>
                </>
              )}

              {status === 'ACCEPTED' && (
                <div className="vh-callout vh-callout--teal"><b>{t('or.acceptedTitle')}</b><span>{t('ov.acceptedBody')}</span></div>
              )}

              {status === 'AWAITING_PRIVACY' && (
                <>
                  <div className="vh-callout vh-callout--teal"><b>{t('ov.privacyNeeded')}</b><span>{t('ov.privacyBody')}</span></div>
                  {panel === 'decline' ? (
                    <div className="vh-callout vh-callout--red">
                      <b>{t('ov.declineTitle')}</b>
                      <span>{t('ov.declineBody')}</span>
                      <div className="or-actions">
                        <button className="vh-btn vh-btn--ghost vh-btn--md" disabled={busy} onClick={() => setPanel('')}>{t('ov.back')}</button>
                        <button className="vh-btn vh-btn--white vh-btn--md" disabled={busy} onClick={() => void run(() => decidePrivacy(orderId, false))}>{t('ov.declineConfirm')}</button>
                      </div>
                    </div>
                  ) : (
                    <div className="or-actions">
                      <button className="vh-btn vh-btn--ghost vh-btn--md" disabled={busy} onClick={() => setPanel('decline')}>{t('ov.decline')}</button>
                      <button className="vh-btn vh-btn--primary vh-btn--md" disabled={busy || !policy.data} onClick={() => setPolicyOpen(true)}>{t('ov.privacyRead')}</button>
                    </div>
                  )}
                  {policyOpen && policy.data && (
                    <PrivacyDialog
                      policy={policy.data}
                      busy={busy}
                      onClose={() => setPolicyOpen(false)}
                      onDecline={() => { setPolicyOpen(false); setPanel('decline') }}
                      onAgree={() => void run(() => decidePrivacy(orderId, true), () => setPolicyOpen(false))}
                    />
                  )}
                </>
              )}

              {status === 'QUOTED' && quotation && (
                <>
                  <div className="vh-rows">
                    <div className="vh-row vh-row--mono"><span style={{ fontFamily: 'inherit' }}>{t('ov.validUntil')}</span><span>{day(quotation.validUntil)}{daysLeft !== null ? ` · ${t('ov.daysLeft', { n: daysLeft })}` : ''}</span></div>
                    {quotation.eta && <div className="vh-row vh-row--mono"><span style={{ fontFamily: 'inherit' }}>{t('ov.eta')}</span><span>{day(quotation.eta)}</span></div>}
                  </div>
                  <div className="vh-stack" style={{ gap: 8 }}>
                    <label className="vh-label" htmlFor="ov-pct">
                      {t('ov.depositPct', { pct: depositPct })}
                      <input id="ov-pct" type="range" min={minPct} max={100} step={5} value={depositPct} onChange={(e) => setPct(Number(e.target.value))} />
                    </label>
                    <span className="co-fine">{t('ov.depositMin', { pct: minPct })}</span>
                  </div>
                  <div className="vh-total-row">
                    <span>{t('or.depositDue')}</span>
                    <span style={{ fontSize: 24 }}>{fmt(depositNow)}</span>
                  </div>
                  {panel === 'changes' ? (
                    confirmBox('changes', t('ov.changesLabel'), () => void run(() => requestChanges(orderId, text.trim())))
                  ) : (
                    <>
                      <button
                        className="vh-btn vh-btn--primary vh-btn--md"
                        disabled={busy || (multi && chosen === null)}
                        onClick={() => void run(
                          () => approveQuotation(orderId, { ...(multi && chosen !== null ? { option: chosen } : {}), deposit_pct: depositPct }),
                          () => navigate(orderPath(orderId, 'deposit')),
                        )}
                      >
                        {t('ov.approve')}
                      </button>
                      {quotation.pdfUrl && <a className="vh-link" href={quotation.pdfUrl} target="_blank" rel="noreferrer">{t('ov.pdf')}</a>}
                      <button className="vh-link" onClick={() => { setPanel('changes'); setText('') }}>{t('ov.changes')}</button>
                      {cancelBlock}
                    </>
                  )}
                </>
              )}

              {status === 'AWAITING_DEPOSIT' && (
                <>
                  <div className="vh-total-row">
                    <span>{t('or.depositDue')}</span>
                    <span style={{ fontSize: 24 }}>{fmt(order.depositAmount ?? 0)}</span>
                  </div>
                  <Link to={orderPath(order.id, 'deposit')} className="vh-btn vh-btn--primary">{t('or.payDeposit')}</Link>
                  {cancelBlock}
                </>
              )}

              {['CONFIRMED', 'AWAITING_ACCEPTANCE', 'AWAITING_FINAL_PAYMENT', 'READY_TO_DELIVER', 'DELIVERING', 'COMPLETED'].includes(status) && (
                <>
                  <div className="vh-callout vh-callout--green">
                    <b>{t('or.depositPaid', { status: t(`os.${status}`) })}</b>
                    <span>{t(`ps.${order.production}`)}</span>
                  </div>
                  <span className="co-fine">{t('ov.contactWorkshop')}</span>
                </>
              )}

              {status === 'CANCELLED' && (
                <>
                  <div className="vh-callout vh-callout--red"><b>{t('ov.cancelledTitle')}</b><span>{t('ov.cancelledBody')}</span></div>
                  <Link to={ORDER_HREF} className="vh-btn vh-btn--primary">{t('or.newOrder')}</Link>
                </>
              )}
            </div>
          </aside>
        </div>
      </div>
    </Page>
  )
}
