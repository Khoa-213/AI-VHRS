import { CaretLeft, ChatCircleDots, X } from '@phosphor-icons/react'
import { useEffect, useRef, useState } from 'react'
import { STATUS_COLOR } from '../../constants/orderStatus'
import { useAsync } from '../../hooks/useAsync'
import { useLocale, useT } from '../../i18n'
import { Link, matchOrderRoute, orderPath, usePath } from '../../router/router'
import { ApiError } from '../../services/api'
import { listConversations, unreadCount, type Conversation } from '../../services/chat'
import { errText, getOrder, orderErrorKey, type OrderStatus } from '../../services/orders'
import { getWork, sendOrderCard, type WorkOrder } from '../../services/workshop'
import { closeChat, doneAsking, openChat, showThread, useChatDock } from '../../store/chatDock'
import { useUser } from '../../store/store'
import Chat from './Chat'
import './chat-dock.css'

/** Orders whose chat is read only. A COMPLETED order stays open so the customer can still raise a complaint. */
const CLOSED: OrderStatus[] = ['REJECTED', 'CANCELLED']
/** Full-screen or workshop pages where the customer's button would be in the way. */
const HIDDEN = /^\/(staff|tech|admin|login|register|create-order\/draw)(\/|$)/

/**
 * Floating chat, bottom right. One thread per sent order, listed by the backend inbox (`/me/conversations`,
 * `/workshop/conversations`) with the unread badge from `.../unread-count`.
 * - `customer` (mounted in App): opening it from an order shares that order's card (`ORDER_CARD`) in its thread, so the
 *   studio sees which order the question is about.
 * - `workshop` (mounted in the workshop Shell): a Staff sees the orders they hold plus the unclaimed pool (read only until
 *   claimed), a Manager every sent order, each with the customer's name.
 */
