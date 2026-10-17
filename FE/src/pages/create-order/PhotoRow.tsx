import { useEffect, useState } from 'react'
import { useT } from '../../i18n'
import { cropOf, getInputFileUrl, type CropBox, type OrderInput } from '../../services/orders'

const num = (v: unknown): number | null => (typeof v === 'number' ? v : null)

/**
 * One uploaded photo with the backend's quality reading, rotate buttons and a crop made of four edge sliders.
 * `onEdit` sends the change; the backend analyses the photo again, so the quality and the price follow.
 */
export default function PhotoRow({
  orderId, input, index, busy, onEdit, onRemove,
}: {
  orderId: number
  input: OrderInput
  index: number
  busy: boolean
  onEdit: (patch: { rotation_deg?: 0 | 90 | 180 | 270; crop_box?: CropBox | null }) => void
  onRemove: () => void
}) {
  const t = useT()
  const pdf = input.mime === 'application/pdf'
  const [url, setUrl] = useState<string | null>(null)
  const [nat, setNat] = useState<{ w: number; h: number } | null>(null)
  const saved = cropOf(input)
  // Edge trims in percent: how much is cut from the left, top, right and bottom of the rotated photo.
  const [trim, setTrim] = useState(() => ({
    l: Math.round((saved?.x ?? 0) * 100),
    t: Math.round((saved?.y ?? 0) * 100),
    r: Math.round((1 - (saved ? saved.x + saved.w : 1)) * 100),
    b: Math.round((1 - (saved ? saved.y + saved.h : 1)) * 100),
  }))

  useEffect(() => {
    if (pdf) return
    let live = true
    getInputFileUrl(orderId, input.id).then((u) => live && setUrl(u)).catch(() => undefined)
    return () => {
      live = false
    }
  }, [orderId, input.id, pdf])

  const q = input.quality
  const rot = input.rotation
  const swap = rot === 90 || rot === 270
  const W = nat ? (swap ? nat.h : nat.w) : 1
  const H = nat ? (swap ? nat.w : nat.h) : 1
  const rotate = (by: 90 | -90) => onEdit({ rotation_deg: ((((rot + by) % 360) + 360) % 360) as 0 | 90 | 180 | 270 })

  const setEdge = (k: 'l' | 't' | 'r' | 'b', v: number) => {
    const next = { ...trim, [k]: v }
    // Keep at least 10% of the photo in each direction.
    if (next.l + next.r > 90 || next.t + next.b > 90) return
    setTrim(next)
  }
  const dirty = trim.l + trim.t + trim.r + trim.b > 0
  const applyCrop = () => onEdit({ crop_box: { x: trim.l / 100, y: trim.t / 100, w: 1 - (trim.l + trim.r) / 100, h: 1 - (trim.t + trim.b) / 100 } })
  const resetCrop = () => {
    setTrim({ l: 0, t: 0, r: 0, b: 0 })
    if (saved) onEdit({ crop_box: null })
  }

  return (
    <div className="co-photo">
      <div className="co-photo-head">
        <div className="co-file-text">
          <span className="co-file-name">{t('co.photoN', { n: index })}</span>
          <span className={`co-file-ok vh-mono${input.qualityWarning ? ' warn' : ''}`}>{t(input.qualityWarning ? 'co.qualityWarn' : 'co.fileReady')}</span>
        </div>
        <button className="vh-btn vh-btn--ghost vh-btn--sm" disabled={busy} onClick={onRemove}>{t('co.remove')}</button>
      </div>

      {!pdf && (
        <div className="co-photo-body">
          <div className="co-photo-frame" style={{ aspectRatio: `${W} / ${H}` }}>
            {url && (
              <img
                src={url}
                alt={t('co.photoN', { n: index })}
                onLoad={(e) => setNat({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
                style={{ width: swap ? `${(H / W) * 100}%` : '100%', transform: `translate(-50%, -50%) rotate(${rot}deg)` }}
              />
            )}
            {dirty && (
              <span
                className="co-photo-crop"
                style={{ left: `${trim.l}%`, top: `${trim.t}%`, right: `${trim.r}%`, bottom: `${trim.b}%` }}
                aria-hidden
              />
            )}
          </div>

          <div className="co-photo-tools">
            <div className="co-photo-rot">
              <button className="vh-btn vh-btn--ghost vh-btn--sm" disabled={busy} onClick={() => rotate(-90)}>{t('co.rotateLeft')}</button>
              <button className="vh-btn vh-btn--ghost vh-btn--sm" disabled={busy} onClick={() => rotate(90)}>{t('co.rotateRight')}</button>
            </div>
            {(['l', 't', 'r', 'b'] as const).map((k) => (
              <label key={k} className="co-photo-slider">
                <span>{t(`co.trim.${k}`)} <b className="vh-mono">{trim[k]}%</b></span>
                <input type="range" min={0} max={80} step={1} value={trim[k]} onChange={(e) => setEdge(k, Number(e.target.value))} />
              </label>
            ))}
            <div className="co-photo-rot">
              <button className="vh-btn vh-btn--primary vh-btn--sm" disabled={busy || !dirty} onClick={applyCrop}>{t('co.applyCrop')}</button>
              <button className="vh-btn vh-btn--ghost vh-btn--sm" disabled={busy || (!dirty && !saved)} onClick={resetCrop}>{t('co.resetCrop')}</button>
            </div>
          </div>
        </div>
      )}

      {q && num(q.chars_estimate) !== null && (
        <p className="co-meta vh-mono">
          {t('co.photoRead', {
            min: num(q.chars_min) ?? 0, max: num(q.chars_max) ?? 0,
            sharp: Math.round(num(q.sharpness) ?? 0), light: Math.round(num(q.brightness) ?? 0),
          })}
        </p>
      )}
      {pdf && <p className="co-meta">{t('co.pdfNote')}</p>}
    </div>
  )
}
