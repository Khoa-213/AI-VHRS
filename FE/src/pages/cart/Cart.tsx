import { useEffect, useRef, useState } from 'react'
import Page from '../../components/layout/Page'
import { ORDER_HREF } from '../../constants'
import { PACKS, PAPERS, PAYMENT_BADGES, PRODUCTS } from '../../constants/catalog'
import PaymentLogos from '../../components/ui/PaymentLogos'
import { useT, useTn } from '../../i18n'
import { Link, navigate, orderPath } from '../../router/router'
import { addToCart, checkoutCart, setCartQty, signIn, useCart, useUser } from '../../store/store'
import { fmt } from '../../utils/format'
import './cart.css'

export default function Cart() {
  const t = useT()
  const tn = useTn()
  const user = useUser()
  const cart = useCart()
  const [sel, setSel] = useState<Record<string, { paper: number; pack: number }>>({})
  const [added, setAdded] = useState<string | null>(null)
  const [placed, setPlaced] = useState<string | null>(null)
  const carousel = useRef<HTMLDivElement>(null)
  const addTimer = useRef<number | undefined>(undefined)
  useEffect(() => () => window.clearTimeout(addTimer.current), [])

  const sub = cart.reduce((n, c) => n + c.unit * c.qty, 0)
  const ship = sub >= 500000 ? 0 : 30000

  const checkout = () => {
    if (!user) {
      signIn()
      return
    }
    const order = checkoutCart()
    if (order) {
      setPlaced(order.id)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    }
  }

  const scrollCarousel = (d: number) => carousel.current?.scrollBy({ left: d * 340, behavior: 'smooth' })

  return (
    <Page label="Cart" width={1200}>
      <div className="ct-sections">
        {placed && (
          <div className="ct-banner">
            <span>
              {t('ct.placed', { id: placed })}{' '}
              <Link to={orderPath(placed, 'review')} className="vh-link">{t('ct.openOrder')}</Link>
            </span>
            <button className="vh-link" style={{ color: 'var(--t4)', fontSize: 14 }} onClick={() => setPlaced(null)}>{t('ct.dismiss')}</button>
          </div>
        )}

        {!cart.length ? (
          <section className="ct-empty">
            <span className="ct-empty-icon">
              <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4Z" />
                <path d="M3 6h18" />
                <path d="M16 10a4 4 0 0 1-8 0" />
              </svg>
            </span>
            <h1>{t('ct.emptyTitle')}</h1>
            <p>{t(user ? 'ct.emptyUser' : 'ct.emptyGuest')}</p>
            <div className="ct-empty-actions">
              <Link to="/" className="vh-btn vh-btn--ghost vh-btn--md ct-wide">{t('ct.browse')}</Link>
              {user ? (
                <Link to={ORDER_HREF} className="vh-btn vh-btn--primary vh-btn--md ct-wide">{t('ct.create')}</Link>
              ) : (
                <button className="vh-btn vh-btn--primary vh-btn--md ct-wide" onClick={signIn}>{t('nav.signIn')}</button>
              )}
            </div>
          </section>
        ) : (
          <section className="ct-cart">
            <h1 className="ct-title">{t('ct.title')}</h1>
            <div className="vh-cols" style={{ gap: 24 }}>
              <div className="ct-items">
                {cart.map((it) => (
                  <div key={it.key} className="ct-item">
                    <div className="ct-item-thumb">
                      <div className="ct-item-paper" style={{ aspectRatio: it.aspect, background: it.paperColor }}>
                        <span style={{ fontFamily: it.font }}>{it.text}</span>
                      </div>
                    </div>
                    <div className="ct-item-text">
                      <span className="ct-item-name">{tn(it.name)}</span>
                      <span className="ct-item-variant">{tn(it.paperName)} · {it.pack > 1 ? t('ct.pack', { n: it.pack }) : t('ct.single')}</span>
                      <button className="ct-remove" onClick={() => setCartQty(it.key, 0)}>{t('ct.remove')}</button>
                    </div>
                    <div className="ct-item-side">
                      <span className="vh-mono ct-item-line">{fmt(it.unit * it.qty)}</span>
                      <div className="ct-qty">
                        <button aria-label={t('co.dec')} onClick={() => setCartQty(it.key, it.qty - 1)}>−</button>
                        <span className="vh-mono">{it.qty}</span>
                        <button aria-label={t('co.inc')} onClick={() => setCartQty(it.key, it.qty + 1)}>+</button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              <aside className="vh-aside ct-summary" style={{ gap: 12, padding: 22, borderRadius: 24 }}>
                <span style={{ fontSize: 16, fontWeight: 800, color: 'var(--t1)' }}>{t('ct.summary')}</span>
                <div className="ct-sum-row"><span>{t('ct.subtotal')}</span><b className="vh-mono">{fmt(sub)}</b></div>
                <div className="ct-sum-row"><span>{t('ct.shipping')}</span><b className="vh-mono">{ship ? fmt(ship) : t('ct.free')}</b></div>
                <span style={{ fontSize: 12, color: 'var(--t6)' }}>{t('ct.freeFrom')}</span>
                <div className="vh-total-row" style={{ paddingTop: 12, borderTop: '1px solid var(--fx-08)' }}>
                  <span>{t('ct.total')}</span>
                  <span style={{ fontSize: 26 }}>{fmt(sub + ship)}</span>
                </div>
                <button className="vh-btn vh-btn--primary" style={{ marginTop: 6 }} onClick={checkout}>
                  {t(user ? 'ct.checkout' : 'ct.signInCheckout')}
                </button>
              </aside>
            </div>
          </section>
        )}

        <section className="ct-more">
          <h2>{t('ct.more')}</h2>
          <div className="ct-carousel" ref={carousel}>
            {PRODUCTS.map((p) => {
              const s = sel[p.id] ?? { paper: 0, pack: 0 }
              const paper = PAPERS[s.paper]
              const pack = PACKS[s.pack]
              const flash = added === p.id
              const set = (patch: Partial<typeof s>) => setSel((all) => ({ ...all, [p.id]: { ...s, ...patch } }))
              const add = () => {
                addToCart({
                  key: `${p.id}|${paper.id}|${pack.n}`,
                  name: p.name, text: p.text, font: p.font, aspect: p.aspect,
                  paperName: paper.name, paperColor: paper.color, pack: pack.n,
                  unit: (p.base + paper.price) * pack.mult,
                })
                setAdded(p.id)
                window.clearTimeout(addTimer.current)
                addTimer.current = window.setTimeout(() => setAdded(null), 1400)
              }
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
                  <button className="ct-add" style={flash ? { background: 'var(--good-solid)', color: 'var(--good-solid-fg)' } : undefined} onClick={add}>
                    {t(flash ? 'ct.added' : 'ct.add')}
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
