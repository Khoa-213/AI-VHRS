import { useEffect, useRef, useState } from 'react'
import { inkMask } from '../../components/ui/PaperSheet'
import { ORDER_HREF } from '../../constants'
import { FONT_STYLES, INKS, PACKS, PAPERS, PRODUCTS, STEP_LABELS, TYPES } from '../../constants/catalog'
import { useLocale, useT, useTn } from '../../i18n'
import { Link, navigate } from '../../router/router'
import { deleteDraft, newDraftId, saveDraft, useDrafts, useUser } from '../../store/store'
import type { OrderDraft } from '../../types'
import { fmt } from '../../utils/format'
import { quote } from '../../utils/pricing'
import { draftPathFor } from '../create-order/draft'
import './drafts.css'

function ago(iso: string, locale: string) {
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' })
  const s = Math.round((new Date(iso).getTime() - Date.now()) / 1000)
  const a = Math.abs(s)
  if (a < 45) return rtf.format(0, 'second')
  if (a < 3600) return rtf.format(Math.round(s / 60), 'minute')
  if (a < 86400) return rtf.format(Math.round(s / 3600), 'hour')
  return rtf.format(Math.round(s / 86400), 'day')
}

/** Drafts grid plus ready-made designs to start from. */
export default function DraftsSection() {
  const t = useT()
  const tn = useTn()
  const locale = useLocale()
  const user = useUser()
  const drafts = useDrafts()
  const [sel, setSel] = useState<Record<string, { paper: number; pack: number }>>({})
  const [confirming, setConfirming] = useState<string | null>(null)
  const carousel = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!confirming) return
    const h = window.setTimeout(() => setConfirming(null), 4000)
    return () => window.clearTimeout(h)
  }, [confirming])

  const scrollCarousel = (d: number) => carousel.current?.scrollBy({ left: d * 340, behavior: 'smooth' })

  const useDesign = (p: (typeof PRODUCTS)[number], paperIdx: number, packIdx: number) => {
    const now = new Date().toISOString()
    const id = newDraftId()
    const draft: OrderDraft = {
      id, owner: user?.name ?? 'guest', createdAt: now, updatedAt: now,
      step: 2, maxStep: 2,
      type: p.type, mode: 'text', text: p.text,
      fontStyle: FONT_STYLES.find((f) => f.font === p.font)?.id ?? 'script',
      upload: null, strokes: 0, drawUrl: null, sizeId: 'a4', landscape: false,
      paper: PAPERS[paperIdx].id, pen: null, ink: INKS.find((i) => i.color === p.ink)?.id ?? null,
      qty: PACKS[packIdx].n, name: '', phone: '', address: '', pay: null,
    }
    saveDraft(draft)
    navigate(draftPathFor(id))
  }

  return (
    <div className="dr-section">
      <ul className="dr-list" aria-label={t('dr.listAria')}>
        {drafts.map((d) => {
          const ty = TYPES.find((x) => x.id === d.type)
          const paper = PAPERS.find((x) => x.id === d.paper)
          const ink = INKS.find((x) => x.id === d.ink)
          const q = quote(
            { type: d.type, paper: d.paper, pen: d.pen, ink: d.ink, qty: d.qty, mode: d.mode, text: d.text, hasUpload: !!d.upload, strokes: d.strokes },
            t, tn, locale,
          )
          const img = d.mode === 'draw' ? d.drawUrl : d.upload?.isImg ? d.upload.dataUrl : null
          const font = FONT_STYLES.find((f) => f.id === d.fontStyle)?.font
          const label = tn(STEP_LABELS[Math.min(3, d.step)])
          const asking = confirming === d.id
          return (
            <li key={d.id} className="dr-item">
              <div className="dr-stage">
                <div className="dr-paper" style={{ aspectRatio: ty?.aspect ?? '105/148', background: paper?.color ?? '#f4eee0' }}>
                  {img
                    ? d.mode === 'draw'
                      ? <div className="dr-thumb-img" style={inkMask(img, ink?.color ?? '#1b2440')} />
                      : <img src={img} alt="" className="dr-thumb-img" />
                    : <span style={{ fontFamily: font, color: ink?.color ?? '#1b2440' }}>{d.text.trim() || ''}</span>}
                </div>
              </div>
              <div className="dr-main">
                <span className="dr-name">{ty ? `${tn(ty.name)} × ${d.qty}` : t('dr.untitled')}</span>
                <span className="dr-meta">{t('dr.step', { n: d.step + 1, total: STEP_LABELS.length, label })}</span>
                <span className="dr-steps" aria-hidden>
                  {STEP_LABELS.map((l, i) => <i key={l} className={i < d.step ? 'done' : i === d.step ? 'now' : ''} />)}
                </span>
                <span className="dr-meta">
                  {t('dr.saved', { time: ago(d.updatedAt, locale) })}
                  {' · '}
                  {ty ? t('dr.estimate', { total: fmt(q.total) }) : t('dr.noEstimate')}
                </span>
              </div>
              <div className="dr-side">
                <Link to={draftPathFor(d.id)} className="vh-btn vh-btn--primary vh-btn--sm dr-continue">{t('dr.continue')}</Link>
                {asking ? (
                  <span className="dr-confirm" role="alert">
                    <span>{t('dr.confirm')}</span>
                    <button className="ct-remove" onClick={() => deleteDraft(d.id)}>{t('dr.yes')}</button>
                    <button className="ct-remove dr-keep" onClick={() => setConfirming(null)}>{t('dr.no')}</button>
                  </span>
                ) : (
                  <button className="ct-remove" onClick={() => setConfirming(d.id)}>{t('dr.delete')}</button>
                )}
              </div>
            </li>
          )
        })}
        <li>
          <Link to={ORDER_HREF} className="dr-new">
            <span className="dr-new-plus" aria-hidden>+</span>
            <span>{t('dr.newOrder')}</span>
          </Link>
        </li>
      </ul>
      {!drafts.length && <p className="dr-empty-note">{t('dr.emptyBody')}</p>}

      <section className="ct-more dr-more">
        <h2>{t('ct.more')}</h2>
        <div className="ct-carousel" ref={carousel}>
          {PRODUCTS.map((p) => {
            const s = sel[p.id] ?? { paper: 0, pack: 0 }
            const paper = PAPERS[s.paper]
            const pack = PACKS[s.pack]
            const set = (patch: Partial<typeof s>) => setSel((all) => ({ ...all, [p.id]: { ...s, ...patch } }))
            return (
              <div key={p.id} className="ct-card">
                <div className="ct-card-stage">
                  <div className="ct-card-paper" style={{ aspectRatio: p.aspect, background: paper.color }}>
                    <span style={{ fontFamily: p.font, fontSize: p.size, color: p.ink }}>{p.text}</span>
                  </div>
                </div>
                <span className="ct-card-name">{tn(p.name)}</span>
                <div className="ct-dots">
                  {PAPERS.map((pp, i) => (
                    <button
                      key={pp.id}
                      title={tn(pp.name)}
                      aria-label={tn(pp.name)}
                      style={{ background: pp.color, borderColor: i === s.paper ? 'var(--accent)' : 'var(--fx-2)' }}
                      onClick={() => set({ paper: i })}
                    />
                  ))}
                </div>
                <div className="ct-packs">
                  {PACKS.map((pk, i) => (
                    <button key={pk.n} className={i === s.pack ? 'on' : ''} onClick={() => set({ pack: i })}>{tn(pk.label)}</button>
                  ))}
                </div>
                <span className="vh-mono ct-card-price">{fmt((p.base + paper.price) * pack.mult)}</span>
                <button className="ct-add" style={{ background: 'var(--btn-inv-bg)' }} onClick={() => useDesign(p, s.paper, s.pack)}>
                  {t('dr.useDesign')}
                </button>
              </div>
            )
          })}
        </div>
        <div className="ct-arrows">
          <button aria-label={t('ct.prev')} onClick={() => scrollCarousel(-1)}>←</button>
          <button aria-label={t('ct.next')} onClick={() => scrollCarousel(1)}>→</button>
        </div>
      </section>
    </div>
  )
}
