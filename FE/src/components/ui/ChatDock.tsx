import { ArrowSquareOut, CaretLeft, ChatCircleDots, X } from '@phosphor-icons/react'
import { useEffect, useRef } from 'react'
import { STATUS_COLOR } from '../../constants/orderStatus'
import { useAsync } from '../../hooks/useAsync'
import { useLocale, useT } from '../../i18n'
import { Link, matchOrderRoute, orderPath, usePath } from '../../router/router'
import { listConversations, type Conversation } from '../../services/chat'
import type { Order } from '../../services/orders'
import { closeChat, openChat, showThread, useChatDock } from '../../store/chatDock'
import { useUser } from '../../store/store'
import { fmt } from '../../utils/format'
import Chat from './Chat'
import './chat-dock.css'

const CLOSED = ['REJECTED', 'CANCELLED', 'COMPLETED']
/** Full-screen or workshop pages where the floating button would be in the way. */
const HIDDEN = /^\/(staff|tech|admin|login|register|create-order\/draw)(\/|$)/

function OrderCard({ order, at }: { order: Order; at: string }) {
  const t = useT()
  const locale = useLocale()
  const price = order.total ?? order.estMax
  return (
    <div className="chat-msg mine cd-card">
      <span className="cd-card-tag">{t('cd.asking')}</span>
      <div className="cd-card-body">
        <b className="vh-mono">{order.code}</b>
        <span>{t(`ot.${order.type}`)}</span>
        <span className="vh-chip" style={{ color: STATUS_COLOR[order.status] }}>{t(`os.${order.status}`)}</span>
        <span className="cd-card-meta">
          {t('cd.qty', { n: order.quantity })}
          {price !== null && <> · <span className="vh-mono">{fmt(price)}</span></>}
        </span>
      </div>
      <Link to={orderPath(order.id, 'review')} className="cd-card-link">
        {t('cd.viewOrder')} <ArrowSquareOut size={14} aria-hidden />
      </Link>
      <span className="chat-time vh-mono">{new Date(at).toLocaleString(locale, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</span>
    </div>
  )
}

/**
 * Floating chat for signed-in customers, bottom right on the customer site. One thread per sent order. Opening it from
 * an order page drops that order's card into its thread, so the studio sees which order the question is about.
 */
export default function ChatDock() {
  const t = useT()
  const locale = useLocale()
  const user = useUser()
  const path = usePath()
  const dock = useChatDock()
  const panel = useRef<HTMLElement>(null)
  const fab = useRef<HTMLButtonElement>(null)
  const customer = user?.role === 'customer'
  const list = useAsync(() => (customer ? listConversations() : Promise.resolve([])), [customer], dock.open ? 15000 : 60000)
  const convos = list.data ?? []
  const unread = convos.reduce((n, c) => n + c.unread, 0)
  const here = Number(matchOrderRoute(path, 'review') ?? matchOrderRoute(path, 'deposit') ?? NaN)
  const active = convos.find((c) => c.order.id === dock.orderId) ?? null
  const inThread = !!active || (dock.orderId !== null && list.loading)

  useEffect(() => {
    if (!dock.open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      closeChat()
      fab.current?.focus()
    }
    window.addEventListener('keydown', onKey)
    panel.current?.focus()
    return () => window.removeEventListener('keydown', onKey)
  }, [dock.open])

  if (!customer || HIDDEN.test(path)) return null

  const toggle = () => {
    if (dock.open) return closeChat()
    // On an order page, ask about that order even before the list has loaded; a draft simply has no thread to show.
    const draft = !list.loading && !convos.some((c) => c.order.id === here)
    if (Number.isFinite(here) && !draft) openChat(here)
    else openChat()
  }

  const preview = (c: Conversation) =>
    c.last ? (c.last.body || t('cd.photo')) : dock.cards[c.order.id] ? t('cd.asking') : t('cd.noMessages')
  const time = (c: Conversation) => {
    const iso = c.last?.createdAt ?? c.order.submittedAt ?? c.order.createdAt
    return new Date(iso).toLocaleDateString(locale, { day: 'numeric', month: 'short' })
  }

  return (
    <div className="cd">
      {dock.open && (
        <section
          ref={panel}
          tabIndex={-1}
          className={`cd-panel${inThread ? ' cd-panel--thread' : ''}`}
          role="dialog"
          aria-label={t('cd.title')}
        >
          <header className="cd-head">
            {inThread && (
              <button type="button" className="cd-icon cd-back" onClick={() => showThread(null)} aria-label={t('cd.back')} title={t('cd.back')}>
                <CaretLeft size={18} aria-hidden />
              </button>
            )}
            <div className="cd-head-t">
              <b>{t('cd.title')}</b>
              <span>{t('cd.sub')}</span>
            </div>
            <button type="button" className="cd-icon" onClick={() => closeChat()} aria-label={t('common.close')} title={t('common.close')}>
              <X size={18} aria-hidden />
            </button>
          </header>

          <div className="cd-body">
            <nav className="cd-list" aria-label={t('cd.threads')}>
              {list.loading && !list.data && <p className="cd-note">{t('cd.loading')}</p>}
              {list.data && !convos.length && (
                <div className="cd-note">
                  <p>{t('cd.noOrders')}</p>
                  <Link to="/create-order" className="vh-link" onClick={() => closeChat()}>{t('nav.startWriting')}</Link>
                </div>
              )}
              {convos.map((c) => (
                <button
                  key={c.order.id}
                  type="button"
                  className={`cd-item${c.order.id === dock.orderId ? ' on' : ''}`}
                  aria-current={c.order.id === dock.orderId ? 'true' : undefined}
                  onClick={() => openChat(c.order.id, false)}
                >
                  <span className="cd-item-top">
                    <b className="vh-mono">{c.order.code}</b>
                    <span className="cd-item-time">{time(c)}</span>
                  </span>
                  <span className="cd-item-mid">
                    <span className="vh-chip" style={{ color: STATUS_COLOR[c.order.status] }}>{t(`os.${c.order.status}`)}</span>
                  </span>
                  <span className="cd-item-bot">
                    <span className="cd-item-last">{preview(c)}</span>
                    {c.unread > 0 && <span className="cd-badge" aria-label={t('cd.unread', { n: c.unread })}>{c.unread}</span>}
                  </span>
                </button>
              ))}
            </nav>

            <div className="cd-thread">
              {active ? (
                <>
                  <div className="cd-thread-head">
                    <div>
                      <b className="vh-mono">{active.order.code}</b>
                      <span>{t(`ot.${active.order.type}`)}</span>
                    </div>
                    <Link to={orderPath(active.order.id, 'review')} className="vh-link">{t('cd.viewOrder')}</Link>
                  </div>
                  <Chat
                    key={active.order.id}
                    orderId={active.order.id}
                    bare
                    closed={CLOSED.includes(active.order.status)}
                    card={dock.cards[active.order.id] ? { at: dock.cards[active.order.id], node: <OrderCard order={active.order} at={dock.cards[active.order.id]} /> } : undefined}
                  />
                </>
              ) : (
                <p className="cd-note cd-pick">{list.loading ? t('cd.loading') : convos.length ? t('cd.pick') : t('cd.howTo')}</p>
              )}
            </div>
          </div>
        </section>
      )}

      <button
        ref={fab}
        type="button"
        className="cd-fab"
        aria-expanded={dock.open}
        aria-label={unread ? t('cd.openUnread', { n: unread }) : t('cd.open')}
        title={t('cd.open')}
        onClick={toggle}
      >
        {dock.open ? <X size={24} aria-hidden /> : <ChatCircleDots size={26} weight="fill" aria-hidden />}
        {!dock.open && unread > 0 && <span className="cd-badge cd-fab-badge">{unread > 99 ? '99+' : unread}</span>}
      </button>
    </div>
  )
}
