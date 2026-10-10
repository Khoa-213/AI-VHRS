import { useEffect, useRef, useState } from 'react'
import Page from '../../components/layout/Page'
import { ORDER_HREF } from '../../constants'
import { PACKS, PAPERS, PAYMENT_BADGES, PRODUCTS } from '../../constants/catalog'
import { Link, navigate, orderPath } from '../../router/router'
import { addToCart, checkoutCart, setCartQty, signIn, useCart, useUser } from '../../store/store'
import { fmt } from '../../utils/format'
import './cart.css'

export default function Cart() {
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
              Order <b className="vh-mono">{placed}</b> placed — it’s now in the FR3 queue.{' '}
              <Link to={orderPath(placed, 'review')} className="vh-link">Open order</Link>
            </span>
            <button className="vh-link" style={{ color: 'var(--t4)', fontSize: 14 }} onClick={() => setPlaced(null)}>Dismiss</button>
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
            <h1>Your cart is empty</h1>
            <p>{user ? 'Start a custom order, or add a ready-made design below.' : 'Sign in to see saved items and your order history, or keep exploring.'}</p>
            <div className="ct-empty-actions">
              <Link to="/" className="vh-btn vh-btn--ghost vh-btn--md ct-wide">Continue browsing</Link>
              {user ? (
                <Link to={ORDER_HREF} className="vh-btn vh-btn--primary vh-btn--md ct-wide">Create new order</Link>
              ) : (
                <button className="vh-btn vh-btn--primary vh-btn--md ct-wide" onClick={signIn}>Sign in</button>
              )}
            </div>
          </section>
        ) : (
          <section className="ct-cart">
            <h1 className="ct-title">Your cart</h1>
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
                      <span className="ct-item-name">{it.name}</span>
                      <span className="ct-item-variant">{it.paperName} · {it.pack > 1 ? `pack of ${it.pack}` : 'single'}</span>
                      <button className="ct-remove" onClick={() => setCartQty(it.key, 0)}>Remove</button>
                    </div>
                    <div className="ct-item-side">
                      <span className="vh-mono ct-item-line">{fmt(it.unit * it.qty)}</span>
                      <div className="ct-qty">
                        <button aria-label="Decrease" onClick={() => setCartQty(it.key, it.qty - 1)}>−</button>
                        <span className="vh-mono">{it.qty}</span>
                        <button aria-label="Increase" onClick={() => setCartQty(it.key, it.qty + 1)}>+</button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              <aside className="vh-aside ct-summary" style={{ gap: 12, padding: 22, borderRadius: 24 }}>
                <span style={{ fontSize: 16, fontWeight: 800, color: 'var(--t1)' }}>Summary</span>
                <div className="ct-sum-row"><span>Subtotal</span><b className="vh-mono">{fmt(sub)}</b></div>
                <div className="ct-sum-row"><span>Shipping</span><b className="vh-mono">{ship ? fmt(ship) : 'Free'}</b></div>
                <span style={{ fontSize: 12, color: 'var(--t6)' }}>Free shipping from 500.000₫</span>
                <div className="vh-total-row" style={{ paddingTop: 12, borderTop: '1px solid var(--fx-08)' }}>
                  <span>Total</span>
                  <span style={{ fontSize: 26 }}>{fmt(sub + ship)}</span>
                </div>
                <button className="vh-btn vh-btn--primary" style={{ marginTop: 6 }} onClick={checkout}>
                  {user ? 'Checkout' : 'Sign in to checkout'}
                </button>
              </aside>
            </div>
          </section>
        )}

        <section className="ct-more">
          <h2>You might also like</h2>
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
                  <span className="ct-card-name">{p.name}</span>
                  <div className="ct-dots">
                    {PAPERS.map((pp, i) => (
                      <button
                        key={pp.id}
                        title={pp.name}
                        aria-label={pp.name}
                        style={{ background: pp.color, borderColor: i === s.paper ? 'var(--accent)' : 'var(--fx-2)' }}
                        onClick={() => set({ paper: i })}
                      />
                    ))}
                  </div>
                  <div className="ct-packs">
                    {PACKS.map((pk, i) => (
                      <button key={pk.n} className={i === s.pack ? 'on' : ''} onClick={() => set({ pack: i })}>{pk.label}</button>
                    ))}
                  </div>
                  <span className="vh-mono ct-card-price">{fmt((p.base + paper.price) * pack.mult)}</span>
                  <button className="ct-add" style={flash ? { background: 'var(--good-solid)', color: 'var(--good-solid-fg)' } : undefined} onClick={add}>
                    {flash ? 'Added ✓' : 'Add to cart'}
                  </button>
                </div>
              )
            })}
          </div>
          <div className="ct-arrows">
            <button aria-label="Previous" onClick={() => scrollCarousel(-1)}>←</button>
            <button aria-label="Next" onClick={() => scrollCarousel(1)}>→</button>
          </div>
          <button className="vh-btn vh-btn--ghost vh-btn--md" onClick={() => navigate(ORDER_HREF)}>Start a custom order</button>
        </section>

        <section className="ct-pay">
          <h3>Supported payment methods</h3>
          <div className="ct-badges">
            {PAYMENT_BADGES.map((pm) => (
              <span key={pm.name}><i style={{ background: pm.dot }} />{pm.name}</span>
            ))}
          </div>
          <div className="ct-help">
            <span>Questions? <a href="#contact">Contact us</a> — we’re here 24/7.</span>
            <a href="#cancellation">Cancellation policy</a>
            <a href="#delivery">Estimated delivery times</a>
          </div>
        </section>
      </div>
    </Page>
  )
}
