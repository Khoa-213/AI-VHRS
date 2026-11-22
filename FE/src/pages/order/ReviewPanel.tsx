import { ImageSquare, Star, X } from '@phosphor-icons/react'
import { useRef, useState } from 'react'
import { useAsync } from '../../hooks/useAsync'
import { useLocale, useT } from '../../i18n'
import { errText, orderErrorKey } from '../../services/orders'
import {
  REVIEW_MAX_COMMENT, REVIEW_MAX_MB, REVIEW_MAX_PHOTOS, REVIEW_TYPES, createOrderReview, getOrderReview, updateOrderReview, uploadReviewPhoto,
  type OrderReview,
} from '../../services/reviews'
import './review.css'

/** A photo in the form: one already saved on the review (with its link) or one just uploaded (path only). */
/** JPG or PNG, not empty and within the size limit. */
const fileOk = (f: File) => {
  const limit = REVIEW_MAX_MB * 1048576
  if (f.size <= 0) return false
  return REVIEW_TYPES.includes(f.type) && limit >= f.size
}
interface Shot { path: string; url: string | null }

/**
 * The customer's review of a completed order: shown once written, editable until `editable_until` unless a Manager hid it.
 * Rating, comment and photos go to `/orders/{id}/review`; photos are uploaded to storage first, then sent by path.
 */
export default function ReviewPanel({ orderId }: { orderId: number }) {
  const t = useT()
  const locale = useLocale()
  const q = useAsync(() => getOrderReview(orderId), [orderId])
  const [editing, setEditing] = useState(false)
  // The edit window is checked against when the page opened; the server has the final word on save.
  const [openedAt] = useState(() => Date.now())
  const review = q.data ?? null
  const day = (iso: string) => new Date(iso).toLocaleDateString(locale, { day: 'numeric', month: 'short', year: 'numeric' })
  const canEdit = !!review && !review.hidden && Date.parse(review.editableUntil) > openedAt

  return (
    <section className="rv-panel" aria-labelledby={`rv-h-${orderId}`}>
      <h3 id={`rv-h-${orderId}`}>{t('rv.title')}</h3>
      {q.loading && <p className="co-fine" role="status">{t('co.loading')}</p>}
      {q.error != null && (
        <div className="vh-callout vh-callout--red" role="alert">
          <span>{errText(t, orderErrorKey(q.error))}</span>
          <button type="button" className="vh-btn vh-btn--ghost vh-btn--md" onClick={() => void q.reload()}>{t('dl.retry')}</button>
        </div>
      )}
      {!q.loading && !q.error && (editing || !review
        ? <ReviewForm orderId={orderId} review={review} onCancel={review ? () => setEditing(false) : undefined}
            onSaved={async () => { setEditing(false); await q.reload() }} />
        : review && (
          <div className="rv-view">
            <Stars value={review.rating} />
            {review.comment && <p className="rv-comment">{review.comment}</p>}
            {review.photos.length > 0 && <ul className="rv-photos">{review.photos.map((p) => (
              <li key={p.id}>{p.url ? <a href={p.url} target="_blank" rel="noreferrer"><img src={p.url} alt={t('rv.photoAlt')} loading="lazy" /></a> : <span className="rv-photo-off"><ImageSquare size={20} aria-hidden /></span>}</li>
            ))}</ul>}
            {review.hidden
              ? <p className="vh-callout vh-callout--red">{t('rv.hidden')}</p>
              : <p className="co-fine">{canEdit ? t('rv.editUntil', { date: day(review.editableUntil) }) : t('rv.editClosed')}</p>}
            {canEdit && <button type="button" className="vh-btn vh-btn--ghost vh-btn--md" onClick={() => setEditing(true)}>{t('rv.edit')}</button>}
          </div>
        ))}
    </section>
  )
}

function Stars({ value }: { value: number }) {
  const t = useT()
  return (
    <span className="rv-stars" role="img" aria-label={t('rv.starsOf', { n: value })}>
      {[1, 2, 3, 4, 5].map((n) => <Star key={n} size={20} weight={n <= value ? 'fill' : 'regular'} aria-hidden />)}
      <span className="rv-stars-n">{t('rv.starsOf', { n: value })}</span>
    </span>
  )
}

