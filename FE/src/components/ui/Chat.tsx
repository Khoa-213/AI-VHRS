import { ArrowSquareOut } from '@phosphor-icons/react'
import { useEffect, useRef, useState } from 'react'
import { STATUS_COLOR } from '../../constants/orderStatus'
import { useAsync } from '../../hooks/useAsync'
import { useLocale, useT } from '../../i18n'
import { Link } from '../../router/router'
import { orderErrorKey, errText } from '../../services/orders'
import { CHAT_IMAGES, CHAT_MAX_MB, listMessages, markMessagesRead, sendMessage, type Message } from '../../services/workshop'
import { fmt } from '../../utils/format'
import './chat.css'

/** An `ORDER_CARD` message: the order the customer is asking about, in its current state. */
function CardBody({ m, href }: { m: Message; href: string }) {
  const t = useT()
  const c = m.card
  if (!c) return null
  return (
    <>
      <span className="chat-card-tag">{t(m.mine ? 'cd.asking' : 'cd.askingThem')}</span>
      <div className="chat-card">
        <b className="vh-mono">{c.code}</b>
        <span>{t(`ot.${c.type}`)}</span>
        <span className="vh-chip" style={{ color: STATUS_COLOR[c.status] }}>{t(`os.${c.status}`)}</span>
        <span className="chat-card-meta">
          {t('cd.qty', { n: c.quantity })}
          {c.total !== null && <> · <span className="vh-mono">{fmt(c.total)}</span></>}
        </span>
      </div>
      <Link to={href} className="chat-card-link">{t('cd.viewOrder')} <ArrowSquareOut size={14} aria-hidden /></Link>
    </>
  )
}

/**
 * The conversation on one order, shared by the customer and the workshop. New messages are picked up every 10 seconds, and
 * again whenever `refresh` changes. `locked` replaces the compose box with a note (closed order, order not claimed yet);
 * `hint` sits above it. `orderHref` is where an order card links to. `bare` drops the heading.
 */
export default function Chat({ orderId, orderHref, locked, hint, refresh = 0, bare = false, onRead }: {
  orderId: number
  orderHref: string
  locked?: string
  hint?: string
  refresh?: number
  bare?: boolean
  onRead?: () => void
}) {
  const t = useT()
  const locale = useLocale()
  const list = useAsync(() => listMessages(orderId), [orderId, refresh], 10000)
  const [text, setText] = useState('')
  const [image, setImage] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const end = useRef<HTMLDivElement>(null)
  const file = useRef<HTMLInputElement>(null)
  const messages = list.data?.items ?? []
  const unread = list.data?.unread ?? 0
  const read = useRef(onRead)
  useEffect(() => {
    read.current = onRead
  })

  useEffect(() => {
    if (unread > 0) void markMessagesRead(orderId).then(() => read.current?.(), () => undefined)
  }, [unread, orderId])
  useEffect(() => {
    end.current?.scrollIntoView({ block: 'nearest' })
  }, [messages.length])

  const pick = (f: File | undefined) => {
    if (!f) return
    if (!CHAT_IMAGES.includes(f.type)) return setErr('err.fileType')
    if (f.size > CHAT_MAX_MB * 1024 * 1024) return setErr('err.fileTooLarge')
    setErr('')
    setImage(f)
  }

  const send = async () => {
    if (busy || (!text.trim() && !image)) return
    setBusy(true)
    setErr('')
    try {
      await sendMessage(orderId, text, image ?? undefined)
      setText('')
      setImage(null)
      await list.reload()
    } catch (e) {
      setErr(orderErrorKey(e))
    } finally {
      setBusy(false)
    }
  }

  const when = (iso: string) => new Date(iso).toLocaleString(locale, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })

  return (
    <section className="chat" aria-label={t('chat.title')}>
      {!bare && <h2 className="chat-title">{t('chat.title')}{unread > 0 && <b className="chat-unread vh-mono">{unread}</b>}</h2>}
      <div className="chat-log" role="log" aria-live="polite">
        {!!list.error && !list.data && <p className="chat-note">{errText(t, orderErrorKey(list.error))}</p>}
        {list.data && !messages.length && <p className="chat-note">{t('chat.empty')}</p>}
        {messages.map((m) => (
          <div key={m.id} className={`chat-msg${m.mine ? ' mine' : ''}${m.kind === 'ORDER_CARD' ? ' chat-msg--card' : ''}`}>
            {m.kind === 'ORDER_CARD' && <CardBody m={m} href={orderHref} />}
            {m.kind !== 'ORDER_CARD' && m.body && <p>{m.body}</p>}
            {m.attachments.map((a) => (
              <a key={a.url} href={a.url} target="_blank" rel="noreferrer"><img src={a.url} alt={t('chat.image')} /></a>
            ))}
            <span className="chat-time vh-mono">{when(m.createdAt)}</span>
          </div>
        ))}
        <div ref={end} />
      </div>

      {locked ? (
        <p className="chat-note">{locked}</p>
      ) : (
        <div className="chat-compose">
          {hint && <p className="chat-note">{hint}</p>}
          {err && <p className="lg-error" role="alert">{errText(t, err)}</p>}
          <textarea
            className="vh-textarea"
            rows={2}
            maxLength={2000}
            value={text}
            placeholder={t('chat.placeholder')}
            aria-label={t('chat.placeholder')}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="chat-actions">
            <input ref={file} type="file" accept={CHAT_IMAGES.join(',')} hidden onChange={(e) => { pick(e.target.files?.[0]); e.target.value = '' }} />
            <button type="button" className="vh-btn vh-btn--ghost vh-btn--sm" onClick={() => file.current?.click()}>
              {image ? t('chat.imageChosen') : t('chat.attach')}
            </button>
            {image && <button type="button" className="vh-link" onClick={() => setImage(null)}>{t('co.remove')}</button>}
            <button type="button" className="vh-btn vh-btn--primary vh-btn--sm" disabled={busy || (!text.trim() && !image)} onClick={() => void send()}>
              {t(busy ? 'chat.sending' : 'chat.send')}
            </button>
          </div>
        </div>
      )}
    </section>
  )
}
