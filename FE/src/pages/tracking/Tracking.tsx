import { ArrowUpRight, CheckCircle, Circle, Copy } from '@phosphor-icons/react'
import { useEffect, useRef, useState } from 'react'
import Page from '../../components/layout/Page'
import { NoOrder, OrderTimeline, SpecRows } from '../../components/ui/OrderParts'
import ShipmentTimeline from '../../components/ui/ShipmentTimeline'
import { useShipmentSync } from '../../hooks/useShipmentSync'
import { useLocale, useT } from '../../i18n'
import { PACK_STEPS, PHASES, lastLog, phaseOf, shipmentOf, stageOf, trackingUrl } from '../../services/ghn'
import { Link, orderPath } from '../../router/router'
import { useOrder } from '../../store/store'
import './tracking.css'

export default function Tracking({ id }: { id: string | null }) {
  const order = useOrder(id)
  const t = useT()
  const locale = useLocale()
  const day = (iso?: string) =>
    iso ? new Date(iso).toLocaleDateString(locale, { weekday: 'long', day: 'numeric', month: 'long' }) : t('tk.tbc')
  const sync = useShipmentSync(order)
  const [copied, setCopied] = useState(false)
  const timer = useRef<number | undefined>(undefined)
  useEffect(() => () => window.clearTimeout(timer.current), [])

  if (!order) return <NoOrder label="Tracking" />

  if (!['Shipped', 'Delivered'].includes(order.status)) {
    return (
      <Page label="Tracking" width={720}>
        <div className="vh-panel" style={{ alignItems: 'flex-start' }}>
          <span className="vh-eyebrow">{t('tk.order', { id: order.id })}</span>
          <h1 className="vh-h1">{t('tk.notShippedTitle')}</h1>
          <p className="vh-lede">{t('tk.notShippedBody')}</p>
          <Link to={orderPath(order.id, 'result')} className="vh-btn vh-btn--primary">{t('tk.backToOrder')}</Link>
        </div>
      </Page>
    )
  }

  const s = shipmentOf(order)
  const stage = stageOf(order)
  const phase = phaseOf(order)
  const last = lastLog(s)
  const packedCount = s.pack.length

  const courierTitle = ['tk.title.pack', 'tk.title.pickup', 'tk.title.transit', 'tk.title.delivering'][phase] ?? 'tk.title.transit'
  const title = t(
    stage === 'done' ? 'tk.title.done'
    : stage === 'problem' ? 'tk.title.problem'
    : stage === 'courier' ? courierTitle
    : 'tk.title.pack',
  )
  const sub =
    stage === 'pack' || stage === 'book'
      ? t('tk.sub.pack', { n: packedCount, total: PACK_STEPS.length })
      : stage === 'problem'
        ? t('tk.sub.problem')
        : stage === 'done'
          ? t('tk.sub.done')
          : t('tk.sub.expected', { date: day(s.expectedAt) })

  const copy = () => {
    if (!s.ghnCode) return
    void navigator.clipboard?.writeText(s.ghnCode).then(
      () => {
        setCopied(true)
        window.clearTimeout(timer.current)
        timer.current = window.setTimeout(() => setCopied(false), 1600)
      },
      () => {},
    )
  }

  const to = order.shipTo
  const rows = [
    { k: t('tk.carrier'), v: 'Giao Hàng Nhanh (GHN)' },
    { k: t('tk.expected'), v: day(s.expectedAt) },
    { k: t('tk.deliverTo'), v: to?.name || order.name || t('tk.you') },
    { k: t('tk.address'), v: [to?.street, to?.ward, to?.city].filter(Boolean).join(', ') || order.address || t('tk.noAddr') },
    { k: t('tk.due'), v: t('tk.dueNone') },
  ]

  return (
    <Page label="Tracking" width={1200}>
      <div className="vh-head">
        <div className="vh-head-text">
          <span className="vh-eyebrow">{t('tk.order', { id: order.id })}</span>
          <h1 className="vh-h1">{title}</h1>
          <p className="vh-lede" role="status">{sub}</p>
        </div>
        <OrderTimeline labels={PHASES.map((i) => t(`phase.${i}`))} idx={stage === 'done' ? PHASES.length : phase} />
      </div>

      <div className="vh-cols">
        <section className="vh-col" aria-labelledby="tk-updates">
          {(stage === 'pack' || stage === 'book') && (
            <div className="vh-panel vh-panel--md">
              <h2 className="vh-h2 vh-h2--sm">{t('tk.packing')}</h2>
              <ul className="tk-pack">
                {PACK_STEPS.map((p) => {
                  const done = s.pack.some((m) => m.id === p.id)
                  return (
                    <li key={p.id} className={done ? 'done' : ''}>
                      {done ? <CheckCircle size={22} weight="fill" aria-hidden /> : <Circle size={22} aria-hidden />}
                      <span>{t(`pack.${p.id}`)}</span>
                      <span className="tk-sr">{t(done ? 'tk.stepDone' : 'tk.stepNotYet')}</span>
                    </li>
                  )
                })}
              </ul>
            </div>
          )}

          <div className="vh-panel vh-panel--md">
            <h2 id="tk-updates" className="vh-h2 vh-h2--sm">{t('tk.updates')}</h2>
            <ShipmentTimeline shipment={s} audience="customer" />
            {!s.logs.length && s.ghnCode && <p className="vh-fine">{t('tk.noScan')}</p>}
            {sync.error && <p className="vh-fine" role="alert">{t('tk.refreshErr')}</p>}
          </div>
        </section>

        <aside className="vh-aside" aria-label={t('tk.detailsAria')}>
          {s.ghnCode ? (
            <div className="tk-code">
              <span>{t('tk.code')}</span>
              <div>
                <b className="vh-mono">{s.ghnCode}</b>
                <button type="button" className="tk-copy" onClick={copy} aria-label={t('tk.copyAria')}>
                  <Copy size={18} aria-hidden />
                  {copied ? t('tk.copied') : t('tk.copy')}
                </button>
              </div>
            </div>
          ) : (
            <div className="tk-code">
              <span>{t('tk.code')}</span>
              <b className="tk-wait">{t('tk.codeWait')}</b>
            </div>
          )}

          <SpecRows rows={rows} />

          {last && stage !== 'done' && (
            <p className="vh-fine" style={{ textAlign: 'left' }}>
              {last.place
                ? t('tk.lastScanAt', { time: new Date(last.at).toLocaleString(locale, { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }), place: last.place })
                : t('tk.lastScan', { time: new Date(last.at).toLocaleString(locale, { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) })}
            </p>
          )}

          {s.ghnCode && (
            <a className="vh-btn vh-btn--ghost vh-btn--md" href={trackingUrl(s.ghnCode)} target="_blank" rel="noreferrer">
              {t('tk.openGhn')} <ArrowUpRight size={18} aria-hidden />
            </a>
          )}
          <Link to={orderPath(order.id, 'result')} className="vh-btn vh-btn--ghost vh-btn--md">{t('tk.viewPhotos')}</Link>
        </aside>
      </div>
    </Page>
  )
}
