import { CaretLeft } from '@phosphor-icons/react'
import { useState } from 'react'
import Chat from '../../../components/ui/Chat'
import '../../../components/ui/chat-dock.css'
import { STATUS_COLOR } from '../../../constants/orderStatus'
import { useAsync } from '../../../hooks/useAsync'
import { useLocale, useT } from '../../../i18n'
import { Link, orderPath } from '../../../router/router'
import { listConversations, type Conversation } from '../../../services/chat'
import { errText, orderErrorKey, type OrderStatus } from '../../../services/orders'

/** Orders whose chat is read only (same rule as the floating chat). */
const CLOSED: OrderStatus[] = ['REJECTED', 'CANCELLED']

/**
 * The studio side of the assistant panel: the customer's chats with the workshop staff, one per sent order
 * (`GET /me/conversations`). The order being written here is a draft, and the backend opens a chat only once an order is
 * sent (`ORDER_NOT_SUBMITTED`), so the panel says so and lists the chats of the orders already sent.
 */
export default function StaffChat() {
  const t = useT()
  const locale = useLocale()
  const [openId, setOpenId] = useState<number | null>(null)
  const list = useAsync(() => listConversations('customer'), [], 15000)
  const convos = list.data ?? []
  const row = convos.find((c) => c.orderId === openId) ?? null

  const preview = (c: Conversation) => {
    const text = c.last.kind === 'ORDER_CARD' ? t('cd.card') : c.last.body || (c.last.hasAttachment ? t('cd.photo') : '')
    return c.last.mine ? t('cd.you', { text }) : text
  }
  const time = (iso: string) => new Date(iso).toLocaleDateString(locale, { day: 'numeric', month: 'short' })

  if (openId !== null) {
    const href = orderPath(openId, 'review')
    const locked = row && CLOSED.includes(row.status) ? t('chat.closed') : undefined
    const hint = row && row.status === 'SUBMITTED' ? t('cd.unclaimedHint') : undefined
    return (
      <div className="oa-staff" role="region" aria-label={t('cd.title')}>
        <div className="oa-staff-head">
          <button type="button" className="oa-tool" title={t('cd.back')} onClick={() => setOpenId(null)}>
            <CaretLeft aria-hidden="true" weight="bold" /><span className="oa-sr">{t('cd.back')}</span>
          </button>
          {row && <b className="vh-mono">{row.code}</b>}
          {row && <span className="oa-fine">{t(`ot.${row.type}`)}</span>}
          <Link to={href} className="vh-link oa-staff-view">{t('cd.viewOrder')}</Link>
        </div>
        <Chat key={openId} orderId={openId} orderHref={href} locked={locked} hint={hint} bare onRead={() => void list.reload()} />
      </div>
    )
  }

  return (
    <div className="oa-staff" role="region" aria-label={t('cd.title')}>
      <p className="oa-staff-note" role="note">{t('oa.staffDraft')}</p>
      {list.loading && !list.data && <p className="oa-fine">{t('cd.loading')}</p>}
      {!!list.error && !list.data && <p className="lg-error" role="alert">{errText(t, orderErrorKey(list.error))}</p>}
      {list.data && !convos.length && <p className="oa-fine">{t('cd.noOrders')}</p>}
      {!!convos.length && (
        <nav className="oa-staff-list" aria-label={t('cd.threads')}>
          {convos.map((c) => (
            <button key={c.orderId} type="button" className="cd-item" onClick={() => setOpenId(c.orderId)}>
              <span className="cd-item-top">
                <b className="vh-mono">{c.code}</b>
                <span className="cd-item-time">{time(c.last.createdAt)}</span>
              </span>
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
      )}
    </div>
  )
}
