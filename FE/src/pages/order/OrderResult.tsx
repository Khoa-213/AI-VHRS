import { useState } from 'react'
import Page from '../../components/layout/Page'
import { NoOrder, OrderTimeline, SpecRows } from '../../components/ui/OrderParts'
import PaperSheet from '../../components/ui/PaperSheet'
import { REWRITE_REASONS, layoutById } from '../../constants/catalog'
import { Link, navigate, orderPath } from '../../router/router'
import { setStatus, useOrder } from '../../store/store'
import { depositOf, fmt } from '../../utils/format'
import './order.css'
import { useViewer } from './useViewer'

const STEPS = ['Order placed', 'AI sketch', 'Staff review', 'Deposit', 'Written', 'Shipped']

const STATUS_LABEL: Record<string, string> = {
  Written: 'Written · awaiting your approval',
  Rewriting: 'Rewriting',
  Shipped: 'Shipped',
  Delivered: 'Delivered',
}
const TITLE: Record<string, string> = {
  Written: 'Your piece is written.',
  Rewriting: 'Writing it again.',
  Shipped: 'On its way to you.',
  Delivered: 'Delivered.',
}

export default function OrderResult({ id }: { id: string | null }) {
  const order = useOrder(id)
  const view = useViewer(!!order)
  const [rewriteOpen, setRewriteOpen] = useState(false)
  const [reasons, setReasons] = useState<string[]>([])
  const [note, setNote] = useState('')
  const [photoDate] = useState(() => new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short' }))

  if (!order) return <NoOrder label="Order Result" />

  const sp = order.spec
  const layout = layoutById(order.layout)
  const used = (order.rewrites ?? 0) >= 1
  // Before the robot has written anything, this page previews the result.
  const status = ['Written', 'Rewriting', 'Shipped', 'Delivered'].includes(order.status) ? order.status : 'Written'
  const shipped = status === 'Shipped' || status === 'Delivered'
  const version = used && status !== 'Rewriting' ? 'REWRITE #1' : 'ORIGINAL'
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
    { k: 'Format', v: sp.type },
    { k: 'Paper', v: sp.paper },
    { k: 'Ink', v: sp.ink },
    { k: 'Quantity', v: String(sp.qty) },
    { k: 'Due on delivery', v: remain },
  ]

  return (
    <Page label="Order Result">
      <div className="vh-head">
        <div className="vh-head-text">
          <span className="vh-eyebrow">Order {order.id} · {STATUS_LABEL[status]}</span>
          <h1 className="vh-h1">{TITLE[status]}</h1>
        </div>
        <OrderTimeline labels={STEPS} idx={shipped ? 5 : 4} />
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
                <span>Written by Fairino FR3</span>
              </div>
            </div>

            <div className="rs-badge vh-mono"><i />STAFF PHOTO · {version} · FULL SHEET</div>

            <div className="rs-zoom">
              <button aria-label="Zoom out" onClick={() => view.zoomBy(1 / 1.25)}>−</button>
              <span className="rs-pct" ref={view.zoom}>100%</span>
              <button aria-label="Zoom in" onClick={() => view.zoomBy(1.25)}>+</button>
              <span className="rs-sep" />
              <button className="rs-reset" aria-label="Reset view" onClick={view.reset}>Reset</button>
            </div>
            <span className="rs-help">Drag to rotate 360° · pinch or scroll to zoom · double-click to reset</span>

            {status === 'Rewriting' && (
              <div className="rs-overlay">
                <b><i className="vh-pulse vh-pulse--orange" />Rewriting in progress</b>
                <span>The FR3 is writing a fresh copy. Staff will send new photos when it’s done.</span>
              </div>
            )}
          </div>
        </section>

        <aside className="vh-aside">
          <div className="rs-who">
            <span className="rs-who-av">M</span>
            <div>
              <b>Minh · AI-VHRS Studio</b>
              <span>{used ? 'Rewrite photos' : 'Photos'} · {photoDate} · 3 shots</span>
            </div>
          </div>
          <p className="rs-note">
            {used && status !== 'Rewriting'
              ? 'Here’s the rewritten copy with your notes applied. Take a look before we ship.'
              : 'Fresh off the FR3 — ink is dry and every piece passed QC. Check the close-up, then approve or request a rewrite.'}
          </p>
          <SpecRows rows={rows} />

          {status === 'Written' && !rewriteOpen && (
            <>
              <button className="vh-btn vh-btn--primary" onClick={() => navigate(orderPath(order.id, 'final-payment'))}>
                Looks perfect — pay &amp; ship
              </button>
              <button
                className="vh-btn vh-btn--ghost vh-btn--md"
                style={{ height: 52, color: used ? 'var(--t6)' : 'var(--t1)' }}
                disabled={used}
                onClick={() => setRewriteOpen(true)}
              >
                Request rewrite
                <span
                  className="rs-chip"
                  style={{ color: used ? 'var(--t5)' : 'var(--good-solid-fg)', background: used ? 'var(--fx-08)' : 'var(--good-solid)' }}
                >
                  {used ? 'USED' : '1 FREE'}
                </span>
              </button>
              <span className="vh-fine">
                {used
                  ? 'Your free rewrite has been used. Contact the studio for further changes.'
                  : 'One free rewrite per order — the arm writes a brand-new copy.'}
              </span>
            </>
          )}

          {status === 'Written' && rewriteOpen && (
            <div className="rs-rewrite">
              <b>What should we fix?</b>
              <div className="rs-reasons">
                {REWRITE_REASONS.map((r) => (
                  <button key={r} className={`rs-reason${reasons.includes(r) ? ' on' : ''}`} onClick={() => toggle(r)}>{r}</button>
                ))}
              </div>
              <textarea
                className="vh-textarea"
                rows={3}
                value={note}
                placeholder="Tell the studio what to change (optional)"
                onChange={(e) => setNote(e.target.value)}
              />
              <div className="or-actions">
                <button className="vh-btn vh-btn--ghost vh-btn--sm" style={{ flex: 1, height: 48 }} onClick={() => setRewriteOpen(false)}>
                  Cancel
                </button>
                <button className="vh-btn vh-btn--primary vh-btn--sm" style={{ flex: 1.6, height: 48 }} disabled={!reasons.length} onClick={confirmRewrite}>
                  Use free rewrite
                </button>
              </div>
            </div>
          )}

          {status === 'Rewriting' && (
            <div className="vh-callout vh-callout--orange">
              <b>Free rewrite requested</b>
              <span>
                {(order.rewriteReasons ?? []).join(' · ')}
                {order.rewriteNote ? ` — “${order.rewriteNote}”` : ''}. Usually ready within 24 hours.
              </span>
            </div>
          )}

          {shipped && (
            <>
              <div className="vh-callout vh-callout--green">
                <b>Approved · shipping now</b>
                <span>Remaining {remain} is due on delivery. Tracking will be sent to your phone.</span>
              </div>
              <Link to="/" className="vh-btn vh-btn--ghost vh-btn--md">Back to home</Link>
            </>
          )}
        </aside>
      </div>
    </Page>
  )
}
