import { Eye, EyeSlash, Star } from '@phosphor-icons/react'
import { useState } from 'react'
import Shell from '../../components/ws/Shell'
import { useAsync } from '../../hooks/useAsync'
import { useLocale, useT } from '../../i18n'
import { Link } from '../../router/router'
import { managerReviews, setReviewHidden, type ManagedReview } from '../../services/managerOps'
import { errText, orderErrorKey } from '../../services/orders'
import { Chip, Panel, Period } from './managerKit'

const PAGE_SIZE = 20
const SHOW = ['all', 'shown', 'hidden'] as const
const STARS = [0, 5, 4, 3, 2, 1] as const

/**
 * Manager review moderation (FR-58, `GET /manager/reviews`): every customer review, newest first, filtered by visibility and
 * stars. A review is hidden from the public page or shown again with a reason (5 to 300 characters, kept in the audit log); it is
 * never deleted. Comments are the customers' own words and are shown as written.
 */
export default function Reviews() {
  const t = useT()
  const locale = useLocale()
  const [show, setShow] = useState<(typeof SHOW)[number]>('all')
  const [rating, setRating] = useState<(typeof STARS)[number]>(0)
  const [page, setPage] = useState(1)
  const list = useAsync(
    () => managerReviews({ hidden: show === 'all' ? undefined : show === 'hidden', rating: rating || undefined, page, pageSize: PAGE_SIZE }),
    [show, rating, page],
  )
  const [reasons, setReasons] = useState<Record<number, string>>({})
  const [busy, setBusy] = useState<number | null>(null)
  const [err, setErr] = useState('')
  const [done, setDone] = useState('')

  const toggle = async (r: ManagedReview) => {
    const reason = (reasons[r.id] ?? '').trim()
    if (busy !== null || reason.length < 5) return
    setBusy(r.id); setErr(''); setDone('')
    try {
      await setReviewHidden(r.id, !r.hidden, reason)
      setReasons((x) => ({ ...x, [r.id]: '' }))
      setDone(t(r.hidden ? 'mgr.rv.shownDone' : 'mgr.rv.hiddenDone'))
      await list.reload()
    } catch (e) {
      setErr(errText(t, orderErrorKey(e)))
    } finally {
      setBusy(null)
    }
  }

  const when = (iso: string) => new Date(iso).toLocaleString(locale, { dateStyle: 'medium', timeStyle: 'short' })
  const pages = list.data ? Math.max(1, Math.ceil(list.data.total / list.data.pageSize)) : 1

  return (
    <Shell area="manager" active="reviews" title={t('mgr.nav.reviews')}>
      {err && <p className="lg-error" role="alert">{err}</p>}
      {done && <p className="note-ok" role="status">{done}</p>}

      <Panel title={t('mgr.rv.filters')} sub={t('mgr.rv.sub')}>
        <div className="mgr-filters">
          <div className="mgr-field-group">
            <span>{t('mgr.rv.show')}</span>
            <Period options={SHOW} value={show} onChange={(v) => { setShow(v); setPage(1) }} label={t('mgr.rv.show')} text={(v) => t(`mgr.rv.show.${v}`)} />
          </div>
          <div className="mgr-field-group">
            <span>{t('mgr.rv.stars')}</span>
            <Period options={STARS} value={rating} onChange={(v) => { setRating(v); setPage(1) }} label={t('mgr.rv.stars')} text={(v) => (v ? t('mgr.rv.starsN', { n: v }) : t('mgr.rv.show.all'))} />
          </div>
        </div>
      </Panel>

      {!!list.error && <p className="lg-error" role="alert">{errText(t, orderErrorKey(list.error))}</p>}
      {list.loading && !list.data && <p className="sub" role="status">{t('co.loading')}</p>}
      {list.data && !list.data.items.length && <div className="mgr-empty"><b>{t('mgr.rv.none')}</b></div>}

      <div className="mgr-alerts">
        {(list.data?.items ?? []).map((r) => {
          const reason = reasons[r.id] ?? ''
          return (
            <article key={r.id} className={`mgr-alert${r.hidden ? ' off' : ''}`} aria-label={t('mgr.rv.aria', { code: r.orderCode, n: r.rating })}>
              <div className="mgr-alert-head">
                <span className="mgr-stars" aria-label={t('mgr.rv.starsN', { n: r.rating })}>
                  {[1, 2, 3, 4, 5].map((n) => <Star key={n} size={16} weight={n <= r.rating ? 'fill' : 'regular'} aria-hidden />)}
                </span>
                <b>{r.customerName}</b>
                <Link to={`/staff/review/${r.orderId}`} className="vh-link">{r.orderCode}</Link>
                <span className="sub">{when(r.createdAt)}</span>
                {r.hidden
                  ? <Chip tone="mute" icon={<EyeSlash size={14} aria-hidden />}>{t('mgr.rv.isHidden')}</Chip>
                  : <Chip tone="good" icon={<Eye size={14} aria-hidden />}>{t('mgr.rv.isShown')}</Chip>}
              </div>
              {r.comment ? <p>{r.comment}</p> : <p className="sub">{t('mgr.rv.noComment')}</p>}
              {r.photos.some((p) => p.url) && (
                <div className="mgr-photos">
                  {r.photos.filter((p) => p.url).map((p, i) => (
                    <a key={p.id} href={p.url ?? undefined} target="_blank" rel="noreferrer"><img src={p.url ?? undefined} alt={t('mgr.rv.photo', { n: i + 1, code: r.orderCode })} loading="lazy" /></a>
                  ))}
                </div>
              )}
              {r.hidden && r.hiddenAt && <p className="sub">{t('mgr.rv.hiddenAt', { when: when(r.hiddenAt) })}</p>}
              <div className="mgr-actions">
                <label className="vh-label">
                  {t('mgr.rv.reason')}
                  <input className="vh-input" value={reason} maxLength={300} placeholder={t('mgr.rv.reasonPh')} onChange={(e) => setReasons({ ...reasons, [r.id]: e.target.value })} />
                </label>
                <button type="button" className={`btn sm ${r.hidden ? 'acc' : 'danger'}`} disabled={busy !== null || reason.trim().length < 5} onClick={() => void toggle(r)}>
                  {r.hidden ? <Eye size={16} aria-hidden /> : <EyeSlash size={16} aria-hidden />}{t(busy === r.id ? 'mgr.working' : r.hidden ? 'mgr.rv.unhide' : 'mgr.rv.hide')}
                </button>
              </div>
            </article>
          )
        })}
      </div>

      {list.data && pages > 1 && (
        <div className="mgr-pager">
          <span>{t('mgr.pager', { page, pages })}</span>
          <div>
            <button type="button" className="btn ghost sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>{t('mgr.prev')}</button>
            <button type="button" className="btn ghost sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>{t('mgr.next')}</button>
          </div>
        </div>
      )}
    </Shell>
  )
}
