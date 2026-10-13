import { ClockCounterClockwise } from '@phosphor-icons/react'
import { useRef, useState } from 'react'
import { ORDER_HREF } from '../../constants'
import { STATUS_COLORS } from '../../constants/catalog'
import { useT, useTn } from '../../i18n'
import { Link, orderPath } from '../../router/router'
import { signIn, useOrders, useUser } from '../../store/store'
import type { Order } from '../../types'
import { fmt } from '../../utils/format'

/** Where an order opens from the history list, by status. */
function orderHref(o: Order) {
  if (o.status === 'Accepted') return orderPath(o.id, 'deposit')
  if (['Shipped', 'Delivered'].includes(o.status)) return orderPath(o.id, 'tracking')
  if (['Written', 'Rewriting'].includes(o.status)) return orderPath(o.id, 'result')
  return orderPath(o.id, 'review')
}

/** Clock icon in the top bar. Hover or click to see the latest orders. */
export default function OrderHistoryMenu({ buttonClassName }: { buttonClassName: string }) {
  const t = useT()
  const tn = useTn()
  const user = useUser()
  const orders = useOrders()
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
    <div className={`vh-dd${open ? ' open' : ''}`} onMouseEnter={enter} onMouseLeave={leave}>
      <button
        type="button"
        className={buttonClassName}
        aria-label={t('hist.title')}
        aria-haspopup="true"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        onFocus={enter}
      >
        <ClockCounterClockwise size={20} aria-hidden />
      </button>
      <div className="vh-dd-panel">
        <div className="vh-dd-card">
          <div className="vh-dd-head">
            <span>{t('hist.title')}</span>
            <span className="vh-dd-count">{user ? t('hist.count', { n: orders.length }) : ''}</span>
          </div>
          {user ? (
            <div className="vh-dd-list">
              {orders.slice(0, 4).map((o) => {
                const [color] = STATUS_COLORS[o.status]
                return (
                  <Link key={o.id} to={orderHref(o)} className="vh-dd-item" onClick={() => setOpen(false)}>
                    <div className="vh-dd-item-text">
                      <span className="vh-dd-item-meta">{o.id} · {o.date}</span>
                      <span className="vh-dd-item-title">{tn(o.title)}</span>
                    </div>
                    <div className="vh-dd-item-side">
                      <span className="vh-chip" style={{ color }}>{t(`status.${o.status}`)}</span>
                      <span className="vh-dd-item-total">{fmt(o.total)}</span>
                    </div>
                  </Link>
                )
              })}
              {!orders.length && <span className="vh-dd-empty">{t('hist.empty')}</span>}
            </div>
          ) : (
            <div className="vh-dd-signin">
              <span>{t('hist.signInPrompt')}</span>
              <button className="vh-btn vh-btn--ghost vh-btn--sm" onClick={signIn}>{t('nav.signIn')}</button>
            </div>
          )}
          <div className="vh-dd-foot">
            {user && (
              <Link to="/drafts" className="vh-btn vh-btn--ghost vh-btn--sm vh-grow" onClick={() => setOpen(false)}>{t('hist.viewDrafts')}</Link>
            )}
            <Link to={ORDER_HREF} className="vh-btn vh-btn--primary vh-btn--sm vh-grow" onClick={() => setOpen(false)}>{t('hist.create')}</Link>
          </div>
        </div>
      </div>
    </div>
  )
}
