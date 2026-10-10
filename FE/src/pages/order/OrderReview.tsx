import { useEffect, useState } from 'react'
import Page from '../../components/layout/Page'
import { NoOrder, OrderTimeline, SpecRows } from '../../components/ui/OrderParts'
import PaperSheet from '../../components/ui/PaperSheet'
import { LAYOUTS, layoutById } from '../../constants/catalog'
import { Link, orderPath } from '../../router/router'
import { updateOrder, useOrder } from '../../store/store'
import type { LayoutId } from '../../types'
import { depositOf, fmt, fontScale } from '../../utils/format'
import './order.css'

type Phase = 'gen' | 'review' | 'pending' | 'accepted' | 'done'

const STEPS = ['Order placed', 'AI sketch', 'Staff review', 'Deposit', 'Writing', 'Delivered']
const STEP_IDX: Record<Phase, number> = { gen: 1, review: 1, pending: 2, accepted: 3, done: 4 }

const STATUS_LABEL: Record<Phase, string> = {
  gen: 'Generating sketch',
  review: 'Awaiting your review',
  pending: 'Pending',
  accepted: 'Accepted — deposit due',
  done: '',
}
const TITLE: Record<Phase, string> = {
  gen: 'Sketching your order…',
  review: 'Review your sketch.',
  pending: 'Waiting for staff.',
  accepted: 'Approved. One step left.',
  done: 'You’re in the queue.',
}

