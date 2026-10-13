import { useEffect, useRef, useState } from 'react'
import Page from '../../components/layout/Page'
import PaymentLogos from '../../components/ui/PaymentLogos'
import { ORDER_HREF } from '../../constants'
import { FONT_STYLES, INKS, PACKS, PAPERS, PAYMENT_BADGES, PRODUCTS, STEP_LABELS, TYPES } from '../../constants/catalog'
import { useLocale, useT, useTn } from '../../i18n'
import { Link, navigate } from '../../router/router'
import { deleteDraft, newDraftId, saveDraft, signIn, useDrafts, useUser } from '../../store/store'
import type { OrderDraft } from '../../types'
import { fmt } from '../../utils/format'
import { quote } from '../../utils/pricing'
import { inkMask } from '../../components/ui/PaperSheet'
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

export default function Drafts() {
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
    <Page label="Drafts" width={1200}>
      <div className="ct-sections">
        {!user || !drafts.length ? (
          <section className="ct-empty">
            <span className="ct-empty-icon">
              <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
                <path d="M14 3v5h5" />
                <path d="M9 13h6M9 17h4" />
              </svg>
            </span>
            <h1>{t('dr.emptyTitle')}</h1>
            <p>{t(user ? 'dr.emptyBody' : 'dr.guestBody')}</p>
            <div className="ct-empty-actions">
              <Link to="/" className="vh-btn vh-btn--ghost vh-btn--md ct-wide">{t('ct.browse')}</Link>
              {user ? (
                <Link to={ORDER_HREF} className="vh-btn vh-btn--primary vh-btn--md ct-wide">{t('hist.create')}</Link>
              ) : (
                <button className="vh-btn vh-btn--primary vh-btn--md ct-wide" onClick={signIn}>{t('nav.signIn')}</button>
              )}
            </div>
          </section>
        ) : (
          <section className="ct-cart">
            <div className="dr-head">
              <h1 className="ct-title">{t('dr.title')}</h1>
              <p className="vh-lede">{t('dr.lede')}</p>
            </div>
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
          </section>
        )}

        <section className="ct-more">
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
          <button className="vh-btn vh-btn--ghost vh-btn--md" onClick={() => navigate(ORDER_HREF)}>{t('ct.custom')}</button>
        </section>

        <section className="ct-pay">
          <h3>{t('ct.payTitle')}</h3>
          <PaymentLogos names={PAYMENT_BADGES.map((pm) => pm.name)} />
          <div className="ct-help">
            <span>{t('ct.help', { link: t('ct.contact') })}</span>
            <a href="#cancellation">{t('ct.cancel')}</a>
            <a href="#delivery">{t('ct.delivery')}</a>
          </div>
        </section>
      </div>
    </Page>
  )
}
