import { useState } from 'react'
import Page from '../../components/layout/Page'
import { NoOrder, OrderTimeline, SpecRows } from '../../components/ui/OrderParts'
import PaperSheet from '../../components/ui/PaperSheet'
import { REWRITE_REASONS, layoutById } from '../../constants/catalog'
import { useLocale, useT, useTn } from '../../i18n'
import { Link, navigate, orderPath } from '../../router/router'
import { setStatus, useOrder } from '../../store/store'
import { depositOf, fmt } from '../../utils/format'
import './order.css'
import { useViewer } from './useViewer'

const STEP_KEYS = ['steps.placed', 'steps.sketch', 'steps.review', 'steps.deposit', 'steps.written', 'steps.shipped']

export default function OrderResult({ id }: { id: string | null }) {
  const t = useT()
  const tn = useTn()
  const locale = useLocale()
  const order = useOrder(id)
  const view = useViewer(!!order)
  const [rewriteOpen, setRewriteOpen] = useState(false)
  const [reasons, setReasons] = useState<string[]>([])
  const [note, setNote] = useState('')
  const [photoDate] = useState(() => new Date().toLocaleDateString(locale, { day: '2-digit', month: 'short' }))

  if (!order) return <NoOrder label="Order Result" />

  const sp = order.spec
  const layout = layoutById(order.layout)
  const used = (order.rewrites ?? 0) >= 1
  // Before the robot has written anything, this page previews the result.
  const status = ['Written', 'Rewriting', 'Shipped', 'Delivered'].includes(order.status) ? order.status : 'Written'
  const shipped = status === 'Shipped' || status === 'Delivered'
  const version = t(used && status !== 'Rewriting' ? 'rs.version.rewrite' : 'rs.version.original')
  const deposit = depositOf(order.total)
  const remain = fmt(order.total - deposit)

  const toggle = (r: string) => setReasons((rs) => (rs.includes(r) ? rs.filter((x) => x !== r) : [...rs, r]))
  const confirmRewrite = () => {
    if (!reasons.length) return
    setStatus(order.id, 'Rewriting', { rewrites: 1, rewriteReasons: reasons, rewriteNote: note })
    setRewriteOpen(false)
    view.reset()
  }

  const rows = [
    { k: t('rs.rowFormat'), v: tn(sp.type) },
    { k: t('rs.rowPaper'), v: tn(sp.paper) },
    { k: t('rs.rowInk'), v: tn(sp.ink) },
    { k: t('rs.rowQty'), v: String(sp.qty) },
    { k: t('rs.rowDue'), v: remain },
  ]

  return (
    <Page label="Order Result">
      <div className="vh-head">
        <div className="vh-head-text">
          <span className="vh-eyebrow">{t('tk.order', { id: order.id })} · {t(`rs.status.${status}`)}</span>
          <h1 className="vh-h1">{t(`rs.title.${status}`)}</h1>
        </div>
        <OrderTimeline labels={STEP_KEYS.map((k) => t(k))} idx={shipped ? 5 : 4} />
      </div>

      <div className="vh-cols">
        <section className="vh-col" style={{ flex: '999 1 560px', gap: 14 }}>
          <div className="rs-stage" ref={view.stage} onDoubleClick={view.reset}>
            <div className="rs-light" />
            <div
              className="rs-obj"
              ref={view.obj}
              style={{ height: sp.land ? '52%' : '86%', aspectRatio: sp.aspect }}
            >
              <PaperSheet
                spec={sp}
                layout={layout}
                height="100%"
                maxWidth="none"
                shadow="0 30px 50px var(--sh-55), 0 2px 4px var(--sh-3)"
                style={{ position: 'absolute', inset: 0, aspectRatio: 'auto', backfaceVisibility: 'hidden' }}
              >
                <div className="rs-shine" />
              </PaperSheet>
              <div className="rs-back" style={{ background: sp.paperColor, filter: 'brightness(.93)', color: sp.inkColor }}>
                <b>AI-VHRS · {order.id}</b>
                <span>{t('rs.writtenBy')}</span>
              </div>
            </div>

            <div className="rs-badge vh-mono"><i />{t('rs.badge', { version })}</div>

            <div className="rs-zoom">
              <button aria-label={t('rs.zoomOut')} onClick={() => view.zoomBy(1 / 1.25)}>−</button>
              <span className="rs-pct" ref={view.zoom}>100%</span>
              <button aria-label={t('rs.zoomIn')} onClick={() => view.zoomBy(1.25)}>+</button>
              <span className="rs-sep" />
              <button className="rs-reset" aria-label={t('rs.resetView')} onClick={view.reset}>{t('rs.reset')}</button>
            </div>
            <span className="rs-help">{t('rs.help')}</span>

            {status === 'Rewriting' && (
              <div className="rs-overlay">
                <b><i className="vh-pulse vh-pulse--orange" />{t('rs.rewritingTitle')}</b>
                <span>{t('rs.rewritingBody')}</span>
              </div>
            )}
          </div>
        </section>

        <aside className="vh-aside">
          <div className="rs-who">
            <span className="rs-who-av">M</span>
            <div>
              <b>{t('rs.who')}</b>
              <span>{t(used ? 'rs.photosRewrite' : 'rs.photos')} · {photoDate} · {t('rs.shots', { n: order.qc?.photos.length || 3 })}</span>
            </div>
          </div>
          <p className="rs-note">
            {used && status !== 'Rewriting'
              ? t('rs.noteRewritten')
              : t('rs.noteFresh')}
          </p>
          {!!order.qc?.photos.length && (
            <ul className="rs-qc" aria-label={t('rs.photosAria')}>
              {order.qc.photos.map((ph) => (
                <li key={ph.slot}>
                  <img src={ph.url} alt={t('rs.photoAlt', { slot: tn(ph.slot), id: order.id })} />
                  <span>{tn(ph.slot)}</span>
                </li>
              ))}
            </ul>
          )}
          {order.qc?.note && <p className="rs-note">{order.qc.note}</p>}
          <SpecRows rows={rows} />

          {status === 'Written' && !rewriteOpen && (
            <>
              <button className="vh-btn vh-btn--primary" onClick={() => navigate(orderPath(order.id, 'final-payment'))}>
                {t('rs.approve')}
              </button>
              <button
                className="vh-btn vh-btn--ghost vh-btn--md"
                style={{ height: 52, color: used ? 'var(--t6)' : 'var(--t1)' }}
                disabled={used}
                onClick={() => setRewriteOpen(true)}
              >
                {t('rs.requestRewrite')}
                <span
                  className="rs-chip"
                  style={{ color: used ? 'var(--t5)' : 'var(--good-solid-fg)', background: used ? 'var(--fx-08)' : 'var(--good-solid)' }}
                >
                  {t(used ? 'rs.chipUsed' : 'rs.chipFree')}
                </span>
              </button>
              <span className="vh-fine">
                {t(used ? 'rs.rewriteUsed' : 'rs.rewriteFree')}
              </span>
            </>
          )}

          {status === 'Written' && rewriteOpen && (
            <div className="rs-rewrite">
              <b>{t('rs.fix')}</b>
              <div className="rs-reasons">
                {REWRITE_REASONS.map((r) => (
                  <button key={r} className={`rs-reason${reasons.includes(r) ? ' on' : ''}`} onClick={() => toggle(r)}>{tn(r)}</button>
                ))}
              </div>
              <textarea
                className="vh-textarea"
                rows={3}
                value={note}
                placeholder={t('rs.fixPh')}
                onChange={(e) => setNote(e.target.value)}
              />
              <div className="or-actions">
                <button className="vh-btn vh-btn--ghost vh-btn--sm" style={{ flex: 1, height: 48 }} onClick={() => setRewriteOpen(false)}>
                  {t('rs.cancel')}
                </button>
                <button className="vh-btn vh-btn--primary vh-btn--sm" style={{ flex: 1.6, height: 48 }} disabled={!reasons.length} onClick={confirmRewrite}>
                  {t('rs.useFree')}
                </button>
              </div>
            </div>
          )}

          {status === 'Rewriting' && (
            <div className="vh-callout vh-callout--orange">
              <b>{t('rs.reqTitle')}</b>
              <span>
                {(order.rewriteReasons ?? []).map((r) => tn(r)).join(' · ')}
                {order.rewriteNote ? `: “${order.rewriteNote}”` : ''}. {t('rs.reqEta')}
              </span>
            </div>
          )}

          {shipped && (
            <>
              <div className="vh-callout vh-callout--green">
                <b>{t('rs.approvedTitle')}</b>
                <span>{t('rs.approvedBody', { amount: remain })}</span>
              </div>
              <Link to={orderPath(order.id, 'tracking')} className="vh-btn vh-btn--primary vh-btn--md">{t('tk.track')}</Link>
              <Link to="/" className="vh-btn vh-btn--ghost vh-btn--md">{t('dp.home')}</Link>
            </>
          )}
        </aside>
      </div>
    </Page>
  )
}
