import { useRef, useState } from 'react'
import { ORDER_HREF, svgProps } from '../../constants'
import { STATUS_COLORS } from '../../constants/catalog'
import { Link, orderPath } from '../../router/router'
import { signIn, signOut, useCart, useOrders, useUser } from '../../store/store'
import type { Order } from '../../types'
import { fmt } from '../../utils/format'
import ThemeToggle from '../ui/ThemeToggle'

/** Where an order opens from the history list, by status. */
function orderHref(o: Order) {
  if (o.status === 'Accepted') return orderPath(o.id, 'deposit')
  if (['Written', 'Rewriting', 'Shipped', 'Delivered'].includes(o.status)) return orderPath(o.id, 'result')
  return orderPath(o.id, 'review')
}

export default function SiteHeader() {
  const user = useUser()
  const orders = useOrders()
  const cartCount = useCart().reduce((n, c) => n + c.qty, 0)
  const [open, setOpen] = useState(false)
  const timer = useRef<number | undefined>(undefined)

  const enter = () => {
    window.clearTimeout(timer.current)
    setOpen(true)
  }
  const leave = () => {
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setOpen(false), 160)
  }

  return (
    <header className="vh-header">
      <div className="vh-header-inner">
        <Link to="/" className="vh-logo">AI-VHRS</Link>
        <nav className="vh-nav">
          <Link to="/#showcase">Features</Link>
          <Link to="/#showcase">Robot Specs</Link>
          <Link to="/#modes">Penmanship</Link>
          <Link to="/#queue">Order Queue</Link>
        </nav>
        <div className="vh-actions">
          <button className="vh-icon-btn" aria-label="Search">
            <svg width="19" height="19" viewBox="0 0 24 24" strokeWidth="2" {...svgProps}>
              <circle cx="11" cy="11" r="8" />
              <path d="m21 21-4.3-4.3" />
            </svg>
          </button>
          <ThemeToggle className="vh-icon-btn" />
          <div className={`vh-dd${open ? ' open' : ''}`} onMouseEnter={enter} onMouseLeave={leave}>
            <Link to="/cart" className="vh-icon-btn" aria-label="Cart">
              <svg width="19" height="19" viewBox="0 0 24 24" strokeWidth="2" {...svgProps}>
                <path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4Z" />
                <path d="M3 6h18" />
                <path d="M16 10a4 4 0 0 1-8 0" />
              </svg>
              {cartCount > 0 && <span className="vh-badge">{cartCount}</span>}
            </Link>
            <div className="vh-dd-panel">
              <div className="vh-dd-card">
                <div className="vh-dd-head">
                  <span>Order history</span>
                  <span className="vh-dd-count">{user ? `${orders.length} orders` : ''}</span>
                </div>
                {user ? (
                  <div className="vh-dd-list">
                    {orders.slice(0, 4).map((o) => {
                      const [color, bg] = STATUS_COLORS[o.status]
                      return (
                        <Link key={o.id} to={orderHref(o)} className="vh-dd-item" onClick={() => setOpen(false)}>
                          <div className="vh-dd-item-text">
                            <span className="vh-dd-item-meta">{o.id} · {o.date}</span>
                            <span className="vh-dd-item-title">{o.title}</span>
                          </div>
                          <div className="vh-dd-item-side">
                            <span className="vh-chip" style={{ color, background: bg }}>{o.status}</span>
                            <span className="vh-dd-item-total">{fmt(o.total)}</span>
                          </div>
                        </Link>
                      )
                    })}
                    {!orders.length && <span className="vh-dd-empty">No orders yet.</span>}
                  </div>
                ) : (
                  <div className="vh-dd-signin">
                    <span>Sign in to see your purchase history and track orders in the robot queue.</span>
                    <button className="vh-btn vh-btn--ghost vh-btn--sm" onClick={signIn}>Sign in</button>
                  </div>
                )}
                <div className="vh-dd-foot">
                  <Link to="/cart" className="vh-btn vh-btn--ghost vh-btn--sm vh-grow">View cart</Link>
                  <Link to={ORDER_HREF} className="vh-btn vh-btn--primary vh-btn--sm vh-grow">Create new order</Link>
                </div>
              </div>
            </div>
          </div>
          <button
            className="vh-icon-btn"
            aria-label={user ? 'Sign out' : 'Sign in'}
            title={user ? `Signed in as ${user.name} · click to sign out` : 'Click to sign in'}
            onClick={user ? signOut : signIn}
          >
            {user ? (
              <span className="vh-avatar">{user.name.trim().charAt(0).toUpperCase()}</span>
            ) : (
              <svg width="20" height="20" viewBox="0 0 24 24" strokeWidth="2" {...svgProps}>
                <circle cx="12" cy="12" r="10" />
                <circle cx="12" cy="10" r="3" />
                <path d="M7 20.662V19a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v1.662" />
              </svg>
            )}
          </button>
        </div>
      </div>
    </header>
  )
}
