import {
  Bell, BellRinging, CalendarX, ChatCircleText, CheckCircle, CreditCard, FileText, Prohibit, Truck, Info,
} from '@phosphor-icons/react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useLocale, useT } from '../../i18n'
import { navigate } from '../../router/router'
import { openChat } from '../../store/chatDock'
import type { AppNotification } from '../../services/notifications'
import {
  loadMoreNotifications, readAllNotifications, readNotification, reloadNotifications, useNotifications,
} from '../../store/notifications'
import { useUser } from '../../store/store'
import './notification-bell.css'

const ICONS: Record<string, ReactNode> = {
  ORDER_REJECTED: <Prohibit size={18} aria-hidden />,
  QUOTATION_AVAILABLE: <FileText size={18} aria-hidden />,
  QUOTATION_EXPIRED: <CalendarX size={18} aria-hidden />,
  ETA_POSTPONED: <CalendarX size={18} aria-hidden />,
  PRODUCT_COMPLETED: <CheckCircle size={18} aria-hidden />,
  DELIVERING: <Truck size={18} aria-hidden />,
  PAYMENT: <CreditCard size={18} aria-hidden />,
  NEW_MESSAGE: <ChatCircleText size={18} aria-hidden />,
}

/**
 * Where a notification leads. A new chat message opens the chat thread of that order (so it works even when the order page
 * is already open); a refund for the workshop opens the refunds desk; everything else opens the order page that fits the role.
 */
function target(n: AppNotification, role?: string): { to?: string; chat?: number } | null {
  if (role === 'technician') return { to: '/tech' }
  if (role === 'admin' || n.orderId == null) return null
  if (n.type === 'NEW_MESSAGE') return { chat: n.orderId }
  if (role === 'staff') return { to: n.type === 'PAYMENT' ? '/staff/refunds' : `/staff/review/${n.orderId}` }
  return { to: `/orders/${n.orderId}/review` }
}

/**
 * Notification center bell (FR-27): the badge, the list with "load more", read one / read all, and the live stream.
 * `variant="site"` sits in the public top bar, `"ws"` in the workshop header.
 */
export default function NotificationBell({ variant }: { variant: 'site' | 'landing' | 'adm' | 'ws' }) {
  const t = useT()
  const locale = useLocale()
  const user = useUser()
  const state = useNotifications()
  const [open, setOpen] = useState(false)
  const [more, setMore] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!open) return
    void reloadNotifications()
    const onDown = (e: PointerEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(false) }
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      setOpen(false)
      trigger.current?.focus()
    }
    document.addEventListener('pointerdown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const when = (iso: string) => new Date(iso).toLocaleString(locale, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
  const unread = state.unread

  const choose = (n: AppNotification) => {
    void readNotification(n.id)
    const go = target(n, user?.role)
    if (!go) return
    setOpen(false)
    if (go.chat !== undefined) openChat(go.chat, false)
    else if (go.to) navigate(go.to)
  }

  return (
    <div className={`nbell nbell-${variant}${unread ? ' on' : ''}`} ref={root}>
      <button
        ref={trigger}
        type="button"
        className={variant === 'site' ? 'vh-icon-btn nbell-btn' : variant === 'landing' ? 'lp-icon-btn nbell-btn' : 'nbell-btn'}
        aria-label={unread ? t('nt.bellCount', { n: unread }) : t('nt.bell')}
        title={t('nt.bell')}
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        {unread ? <BellRinging size={20} weight="fill" aria-hidden /> : <Bell size={20} aria-hidden />}
        {unread > 0 && <span className="nbell-count">{unread > 99 ? '99+' : unread}</span>}
      </button>
      {open && (
        <div className="nbell-pop" role="dialog" aria-label={t('nt.title')}>
          <div className="nbell-h">
            <b>{t('nt.title')}</b>
            <button type="button" className="nbell-link" disabled={!unread} onClick={() => void readAllNotifications()}>{t('nt.readAll')}</button>
          </div>
          {!!state.error && !state.items.length && <p className="nbell-empty" role="alert">{t('nt.error')}</p>}
          {state.loaded && !state.error && !state.items.length && <p className="nbell-empty">{t('nt.empty')}</p>}
          <ul>
            {state.items.map((n) => (
              <li key={n.id} className={n.isRead ? '' : 'unread'}>
                <button type="button" onClick={() => choose(n)}>
                  <span className="nbell-ico">{ICONS[n.type] ?? <Info size={18} aria-hidden />}</span>
                  <span className="nbell-txt">
                    <b>{n.title}</b>
                    <span>{n.body}</span>
                    <small>{n.orderId != null ? `${t('nt.order', { id: n.orderId })} · ` : ''}{when(n.createdAt)}</small>
                  </span>
                  {!n.isRead && <span className="nbell-dot" aria-label={t('nt.unread')} />}
                </button>
              </li>
            ))}
          </ul>
          {state.nextBeforeId != null && (
            <button
              type="button"
              className="nbell-more"
              disabled={more}
              onClick={async () => { setMore(true); await loadMoreNotifications(); setMore(false) }}
            >
              {t('nt.more')}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