function ReviewForm({ orderId, review, onSaved, onCancel }: {
  orderId: number; review: OrderReview | null; onSaved: () => unknown; onCancel?: () => void
}) {
  const t = useT()
  const [rating, setRating] = useState(review?.rating ?? 0)
  const [comment, setComment] = useState(review?.comment ?? '')
  const [shots, setShots] = useState<Shot[]>(review?.photos.map((p) => ({ path: p.path, url: p.url })) ?? [])
  const [busy, setBusy] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [err, setErr] = useState('')
  const lock = useRef(false)
  const file = useRef<HTMLInputElement>(null)

  const add = async (files: FileList | null) => {
    if (!files?.length) return
    setErr('')
    const room = REVIEW_MAX_PHOTOS - shots.length
    const picked = [...files].slice(0, room)
    if (files.length > room) setErr(t('rv.tooMany', { n: REVIEW_MAX_PHOTOS }))
    const bad = picked.find((f) => !fileOk(f))
    if (bad) { setErr(t('rv.badFile', { mb: REVIEW_MAX_MB })); if (file.current) file.current.value = ''; return }
    setUploading(true)
    try {
      for (const f of picked) {
        const path = await uploadReviewPhoto(orderId, f)
        setShots((s) => [...s, { path, url: URL.createObjectURL(f) }])
      }
    } catch (e) {
      setErr(errText(t, orderErrorKey(e)))
    } finally {
      setUploading(false)
      if (file.current) file.current.value = ''
    }
  }

  const save = async () => {
    if (lock.current || rating < 1) return
    lock.current = true
    setBusy(true); setErr('')
    const body = { rating, comment: comment.trim() || null, photos: shots.map((s) => s.path) }
    try {
      if (review) await updateOrderReview(orderId, body)
      else await createOrderReview(orderId, body)
      await onSaved()
    } catch (e) {
      setErr(errText(t, orderErrorKey(e)))
    } finally {
      lock.current = false
      setBusy(false)
    }
  }

  return (
    <form className="rv-form vh-stack" onSubmit={(e) => { e.preventDefault(); void save() }}>
      {!review && <p className="co-fine">{t('rv.invite')}</p>}
      <fieldset className="rv-rate" disabled={busy}>
        <legend className="vh-label">{t('rv.rating')}</legend>
        <div className="rv-rate-row">
          {[1, 2, 3, 4, 5].map((n) => (
            <label key={n} className={n <= rating ? 'on' : undefined}>
              <input type="radio" name={`rv-rating-${orderId}`} value={n} checked={rating === n} onChange={() => setRating(n)} />
              <Star size={28} weight={n <= rating ? 'fill' : 'regular'} aria-hidden />
              <span className="rv-sr">{t('rv.starsOf', { n })}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <label className="vh-stack" style={{ gap: 6 }}>
        <span className="vh-label">{t('rv.comment')}</span>
        <textarea className="vh-textarea" rows={4} maxLength={REVIEW_MAX_COMMENT} value={comment} disabled={busy} onChange={(e) => setComment(e.target.value)} />
        <span className="co-fine">{t('rv.chars', { n: comment.length, max: REVIEW_MAX_COMMENT })}</span>
      </label>
      <div className="vh-stack" style={{ gap: 8 }}>
        <span className="vh-label">{t('rv.photos', { n: shots.length, max: REVIEW_MAX_PHOTOS })}</span>
        {shots.length > 0 && <ul className="rv-photos">{shots.map((s) => (
          <li key={s.path}>
            {s.url ? <img src={s.url} alt={t('rv.photoAlt')} /> : <span className="rv-photo-off"><ImageSquare size={20} aria-hidden /></span>}
            <button type="button" className="rv-remove" aria-label={t('rv.removePhoto')} title={t('rv.removePhoto')} disabled={busy || uploading}
              onClick={() => setShots(shots.filter((x) => x.path !== s.path))}><X size={14} aria-hidden /></button>
          </li>
        ))}</ul>}
        {shots.length < REVIEW_MAX_PHOTOS && (
          <label className="vh-btn vh-btn--ghost vh-btn--md rv-add">
            <ImageSquare size={18} aria-hidden />{t(uploading ? 'rv.uploading' : 'rv.addPhoto')}
            <input ref={file} type="file" accept={REVIEW_TYPES.join(',')} multiple disabled={busy || uploading} className="rv-sr" onChange={(e) => void add(e.target.files)} />
          </label>
        )}
        <span className="co-fine">{t('rv.photoRule', { n: REVIEW_MAX_PHOTOS, mb: REVIEW_MAX_MB })}</span>
      </div>
      {err && <p className="vh-callout vh-callout--red" role="alert">{err}</p>}
      {rating < 1 && <p className="co-fine">{t('rv.needRating')}</p>}
      <div className="rv-actions">
        {onCancel && <button type="button" className="vh-btn vh-btn--ghost vh-btn--md" disabled={busy} onClick={onCancel}>{t('ov.back')}</button>}
        <button type="submit" className="vh-btn vh-btn--primary vh-btn--md" disabled={busy || uploading || rating < 1}>
          {t(busy ? 'rv.saving' : review ? 'rv.saveEdit' : 'rv.send')}
        </button>
      </div>
    </form>
  )
}
