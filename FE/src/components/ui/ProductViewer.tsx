import { ArrowClockwise, ArrowCounterClockwise, ArrowUUpLeft, ArrowsClockwise, MagnifyingGlassMinus, MagnifyingGlassPlus } from '@phosphor-icons/react'
import { useRef, useState, type KeyboardEvent, type PointerEvent } from 'react'
import { useT } from '../../i18n'
import type { PhotoKind } from '../../services/orders'
import './product-viewer.css'

const KINDS: PhotoKind[] = ['OVERALL', 'CLOSE_UP', 'OTHER']
const TILT = 35
const ZOOM_MIN = 1
const ZOOM_MAX = 3

interface View { ry: number; rx: number; zoom: number }
const FLAT: View = { ry: 0, rx: 0, zoom: 1 }

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))

/**
 * The QC photos of the written product, grouped by view (overall, close-up, other). The photo sits on a sheet the
 * customer can turn a full 360 degrees, tilt and zoom, by dragging, with the buttons or with the keyboard. Only the
 * front is photographed, so the back of the sheet says so instead of showing anything made up.
 */
export default function ProductViewer({ photos }: { photos: { id: number; kind: PhotoKind; url: string | null }[] }) {
  const t = useT()
  const first = KINDS.find((k) => photos.some((p) => p.kind === k)) ?? 'OVERALL'
  const [kind, setKind] = useState<PhotoKind>(first)
  const [idx, setIdx] = useState(0)
  const [view, setView] = useState<View>(FLAT)
  const [dragging, setDragging] = useState(false)
  const [spinning, setSpinning] = useState(false)
  const last = useRef<{ x: number; y: number } | null>(null)

  const shown = photos.filter((p) => p.kind === kind)
  const photo = shown[Math.min(idx, shown.length - 1)]

  // A new photo starts flat and facing the customer.
  const show = (k: PhotoKind, i: number) => {
    setKind(k)
    setIdx(i)
    setView(FLAT)
    setSpinning(false)
  }
  const turn = (deg: number) => setView((v) => ({ ...v, ry: v.ry + deg }))
  const tilt = (deg: number) => setView((v) => ({ ...v, rx: clamp(v.rx + deg, -TILT, TILT) }))
  const zoomBy = (d: number) => setView((v) => ({ ...v, zoom: clamp(Math.round((v.zoom + d) * 10) / 10, ZOOM_MIN, ZOOM_MAX) }))
  const spin = () => {
    // With reduced motion there is no transition to wait for, so the turn just happens.
    if (!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) setSpinning(true)
    turn(360)
  }

  const onDown = (e: PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return
    e.currentTarget.setPointerCapture(e.pointerId)
    last.current = { x: e.clientX, y: e.clientY }
    setDragging(true)
    setSpinning(false)
  }
  const onMove = (e: PointerEvent<HTMLDivElement>) => {
    if (!last.current) return
    const dx = e.clientX - last.current.x
    const dy = e.clientY - last.current.y
    last.current = { x: e.clientX, y: e.clientY }
    setView((v) => ({ ...v, ry: v.ry + dx * 0.5, rx: clamp(v.rx - dy * 0.3, -TILT, TILT) }))
  }
  const onUp = () => {
    last.current = null
    setDragging(false)
  }

  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const act: Record<string, () => void> = {
      ArrowLeft: () => turn(-15),
      ArrowRight: () => turn(15),
      ArrowUp: () => tilt(5),
      ArrowDown: () => tilt(-5),
      '+': () => zoomBy(0.25),
      '=': () => zoomBy(0.25),
      '-': () => zoomBy(-0.25),
      '0': () => setView(FLAT),
    }
    const fn = act[e.key]
    if (!fn) return
    e.preventDefault()
    setSpinning(false)
    fn()
  }

  const deg = ((Math.round(view.ry) % 360) + 360) % 360
  const kindLabel = t(`pv.kind.${kind}`)

  return (
    <div className="pvw">
      <div className="pvw-tabs" role="tablist" aria-label={t('pv.views')}>
        {KINDS.map((k) => {
          const n = photos.filter((p) => p.kind === k).length
          return (
            <button key={k} type="button" role="tab" aria-selected={k === kind} disabled={!n} className={`pvw-tab${k === kind ? ' on' : ''}`} onClick={() => show(k, 0)}>
              {t(`pv.kind.${k}`)}
              <span className="pvw-count">{n}</span>
            </button>
          )
        })}
      </div>

      <div
        className={`pvw-stage${dragging ? ' grabbing' : ''}`}
        tabIndex={0}
        role="group"
        aria-label={t('pv.stage', { view: kindLabel })}
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
        onPointerCancel={onUp}
        onKeyDown={onKey}
      >
        {photo ? (
          <div
            className={`pvw-card${dragging ? ' live' : ''}${spinning ? ' spin' : ''}`}
            style={{ transform: `scale(${view.zoom}) rotateX(${view.rx}deg) rotateY(${view.ry}deg)` }}
            onTransitionEnd={() => setSpinning(false)}
          >
            {photo.url
              ? <img className="pvw-front" src={photo.url} alt={t(`ov.photo.${photo.kind}`)} draggable={false} />
              : <span className="pvw-front pvw-wait">{t('opv.loading')}</span>}
            <div className="pvw-back" aria-hidden><span>{t('pv.back')}</span></div>
          </div>
        ) : (
          <span className="opv-note">{t('pv.none')}</span>
        )}
      </div>

      <div className="pvw-bar">
        <div className="pvw-tools">
          <button type="button" className="pvw-tool" aria-label={t('pv.turnLeft')} title={t('pv.turnLeft')} onClick={() => turn(-45)}><ArrowCounterClockwise size={18} aria-hidden /></button>
          <button type="button" className="pvw-tool" aria-label={t('pv.turnRight')} title={t('pv.turnRight')} onClick={() => turn(45)}><ArrowClockwise size={18} aria-hidden /></button>
          <button type="button" className="pvw-tool pvw-tool--wide" disabled={spinning || !photo} onClick={spin}><ArrowsClockwise size={18} aria-hidden />{t('pv.spin')}</button>
          <button type="button" className="pvw-tool" aria-label={t('pv.zoomOut')} title={t('pv.zoomOut')} disabled={view.zoom <= ZOOM_MIN} onClick={() => zoomBy(-0.25)}><MagnifyingGlassMinus size={18} aria-hidden /></button>
          <button type="button" className="pvw-tool" aria-label={t('pv.zoomIn')} title={t('pv.zoomIn')} disabled={view.zoom >= ZOOM_MAX} onClick={() => zoomBy(0.25)}><MagnifyingGlassPlus size={18} aria-hidden /></button>
          <button type="button" className="pvw-tool" aria-label={t('pv.reset')} title={t('pv.reset')} onClick={() => setView(FLAT)}><ArrowUUpLeft size={18} aria-hidden /></button>
        </div>
        <span className="pvw-read vh-mono" aria-live="polite">{t('pv.readout', { deg, zoom: view.zoom.toFixed(2).replace(/\.?0+$/, '') })}</span>
      </div>

      {shown.length > 1 && (
        <div className="pvw-thumbs" role="tablist" aria-label={t('pv.photosOf', { view: kindLabel })}>
          {shown.map((p, i) => (
            <button key={p.id} type="button" role="tab" aria-selected={p.id === photo?.id} className={`pvw-thumb${p.id === photo?.id ? ' on' : ''}`} onClick={() => show(kind, i)}>
              {p.url ? <img src={p.url} alt={t('pv.photoN', { n: i + 1, total: shown.length })} draggable={false} /> : <span>{i + 1}</span>}
            </button>
          ))}
        </div>
      )}

      <p className="pvw-hint">{t('pv.hint')}</p>
    </div>
  )
}
