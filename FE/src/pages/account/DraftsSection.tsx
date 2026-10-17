import { useEffect, useState } from 'react'
import { ORDER_HREF } from '../../constants'
import { useAsync } from '../../hooks/useAsync'
import { useLocale, useT } from '../../i18n'
import { Link } from '../../router/router'
import { deleteOrder, listOrders, orderErrorKey, type Order, errText } from '../../services/orders'
import { fmt } from '../../utils/format'
import { draftPathFor } from '../create-order/draft'
import './drafts.css'

function ago(iso: string, locale: string) {
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' })
  const s = Math.round((new Date(iso).getTime() - Date.now()) / 1000)
  const a = Math.abs(s)
  if (a < 45) return rtf.format(0, 'second')
  if (a < 3600) return rtf.format(Math.round(s / 60), 'minute')
  if (a < 86400) return rtf.format(Math.round(s / 3600), 'hour')
  return rtf.format(Math.round(s / 86400), 'day')
}

function summary(o: Order, t: ReturnType<typeof useT>): string {
  // The list does not carry the inputs, so a draft is named by its type and size.
  const chars = o.charCount ? ` · ${t('dr.chars', { n: o.charCount })}` : ''
  return `${t(`ot.${o.type}`)}${chars}`
}

/** The customer's unsent orders. They are drafts on the server, so any device sees them. */
export default function DraftsSection({ onCount }: { onCount?: (n: number) => void }) {
  const t = useT()
  const locale = useLocale()
  const list = useAsync(() => listOrders({ status: 'DRAFT', pageSize: 50 }), [])
  const [confirming, setConfirming] = useState<number | null>(null)
  const [err, setErr] = useState('')
  const drafts = list.data?.items ?? []

  useEffect(() => {
    if (list.data) onCount?.(list.data.total)
  }, [list.data, onCount])

  useEffect(() => {
    if (confirming === null) return
    const h = window.setTimeout(() => setConfirming(null), 4000)
    return () => window.clearTimeout(h)
  }, [confirming])

  const remove = async (id: number) => {
    setErr('')
    try {
      await deleteOrder(id)
      setConfirming(null)
      await list.reload()
    } catch (e) {
      setErr(orderErrorKey(e))
    }
  }

  return (
    <div className="dr-section">
      {list.loading && !list.data && <p className="vh-lede" role="status">{t('co.loading')}</p>}
      {!!list.error && <p className="lg-error" role="alert">{errText(t, orderErrorKey(list.error))}</p>}
      {err && <p className="lg-error" role="alert">{errText(t, err)}</p>}
      <ul className="dr-list" aria-label={t('dr.listAria')}>
        {drafts.map((d) => {
          const asking = confirming === d.id
          return (
            <li key={d.id} className="dr-item">
              <div className="dr-main">
                <span className="dr-name">{summary(d, t)}</span>
                <span className="dr-meta vh-mono">{d.code}</span>
                <span className="dr-meta">
                  {t('dr.saved', { time: ago(d.savedAt, locale) })}
                  {' · '}
                  {t(d.quantity > 1 ? 'co.pieces' : 'co.piece', { n: d.quantity })}
                  {' · '}
                  {d.estMax !== null ? t('dr.estimate', { total: d.estMin === d.estMax ? fmt(d.estMax) : `${fmt(d.estMin ?? 0)} – ${fmt(d.estMax)}` }) : t('dr.noEstimate')}
                </span>
              </div>
              <div className="dr-side">
                <Link to={draftPathFor(d.id)} className="vh-btn vh-btn--primary vh-btn--sm dr-continue">{t('dr.continue')}</Link>
                {asking ? (
                  <span className="dr-confirm" role="alert">
                    <span>{t('dr.confirm')}</span>
                    <button className="ct-remove" onClick={() => void remove(d.id)}>{t('dr.yes')}</button>
                    <button className="ct-remove dr-keep" onClick={() => setConfirming(null)}>{t('dr.no')}</button>
                  </span>
                ) : (
                  <button className="ct-remove" onClick={() => setConfirming(d.id)}>{t('dr.delete')}</button>
                )}
              </div>
            </li>
          )
        })}
        <li>
          <Link to={ORDER_HREF} className="dr-new">
            <span className="dr-new-plus" aria-hidden>+</span>
            <span>{t('dr.newOrder')}</span>
          </Link>
        </li>
      </ul>
      {!list.loading && !drafts.length && <p className="dr-empty-note">{t('dr.emptyBody')}</p>}
    </div>
  )
}