export default function ChatDock({ side = 'customer' }: { side?: 'customer' | 'workshop' }) {
  const t = useT()
  const locale = useLocale()
  const user = useUser()
  const path = usePath()
  const dock = useChatDock()
  const panel = useRef<HTMLElement>(null)
  const fab = useRef<HTMLButtonElement>(null)
  const [refresh, setRefresh] = useState(0)
  const [askErr, setAskErr] = useState('')
  const workshop = side === 'workshop'
  const manager = user?.apiRole === 'MANAGER'
  const allowed = workshop ? user?.role === 'staff' : user?.role === 'customer'

  const badge = useAsync(() => (allowed ? unreadCount(side) : Promise.resolve(0)), [allowed, side], dock.open ? 15000 : 30000)
  const list = useAsync(
    () => (allowed && dock.open ? listConversations(side) : Promise.resolve(null)),
    [allowed, side, dock.open],
    dock.open ? 15000 : undefined,
  )
  // The open thread's order: header, whether it is closed, and (workshop) whether this Staff may answer.
  const info = useAsync(
    () => (!allowed || dock.orderId === null ? Promise.resolve(null) : workshop ? getWork(dock.orderId) : getOrder(dock.orderId)),
    [allowed, workshop, dock.orderId, refresh],
  )

  const convos = list.data ?? []
  const unread = badge.data ?? 0
  const here = Number(workshop
    ? /^\/staff\/review\/(\d+)\/?$/.exec(path)?.[1] ?? NaN
    : matchOrderRoute(path, 'review') ?? matchOrderRoute(path, 'deposit') ?? NaN)
  const orderHref = (id: number) => (workshop ? `/staff/review/${id}` : orderPath(id, 'review'))
  const row = convos.find((c) => c.orderId === dock.orderId) ?? null
  const order = info.data && info.data.id === dock.orderId ? info.data : null
  const work = workshop ? (order as WorkOrder | null) : null
  const inThread = dock.orderId !== null

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

  // A customer opened the chat from an order: share its card. The backend returns the same card within 10 minutes.
  useEffect(() => {
    const id = dock.ask
    if (id === null || workshop) return
    doneAsking()
    setAskErr('')
    sendOrderCard(id).then(
      () => {
        setRefresh((n) => n + 1)
        void list.reload()
      },
      (e) => {
        if (e instanceof ApiError && e.code === 'ORDER_NOT_SUBMITTED') showThread(null) // a draft has no chat yet
        else setAskErr(orderErrorKey(e))
      },
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dock.ask, workshop])

  if (!allowed || (!workshop && HIDDEN.test(path))) return null

  const toggle = () => {
    if (dock.open) return closeChat()
    if (Number.isFinite(here)) openChat(here, !workshop)
    else openChat()
  }

  const afterRead = () => {
    void badge.reload()
    void list.reload()
  }

  const preview = (c: Conversation) => {
    const text = c.last.kind === 'ORDER_CARD' ? t('cd.card') : c.last.body || (c.last.hasAttachment ? t('cd.photo') : '')
    return c.last.mine ? t('cd.you', { text }) : text
  }
  const time = (iso: string) => new Date(iso).toLocaleDateString(locale, { day: 'numeric', month: 'short' })

  let locked: string | undefined
  let hint: string | undefined
  if (order && CLOSED.includes(order.status)) locked = t('chat.closed')
  else if (work && !manager && work.assignedStaffId !== user?.id) locked = t('cd.ws.claimToReply')
  else if (order && !workshop && order.status === 'SUBMITTED') hint = t('cd.unclaimedHint')

  const code = row?.code ?? order?.code
  const type = row?.type ?? order?.type
  const customerName = row?.customerName ?? work?.customerName ?? null

  return (
    <div className="cd">
      {dock.open && (
        <section
          ref={panel}
          tabIndex={-1}
          className={`cd-panel${inThread ? ' cd-panel--thread' : ''}`}
          role="dialog"
          aria-label={t(workshop ? 'cd.ws.title' : 'cd.title')}
        >
          <header className="cd-head">
            {inThread && (
              <button type="button" className="cd-icon cd-back" onClick={() => showThread(null)} aria-label={t('cd.back')} title={t('cd.back')}>
                <CaretLeft size={18} aria-hidden />
              </button>
            )}
            <div className="cd-head-t">
              <b>{t(workshop ? 'cd.ws.title' : 'cd.title')}</b>
              <span>{t(workshop ? (manager ? 'cd.ws.subManager' : 'cd.ws.sub') : 'cd.sub')}</span>
            </div>
            <button type="button" className="cd-icon" onClick={() => closeChat()} aria-label={t('common.close')} title={t('common.close')}>
              <X size={18} aria-hidden />
            </button>
          </header>

          <div className="cd-body">
            <nav className="cd-list" aria-label={t('cd.threads')}>
              {list.loading && !list.data && <p className="cd-note">{t('cd.loading')}</p>}
              {!!list.error && !list.data && <p className="cd-note">{errText(t, orderErrorKey(list.error))}</p>}
              {list.data && !convos.length && (
                <div className="cd-note">
                  <p>{t(workshop ? 'cd.ws.none' : 'cd.noOrders')}</p>
                  {!workshop && <Link to="/create-order" className="vh-link" onClick={() => closeChat()}>{t('nav.startWriting')}</Link>}
                </div>
              )}
              {convos.map((c) => (
                <button
                  key={c.orderId}
                  type="button"
                  className={`cd-item${c.orderId === dock.orderId ? ' on' : ''}`}
                  aria-current={c.orderId === dock.orderId ? 'true' : undefined}
                  onClick={() => openChat(c.orderId, false)}
                >
                  <span className="cd-item-top">
                    <b className="vh-mono">{c.code}</b>
                    <span className="cd-item-time">{time(c.last.createdAt)}</span>
                  </span>
                  {c.customerName && <span className="cd-item-who">{c.customerName}</span>}
                  <span className="cd-item-mid">
                    <span className="vh-chip" style={{ color: STATUS_COLOR[c.status] }}>{t(`os.${c.status}`)}</span>
                  </span>
                  <span className="cd-item-bot">
                    <span className="cd-item-last">{preview(c)}</span>
                    {c.unread > 0 && <span className="cd-badge" aria-label={t('cd.unread', { n: c.unread })}>{c.unread}</span>}
                  </span>
                </button>
              ))}
            </nav>

            <div className="cd-thread">
              {dock.orderId !== null ? (
                <>
                  <div className="cd-thread-head">
                    <div>
                      {customerName && <b>{customerName}</b>}
                      {code && <b className="vh-mono">{code}</b>}
                      {type && <span>{t(`ot.${type}`)}</span>}
                    </div>
                    <Link to={orderHref(dock.orderId)} className="vh-link">{t('cd.viewOrder')}</Link>
                  </div>
                  {askErr && <p className="lg-error cd-ask-err" role="alert">{errText(t, askErr)}</p>}
                  <Chat
                    key={dock.orderId}
                    orderId={dock.orderId}
                    orderHref={orderHref(dock.orderId)}
                    bare
                    refresh={refresh}
                    locked={locked}
                    hint={hint}
                    onRead={afterRead}
                  />
                </>
              ) : (
                <p className="cd-note cd-pick">{list.loading ? t('cd.loading') : convos.length ? t('cd.pick') : t(workshop ? 'cd.ws.howTo' : 'cd.howTo')}</p>
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
        aria-label={unread ? t(workshop ? 'cd.ws.openUnread' : 'cd.openUnread', { n: unread }) : t(workshop ? 'cd.ws.title' : 'cd.open')}
        title={t(workshop ? 'cd.ws.title' : 'cd.open')}
        onClick={toggle}
      >
        {dock.open ? <X size={24} aria-hidden /> : <ChatCircleDots size={26} weight="fill" aria-hidden />}
        {!dock.open && unread > 0 && <span className="cd-badge cd-fab-badge">{unread > 99 ? '99+' : unread}</span>}
      </button>
    </div>
  )
}
