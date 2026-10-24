import { ArrowBendDownRight, ChatCenteredText } from '@phosphor-icons/react'
import { useAsync } from '../../hooks/useAsync'
import { useLocale, useT } from '../../i18n'
import { listQuotations, type WorkOrder, type WorkQuotation } from '../../services/workshop'
import { fmt } from '../../utils/format'

const price = (q: WorkQuotation) => {
  if (q.options.length < 2) return fmt(q.finalTotal)
  const totals = q.options.map((o) => o.total)
  return `${fmt(Math.min(...totals))} – ${fmt(Math.max(...totals))}`
}

/**
 * The quotations the customer sent back with "Ask for changes", newest first, with their note. A request is open until
 * the workshop makes a newer version (the API then marks the old one SUPERSEDED). Renders nothing when there are none.
 */
export default function ChangeRequests({ order }: { order: WorkOrder }) {
  const t = useT()
  const locale = useLocale()
  const list = useAsync(() => listQuotations(order.id), [order.id, order.status])

  const quotes = [...(list.data ?? [])].sort((a, b) => b.version - a.version)
  const asked = quotes.filter((q) => q.customerNote && (q.status === 'CHANGES_REQUESTED' || q.status === 'SUPERSEDED'))
  if (!asked.length) return null

  const open = asked[0].status === 'CHANGES_REQUESTED'
  const day = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString(locale, { day: 'numeric', month: 'short', year: 'numeric' }) : null)
  // The version that answered a request is the first one made after it.
  const answer = (q: WorkQuotation) => quotes.filter((x) => x.version > q.version).at(-1)?.version

  return (
    <section className={`wk-block wk-changes${open ? ' is-open' : ''}`} aria-label={t('wk.cr.title')}>
      <div className="wk-changes-head">
        <h3>
          <ChatCenteredText size={20} weight="bold" aria-hidden />
          {t('wk.cr.title')}
        </h3>
        <span className={`badge${open ? ' ac' : ''}`}>{t(open ? 'wk.cr.open' : 'wk.cr.done')}</span>
      </div>
      {open && <p className="sd-sub">{t(order.status === 'ACCEPTED' ? 'wk.cr.todo' : 'wk.cr.todoLater')}</p>}

      <ol className="wk-changes-list">
        {asked.map((q, i) => {
          const live = i === 0 && open
          const by = answer(q)
          const sent = day(q.sentAt)
          return (
            <li key={q.id} className={live ? 'is-live' : undefined}>
              <div className="wk-changes-meta">
                <span>{t('wk.cr.on', { v: q.version, price: price(q) })}</span>
                {sent && <span>{t('wk.cr.sent', { date: sent })}</span>}
              </div>
              <blockquote className="wk-text">{q.customerNote}</blockquote>
              {!live && by !== undefined && (
                <span className="wk-changes-reply">
                  <ArrowBendDownRight size={14} weight="bold" aria-hidden />
                  {t('wk.cr.answered', { v: by })}
                </span>
              )}
            </li>
          )
        })}
      </ol>
    </section>
  )
}
