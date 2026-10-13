import { useEffect, useState } from 'react'
import Page from '../../components/layout/Page'
import { NoOrder, OrderTimeline, SpecRows } from '../../components/ui/OrderParts'
import PaperSheet from '../../components/ui/PaperSheet'
import { ORDER_HREF } from '../../constants'
import { LAYOUTS, layoutById } from '../../constants/catalog'
import { useT, useTn } from '../../i18n'
import { Link, orderPath } from '../../router/router'
import { updateOrder, useOrder } from '../../store/store'
import type { LayoutId } from '../../types'
import { depositOf, fmt, fontScale } from '../../utils/format'
import './order.css'

type Phase = 'gen' | 'review' | 'pending' | 'rejected' | 'accepted' | 'done'

const STEP_KEYS = ['steps.placed', 'steps.sketch', 'steps.review', 'steps.deposit', 'steps.writing', 'steps.delivered']
const STEP_IDX: Record<Phase, number> = { gen: 1, review: 1, pending: 2, rejected: 2, accepted: 3, done: 4 }

const STATUS_KEY: Record<Phase, string> = {
  gen: 'or.status.gen',
  review: 'or.status.review',
  pending: 'status.Pending',
  rejected: 'status.Rejected',
  accepted: 'or.status.accepted',
  done: '',
}

export default function OrderReview({ id }: { id: string | null }) {
  const t = useT()
  const tn = useTn()
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
    : order.status === 'Rejected' ? 'rejected'
    : order.status === 'Accepted' ? 'accepted'
    : 'done'
  const progress = phase === 'gen' ? g : 1
  const cur = layoutById(variant)
  const len = sp.text.length || 12
  const scale = 1 + ((seed % 3) - 1) * 0.06
  const fs = fontScale(len) * scale
  const stage =
    progress < 0.25 ? t('or.parsing')
    : progress < 0.5 ? t('or.fitting')
    : progress < 0.75 ? t('or.planning')
    : t('or.rendering')
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
    { k: t('or.format'), v: `${tn(sp.type)}, ${sp.size}` },
    { k: t('or.contentRow'), v: sp.img ? t(sp.mode === 'draw' ? 'or.handDrawn' : 'or.uploaded') : t('or.fontSuffix', { name: tn(sp.fontName) }) },
    { k: t('or.paper'), v: tn(sp.paper) },
    { k: t('or.pen'), v: tn(sp.pen) },
    { k: t('or.ink'), v: tn(sp.ink) },
    { k: t('or.qty'), v: String(sp.qty) },
    { k: t('or.robotTime'), v: t('or.perPiece', { n: sp.mins || 4 }) },
    { k: t('or.total'), v: fmt(order.total) },
  ]

  return (
    <Page label="Order Review">
      <div className="ov">
      <div className="vh-head">
        <div className="vh-head-text">
          <span className="vh-eyebrow">{t('tk.order', { id: order.id })} · {phase === 'done' ? t(`status.${order.status}`) : t(STATUS_KEY[phase])}</span>
          <h1 className="vh-h1">{t(`or.title.${phase}`)}</h1>
        </div>
        <OrderTimeline labels={STEP_KEYS.map((k) => t(k))} idx={STEP_IDX[phase]} />
      </div>

      <div className="vh-cols">
        <section className="vh-col" style={{ flex: '999 1 560px', gap: 20 }}>
          <div className="or-stage">
            <PaperSheet
              spec={sp}
              layout={cur}
              height={sp.land ? '48%' : '82%'}
              maxWidth="90%"
              fs={fs}
              shadow="0 30px 60px var(--sh-55)"
              reveal={phase === 'gen' ? g : 1}
              style={{ position: 'relative' }}
            >
              {phase === 'gen' && <div className="or-nib" style={{ left: `${(g * 100).toFixed(1)}%` }} aria-hidden="true" />}
            </PaperSheet>
          </div>

          {phase === 'gen' && (
            <div className="or-progress">
              <div><span>{stage}</span><span className="vh-mono">{pct}</span></div>
              <div className="or-bar"><div style={{ width: pct }} /></div>
            </div>
          )}

          {phase === 'review' && (
            <div className="vh-stack" style={{ gap: 10 }}>
              <span className="vh-label">{t('or.layout')}</span>
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
                    <span>{tn(v.name)}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </section>

        <aside className="vh-aside">
          <div className="ov-rail-body">
          <span className="ov-rail-title">{t('or.details')}</span>
          <SpecRows rows={rows} />

          {phase === 'gen' && (
            <p className="or-copy">
              {t('or.genCopy', { font: tn(sp.fontName), pen: tn(sp.pen), paper: tn(sp.paper) })}
            </p>
          )}

          {phase === 'review' && (
            <>
              <div className="vh-stack" style={{ gap: 10 }}>
                <label className="vh-label" htmlFor="or-note">{t('or.noteLabel')}</label>
                <textarea
                  id="or-note"
                  className="vh-textarea"
                  rows={3}
                  value={note}
                  placeholder={t('or.notePh')}
                  onChange={(e) => setNote(e.target.value)}
                />
              </div>
              <div className="or-actions">
                <button className="vh-btn vh-btn--ghost vh-btn--md" onClick={regenerate}>
                  {t('or.regen')}
                </button>
                <button className="vh-btn vh-btn--primary vh-btn--md" onClick={approve}>
                  {t('or.send')}
                </button>
              </div>
            </>
          )}

          {phase === 'pending' && (
            <div className="vh-callout vh-callout--amber">
              <b>{t('or.pendingTitle')}</b>
              <span>{t('or.pendingBody')}</span>
            </div>
          )}

          {phase === 'rejected' && (
            <>
              <div className="vh-callout vh-callout--red">
                <b>{t('or.rejectedTitle')}</b>
                <span>{(order.rejectReasons ?? []).map((r) => tn(r)).join(', ') || t('or.noReason')}</span>
                <span className="or-by">{order.staff ?? t('or.studio')}</span>
              </div>
              <Link to={ORDER_HREF} className="vh-btn vh-btn--primary">{t('or.newOrder')}</Link>
            </>
          )}

          {phase === 'accepted' && (
            <>
              <div className="vh-callout vh-callout--teal">
                <b>{t('or.acceptedTitle')}</b>
                <span>{t('or.acceptedNote')}</span>
                <span className="or-by">{order.staff ?? t('or.studio')}</span>
              </div>
              <div className="vh-total-row">
                <span>{t('or.depositDue')}</span>
                <span style={{ fontSize: 24 }}>{fmt(deposit)}</span>
              </div>
              <Link to={orderPath(order.id, 'deposit')} className="vh-btn vh-btn--primary">{t('or.payDeposit')}</Link>
            </>
          )}

          {phase === 'done' && (
            <>
              <div className="vh-callout vh-callout--green">
                <b>{t('or.depositPaid', { status: t(`status.${order.status}`) })}</b>
                <span>{t('or.inQueue')}</span>
              </div>
              <Link to={orderPath(order.id, 'result')} className="vh-btn vh-btn--white vh-btn--md">
                {['Written', 'Rewriting', 'Shipped', 'Delivered'].includes(order.status) ? t('or.viewPhotos') : t('or.preview')}
              </Link>
            </>
          )}
          </div>
        </aside>
      </div>
      </div>
    </Page>
  )
}