export default function OrderReview({ id }: { id: string | null }) {
  const order = useOrder(id)
  const status = order?.status
  const [sketchDone, setSketchDone] = useState(false)
  const [g, setG] = useState(0)
  const [run, setRun] = useState(0)
  const [seed, setSeed] = useState(0)
  const [variant, setVariant] = useState<LayoutId>(order?.layout ?? 'classic')
  const [note, setNote] = useState('')

  // The AI sketch "renders" for a few seconds, then waits for the customer.
  useEffect(() => {
    if (status !== 'Sketching' || sketchDone) return
    const t0 = Date.now()
    const iv = window.setInterval(() => {
      const p = Math.min(1, (Date.now() - t0) / 3600)
      setG(p)
      if (p >= 1) {
        window.clearInterval(iv)
        setSketchDone(true)
      }
    }, 50)
    return () => window.clearInterval(iv)
  }, [run, status, sketchDone])

  if (!order) return <NoOrder label="Order Review" />

  const sp = order.spec
  const phase: Phase =
    order.status === 'Sketching' ? (sketchDone ? 'review' : 'gen')
    : order.status === 'Pending' ? 'pending'
    : order.status === 'Accepted' ? 'accepted'
    : 'done'
  const progress = phase === 'gen' ? g : 1
  const cur = layoutById(variant)
  const len = sp.text.length || 12
  const scale = 1 + ((seed % 3) - 1) * 0.06
  const fs = fontScale(len) * scale
  const strokes = sp.img ? 140 + ((seed * 7) % 40) : Math.round(len * 2.6 + 12)
  const stage =
    progress < 0.25 ? 'Parsing content'
    : progress < 0.5 ? 'Fitting single-line font'
    : progress < 0.75 ? 'Planning 6-DoF pen trajectory'
    : 'Rendering sketch on paper'
  const pct = `${Math.round(progress * 100)}%`
  const deposit = depositOf(order.total)

  const regenerate = () => {
    setSeed((s) => s + 1)
    setG(0)
    setSketchDone(false)
    setRun((r) => r + 1)
  }
  const approve = () => updateOrder(order.id, { status: 'Pending', layout: variant, note })

  const rows = [
    { k: 'Format', v: `${sp.type} · ${sp.size}` },
    { k: 'Content', v: sp.img ? (sp.mode === 'draw' ? 'Hand-drawn' : 'Uploaded image') : `${sp.fontName} font` },
    { k: 'Paper', v: sp.paper },
    { k: 'Pen', v: sp.pen },
    { k: 'Ink', v: sp.ink },
    { k: 'Quantity', v: String(sp.qty) },
    { k: 'Total', v: fmt(order.total) },
  ]

  return (
    <Page label="Order Review">
      <div className="vh-head">
        <div className="vh-head-text">
          <span className="vh-eyebrow">Order {order.id} · {phase === 'done' ? order.status : STATUS_LABEL[phase]}</span>
          <h1 className="vh-h1">{TITLE[phase]}</h1>
        </div>
        <OrderTimeline labels={STEPS} idx={STEP_IDX[phase]} />
      </div>

      <div className="vh-cols">
        <section className="vh-col" style={{ flex: '999 1 560px', gap: 16 }}>
          <div className="or-stage">
            <div className="or-grid" />
            <PaperSheet
              spec={sp}
              layout={cur}
              height={sp.land ? '48%' : '82%'}
              maxWidth="90%"
              fs={fs}
              shadow="0 30px 60px rgba(0,0,0,.55)"
              reveal={phase === 'gen' ? g : 1}
              style={{ position: 'relative' }}
            >
              {phase === 'gen' && <div className="or-nib" style={{ left: `${(g * 100).toFixed(1)}%` }} aria-hidden="true" />}
            </PaperSheet>
            <div className="or-badge vh-mono">
              <span style={{ background: phase === 'gen' ? '#ff5a3c' : '#4ade80' }} />
              {phase === 'gen' ? 'AI SKETCH · RENDERING' : `AI SKETCH · ${cur.name.toUpperCase()}`}
            </div>
            {phase === 'gen' && (
              <div className="or-progress">
                <div><span>{stage}</span><span className="vh-mono">{pct}</span></div>
                <div className="or-bar"><div style={{ width: pct }} /></div>
              </div>
            )}
          </div>

          {phase === 'review' && (
            <div className="vh-stack" style={{ gap: 10 }}>
              <span className="vh-label">AI layout options</span>
              <div className="or-variants">
                {LAYOUTS.map((v) => (
                  <button key={v.id} className={`or-variant${v.id === variant ? ' on' : ''}`} onClick={() => setVariant(v.id)}>
                    <div className="or-variant-stage">
                      <PaperSheet
                        spec={{ ...sp, text: sp.text.length > 40 ? sp.text.slice(0, 40) + '…' : sp.text }}
                        layout={v}
                        height={sp.land ? '50%' : '86%'}
                        maxWidth="90%"
                        fs={fs}
                      />
                    </div>
                    <span>{v.name}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </section>

        <aside className="vh-aside">
          <SpecRows rows={rows} />
          <div className="vh-metrics">
            <div className="vh-metric"><b>{strokes}</b><span>Strokes</span></div>
            <div className="vh-metric"><b>{Math.round(strokes * 0.32)}</b><span>Pen lifts</span></div>
            <div className="vh-metric"><b>{sp.mins || 4} min</b><span>Per piece</span></div>
          </div>

          {phase === 'gen' && (
            <p className="or-copy">
              The AI is fitting your content to the {sp.fontName} single-line font, {sp.pen} and {sp.paper}, then planning the robot’s pen path.
            </p>
          )}

          {phase === 'review' && (
            <>
              <div className="vh-stack" style={{ gap: 10 }}>
                <span className="vh-label">Notes for revision (optional)</span>
                <textarea
                  className="vh-textarea"
                  rows={3}
                  value={note}
                  placeholder="e.g. Make the text slightly larger, add more space at the top"
                  onChange={(e) => setNote(e.target.value)}
                />
              </div>
              <div className="or-actions">
                <button className="vh-btn vh-btn--ghost vh-btn--md" style={{ flex: 1, height: 52 }} onClick={regenerate}>
                  Regenerate
                </button>
                <button className="vh-btn vh-btn--primary vh-btn--md" style={{ flex: 1.6, height: 52 }} onClick={approve}>
                  Approve &amp; send to staff
                </button>
              </div>
            </>
          )}

          {phase === 'pending' && (
            <div className="vh-callout vh-callout--amber">
              <b><i className="vh-pulse" />Pending staff review</b>
              <span>Our studio checks every sketch before the arm writes it. Staff usually respond within 2 hours (8:00–21:00).</span>
            </div>
          )}

          {phase === 'accepted' && (
            <>
              <div className="vh-callout vh-callout--teal">
                <b>Accepted by staff</b>
                <span>“Sketch looks great — ready for the FR3.” — {order.staff ?? 'AI-VHRS Studio'}</span>
              </div>
              <div className="vh-total-row">
                <span>Deposit due (30%)</span>
                <span style={{ fontSize: 24 }}>{fmt(deposit)}</span>
              </div>
              <Link to={orderPath(order.id, 'deposit')} className="vh-btn vh-btn--primary">Pay deposit →</Link>
            </>
          )}

          {phase === 'done' && (
            <>
              <div className="vh-callout vh-callout--green">
                <b>Deposit paid · {order.status}</b>
                <span>Your order is in the robot queue. We’ll notify you when writing starts.</span>
              </div>
              <Link to={orderPath(order.id, 'result')} className="vh-btn vh-btn--white vh-btn--md">
                {['Written', 'Rewriting', 'Shipped', 'Delivered'].includes(order.status) ? 'View finished photos →' : 'Preview result page'}
              </Link>
            </>
          )}
        </aside>
      </div>
    </Page>
  )
}
