import { Fragment, useEffect, useRef, useState, type ReactNode } from 'react'
import { useT } from '../../i18n'
import type { PrivacyPolicy } from '../../services/orders'
import './privacy-dialog.css'

/** `**bold**` inside one line. */
const inline = (s: string): ReactNode[] =>
  s.split(/\*\*(.+?)\*\*/g).map((part, i) => (i % 2 ? <b key={i}>{part}</b> : <Fragment key={i}>{part}</Fragment>))

/** The policy body is light markdown: `#`/`###` headings, `- ` bullets, paragraphs. */
function PolicyBody({ body }: { body: string }) {
  const out: ReactNode[] = []
  let items: string[] = []
  const flush = () => {
    if (!items.length) return
    out.push(<ul key={`u${out.length}`}>{items.map((x, i) => <li key={i}>{inline(x)}</li>)}</ul>)
    items = []
  }
  for (const raw of body.split('\n')) {
    const line = raw.trim()
    if (line.startsWith('- ')) { items.push(line.slice(2)); continue }
    flush()
    if (!line || line === '---') continue
    const h = /^(#{1,4})\s+(.*)$/.exec(line)
    if (h) out.push(<h3 key={out.length}>{inline(h[2])}</h3>)
    else out.push(<p key={out.length}>{inline(line)}</p>)
  }
  flush()
  return <>{out}</>
}

interface Props {
  policy: PrivacyPolicy
  busy: boolean
  onAgree: () => void
  onDecline: () => void
  onClose: () => void
  /** Button texts; the defaults are for the order page after the sketch. */
  agreeLabel?: string
  declineLabel?: string
}

/** The agree button stays disabled until the customer has scrolled the whole policy. */
export default function PrivacyDialog({ policy, busy, onAgree, onDecline, onClose, agreeLabel, declineLabel }: Props) {
  const t = useT()
  const dialog = useRef<HTMLDialogElement>(null)
  const scroller = useRef<HTMLDivElement>(null)
  const [progress, setProgress] = useState(0)
  const [read, setRead] = useState(false)

  useEffect(() => {
    const el = dialog.current!
    const previousOverflow = document.body.style.overflow
    el.showModal()
    document.body.style.overflow = 'hidden'
    return () => {
      el.close()
      document.body.style.overflow = previousOverflow
    }
  }, [])

  const measure = () => {
    const el = scroller.current
    if (!el) return
    const max = el.scrollHeight - el.clientHeight
    const atEnd = max <= 4 || el.scrollTop >= max - 4
    setProgress(max <= 0 ? 1 : Math.min(1, el.scrollTop / max))
    // Once read, stays read: scrolling back up to re-read does not lock the button again.
    if (atEnd) setRead(true)
  }

  useEffect(() => {
    measure()
    const el = scroller.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [policy.body])

  const title = policy.title ?? t('ov.privacyTitle')

  return (
    <dialog ref={dialog} className="pv" aria-labelledby="pv-title" onCancel={onClose}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="pv-card">
        <header className="pv-head">
          <div>
            <h2 id="pv-title">{title}</h2>
            <span className="pv-ver">v{policy.version}</span>
          </div>
          <button className="pv-x" onClick={onClose} aria-label={t('ov.privacyClose')}>×</button>
        </header>
        <div className="pv-bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progress * 100)} aria-label={t('ov.privacyProgress')}>
          <span style={{ width: `${progress * 100}%` }} />
        </div>
        <div className="pv-body" ref={scroller} onScroll={measure} tabIndex={0}>
          <PolicyBody body={policy.body} />
        </div>
        <footer className="pv-foot">
          <p className="pv-hint" role="status">{read ? t('ov.privacyReadDone') : t('ov.privacyScroll')}</p>
          <div className="pv-actions">
            <button className="vh-btn vh-btn--ghost vh-btn--md" disabled={busy} onClick={onDecline}>{declineLabel ?? t('ov.decline')}</button>
            <button className="vh-btn vh-btn--primary vh-btn--md" disabled={busy || !read} onClick={onAgree}>{agreeLabel ?? t('ov.agreeView')}</button>
          </div>
        </footer>
      </div>
    </dialog>
  )
}
