import { useEffect, useState } from 'react'
import { useT } from '../../../i18n'
import { selectionSize, sketchPreviewUrl, type AiSelection, type LoadUrl, type SketchInfo } from '../../../services/orderAi'
import SketchPicker from './SketchPicker'

/** A picture that needs the Bearer header, loaded as an object URL. `id` names what is shown, so another one never shows under it. */
export function BlobImage({ id, load, className }: { id: string; load: LoadUrl; className?: string }) {
  const t = useT()
  const [shown, setShown] = useState<{ id: string; src: string } | null>(null)
  const [failedId, setFailedId] = useState('')

  useEffect(() => {
    let made: string | null = null
    let live = true
    load()
      .then((u) => {
        made = u
        if (live) setShown({ id, src: u })
        else URL.revokeObjectURL(u)
      })
      .catch(() => live && setFailedId(id))
    return () => {
      live = false
      if (made) URL.revokeObjectURL(made)
    }
    // `load` is a new function every render; `id` says when the picture is another one.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  // A picture of another version is never shown for this one: it is the previous one until the new one arrives.
  const src = shown?.src ?? null
  if (failedId === id) return <span className="co-hint oa-img-state">{t('oa.imgFailed')}</span>
  if (!src) return <span className="co-hint oa-img-state" aria-busy="true">{t('oa.imgLoading')}</span>
  return <img className={className} src={src} alt={t('oa.imgAlt')} />
}

/** One page of one sketch revision. */
export function SketchImage({ orderId, revisionId, page = 1, className }: { orderId: number; revisionId: number; page?: number; className?: string }) {
  return <BlobImage id={`${orderId}-${revisionId}-${page}`} load={() => sketchPreviewUrl(orderId, revisionId, page)} className={className} />
}

/**
 * The sketch the order will be sent with, in the preview box beside the form. Follows the order's current revision (never a
 * proposal that is not applied). With `selection` the customer can pick parts of it for the assistant.
 */
export default function SketchView({ orderId, sketch, selection, onSelection, pickLocked = false }: {
  orderId: number
  sketch: SketchInfo
  /** Offered only while the assistant is on. */
  selection?: AiSelection
  onSelection?: (s: AiSelection) => void
  /** The assistant is working or a proposal waits: the pick would apply to a sketch that is about to change. */
  pickLocked?: boolean
}) {
  const t = useT()
  const [page, setPage] = useState(1)
  const [picking, setPicking] = useState(false)
  const at = Math.min(page, sketch.pages)
  const picked = selection ? selectionSize(selection) : 0
  const canPick = !!selection && !!onSelection && sketch.document.some((p) => p.strokes.length > 0)

  return (
    <div className="oa-view">
      <SketchImage orderId={orderId} revisionId={sketch.revisionId} page={at} className="oa-view-img" />
      {sketch.pages > 1 && (
        <div className="oa-pager">
          <button type="button" className="co-btn co-btn--line co-btn--sm" disabled={at <= 1} aria-label={t('oa.prevPage')} onClick={() => setPage(at - 1)}>‹</button>
          <span className="vh-mono">{t('oa.page', { n: at, total: sketch.pages })}</span>
          <button type="button" className="co-btn co-btn--line co-btn--sm" disabled={at >= sketch.pages} aria-label={t('oa.nextPage')} onClick={() => setPage(at + 1)}>›</button>
        </div>
      )}
      {canPick && (
        <button type="button" className="co-btn co-btn--line co-btn--sm" disabled={pickLocked} onClick={() => setPicking(true)}>
          {picked ? t('oa.pick.openN', { n: picked }) : t('oa.pick.open')}
        </button>
      )}
      {sketch.inputsChanged && <span className="oa-stale" role="status">{t('oa.outdated')}</span>}
      {picking && selection && onSelection && (
        <SketchPicker sketch={sketch} selection={selection} onChange={onSelection} onClose={() => setPicking(false)} />
      )}
    </div>
  )
}

