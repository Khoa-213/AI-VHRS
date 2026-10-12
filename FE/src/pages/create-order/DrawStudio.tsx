import { useCallback, useEffect, useLayoutEffect, useRef, useState, type PointerEvent } from 'react'
import { navigate } from '../../router/router'
import { CANVAS_SIZES, loadDraft, saveDraft } from './draft'
import './draw-studio.css'

/** The whole page is a dark dotted surface you can write on; the frame marks the sheet that is actually produced. Strokes are light and the bitmap stays transparent, so the dots are pure CSS. */
const INK = '#f2f3f5'
const DOT_MM = 10
const PX_PER_MM = 4 // resolution of the exported sheet
const MAX_PPM = 6 // never zoom the frame beyond this many css px per mm
const MAX_UNDO = 25
const MARGIN = 48

type PenId = 'pen' | 'monoline' | 'pencil' | 'fountain'

const PENS: { id: PenId; name: string }[] = [
  { id: 'pen', name: 'Pen' },
  { id: 'monoline', name: 'Monoline' },
  { id: 'pencil', name: 'Pencil' },
  { id: 'fountain', name: 'Fountain Pen' },
]

/** Five nib sizes, in millimetres on the sheet. */
const NIB_MM = [0.5, 0.8, 1.2, 2, 3]

type Pt = [number, number]

/** Fountain nib: a thin ellipse held at a fixed angle, so strokes across it come out thick and along it hairline. */
const NIB_ANGLE = -Math.PI / 4

export default function DrawStudio() {
  const [initial] = useState(loadDraft)
  const [sizeId, setSizeId] = useState(initial.sizeId)
  const [landscape, setLandscape] = useState(initial.landscape)
  const [strokes, setStrokes] = useState(initial.strokes)
  const [pen, setPen] = useState<PenId>('pen')
  const [nib, setNib] = useState(1)
  const [menu, setMenu] = useState(false)
  const [canUndo, setCanUndo] = useState(false)
  const [stage, setStage] = useState({ w: 0, h: 0 })

  const size = CANVAS_SIZES.find((s) => s.id === sizeId) ?? CANVAS_SIZES[0]
  const mmW = landscape ? size.h : size.w
  const mmH = landscape ? size.w : size.h
  const pxW = mmW * PX_PER_MM
  const pxH = mmH * PX_PER_MM
  const dpr = typeof window === 'undefined' ? 1 : window.devicePixelRatio || 1

  // css px per millimetre: the frame is the biggest sheet that fits, and it is the measure for everything drawn.
  const ppm = stage.w
    ? Math.max(0.2, Math.min((stage.w - MARGIN) / mmW, (stage.h - MARGIN) / mmH, MAX_PPM))
    : 1
  const frameW = mmW * ppm
  const frameH = mmH * ppm
  const penW = NIB_MM[nib] * ppm * dpr
  const dotGap = DOT_MM * ppm

  const cvRef = useRef<HTMLCanvasElement>(null)
  const stageRef = useRef<HTMLDivElement>(null)
  const dockRef = useRef<HTMLDivElement>(null)
  const drawing = useRef(false)
  const last = useRef<Pt>([0, 0])
  const lastT = useRef(0)
  const liveW = useRef(1)
  const history = useRef<ImageData[]>([])
  const prev = useRef<{ w: number; h: number; ppm: number } | null>(null)

  useLayoutEffect(() => {
    const el = stageRef.current
    if (!el) return
    const measure = () => setStage({ w: el.clientWidth, h: el.clientHeight })
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // (Re)size the bitmap to the stage. Whatever was drawn keeps its physical size relative to the frame:
  // it is rescaled by the change in px/mm around the stage centre, which is also the frame centre.
  useLayoutEffect(() => {
    const cv = cvRef.current
    if (!cv || !stage.w) return
    const W = Math.round(stage.w * dpr)
    const H = Math.round(stage.h * dpr)
    const before = prev.current
    let snap: HTMLCanvasElement | null = null
    if (before && cv.width) {
      snap = document.createElement('canvas')
      snap.width = cv.width
      snap.height = cv.height
      snap.getContext('2d')!.drawImage(cv, 0, 0)
    }
    cv.width = W
    cv.height = H
    const ctx = cv.getContext('2d')!
    history.current = []
    setCanUndo(false)
    if (snap && before) {
      const r = ppm / before.ppm
      ctx.save()
      ctx.translate(W / 2, H / 2)
      ctx.scale(r, r)
      ctx.translate(-before.w / 2, -before.h / 2)
      ctx.drawImage(snap, 0, 0)
      ctx.restore()
    } else if (!before && initial.drawUrl) {
      const im = new Image()
      im.onload = () => {
        const fw = mmW * ppm * dpr
        const fh = mmH * ppm * dpr
        ctx.drawImage(im, (W - fw) / 2, (H - fh) / 2, fw, fh)
      }
      im.src = initial.drawUrl
    }
    prev.current = { w: W, h: H, ppm }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stage.w, stage.h, ppm])

  const point = (e: PointerEvent<HTMLCanvasElement>): Pt => {
    const cv = cvRef.current!
    const r = cv.getBoundingClientRect()
    return [((e.clientX - r.left) * cv.width) / r.width, ((e.clientY - r.top) * cv.height) / r.height]
  }

  /** Stamp the calligraphic nib along a→p so thick/thin follows the direction of travel. */
  const stampNib = (ctx: CanvasRenderingContext2D, a: Pt, p: Pt, scale: number) => {
    const major = penW * 1.7 * scale
    const minor = Math.max(0.5, penW * 0.2 * scale)
    const dist = Math.hypot(p[0] - a[0], p[1] - a[1])
    const steps = Math.max(1, Math.ceil(dist / 0.75))
    ctx.fillStyle = INK
    for (let i = 1; i <= steps; i++) {
      const t = i / steps
      ctx.beginPath()
      ctx.ellipse(a[0] + (p[0] - a[0]) * t, a[1] + (p[1] - a[1]) * t, major, minor, NIB_ANGLE, 0, Math.PI * 2)
      ctx.fill()
    }
  }

  const segment = (ctx: CanvasRenderingContext2D, a: Pt, p: Pt, e: PointerEvent<HTMLCanvasElement>) => {
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'
    ctx.strokeStyle = INK
    if (pen === 'fountain') {
      const now = performance.now()
      const speed = Math.hypot(p[0] - a[0], p[1] - a[1]) / dpr / Math.max(1, now - lastT.current)
      lastT.current = now
      // Pressure when the device reports it, otherwise ink thins as the hand speeds up.
      const target = e.pointerType === 'pen' && e.pressure
        ? 0.55 + e.pressure * 0.9
        : Math.min(1.2, Math.max(0.65, 1.25 - speed * 0.35))
      liveW.current += (target - liveW.current) * 0.2
      stampNib(ctx, a, p, liveW.current)
      return
    }
    let w = penW
    if (pen === 'pen') {
      w = e.pointerType === 'pen' && e.pressure ? penW * (0.4 + e.pressure * 1.2) : penW
    } else if (pen === 'pencil') {
      ctx.globalAlpha = 0.75
      ctx.lineWidth = Math.max(1, penW * 0.55)
      for (let n = 0; n < 2; n++) {
        const j = () => (Math.random() - 0.5) * 0.9 * dpr
        ctx.beginPath()
        ctx.moveTo(a[0] + j(), a[1] + j())
        ctx.lineTo(p[0] + j(), p[1] + j())
        ctx.stroke()
      }
      ctx.globalAlpha = 1
      return
    }
    ctx.lineWidth = w
    ctx.beginPath()
    ctx.moveTo(a[0], a[1])
    ctx.lineTo(p[0], p[1])
    ctx.stroke()
  }

  const down = (e: PointerEvent<HTMLCanvasElement>) => {
    setMenu(false)
    const cv = cvRef.current!
    const ctx = cv.getContext('2d')!
    try {
      e.currentTarget.setPointerCapture(e.pointerId)
    } catch {
      /* not every device supports capture */
    }
    history.current.push(ctx.getImageData(0, 0, cv.width, cv.height))
    if (history.current.length > MAX_UNDO) history.current.shift()
    const p = point(e)
    drawing.current = true
    last.current = p
    lastT.current = performance.now()
    liveW.current = 1
    if (pen === 'fountain') {
      stampNib(ctx, p, p, 1)
    } else {
      ctx.fillStyle = INK
      ctx.beginPath()
      ctx.arc(p[0], p[1], (pen === 'pencil' ? penW * 0.55 : penW) / 2, 0, Math.PI * 2)
      ctx.fill()
    }
  }

  const move = (e: PointerEvent<HTMLCanvasElement>) => {
    if (!drawing.current) return
    const ctx = cvRef.current!.getContext('2d')!
    const raw = point(e)
    // Light smoothing so the fountain nib does not pick up pointer jitter.
    const k = pen === 'fountain' ? 0.45 : 1
    const p: Pt = [last.current[0] + (raw[0] - last.current[0]) * k, last.current[1] + (raw[1] - last.current[1]) * k]
    segment(ctx, last.current, p, e)
    last.current = p
  }

  const up = () => {
    if (!drawing.current) return
    drawing.current = false
    setStrokes((n) => n + 1)
    setCanUndo(true)
  }

  const undo = useCallback(() => {
    const snap = history.current.pop()
    if (!snap) return
    cvRef.current!.getContext('2d')!.putImageData(snap, 0, 0)
    setStrokes((n) => Math.max(0, n - 1))
    setCanUndo(history.current.length > 0)
  }, [])

  const clear = () => {
    const cv = cvRef.current!
    const ctx = cv.getContext('2d')!
    history.current.push(ctx.getImageData(0, 0, cv.width, cv.height))
    ctx.clearRect(0, 0, cv.width, cv.height)
    setStrokes(0)
    setCanUndo(true)
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'z') {
        e.preventDefault()
        undo()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [undo])

  useEffect(() => {
    if (!menu) return
    const onDown = (e: globalThis.PointerEvent) => {
      if (!dockRef.current?.contains(e.target as Node)) setMenu(false)
    }
    const onEsc = (e: KeyboardEvent) => e.key === 'Escape' && setMenu(false)
    document.addEventListener('pointerdown', onDown)
    window.addEventListener('keydown', onEsc)
    return () => {
      document.removeEventListener('pointerdown', onDown)
      window.removeEventListener('keydown', onEsc)
    }
  }, [menu])

  const finish = () => {
    const cv = cvRef.current!
    let drawUrl: string | null = null
    if (strokes > 0) {
      // Only what sits inside the frame is produced: crop it out of the page.
      const out = document.createElement('canvas')
      out.width = pxW
      out.height = pxH
      const fw = frameW * dpr
      const fh = frameH * dpr
      out.getContext('2d')!.drawImage(cv, (cv.width - fw) / 2, (cv.height - fh) / 2, fw, fh, 0, 0, pxW, pxH)
      // Transparent PNG with light strokes: the order recolours it with the chosen ink on the chosen paper.
      drawUrl = out.toDataURL('image/png')
    }
    saveDraft({ mode: 'draw', step: 1, strokes, sizeId, landscape, drawUrl })
    navigate('/create-order')
  }

  return (
    <div className="ds" data-screen-label="Canvas">
      <header className="ds-bar">
        <button className="vh-btn vh-btn--ghost vh-btn--sm" onClick={finish}>Back to order</button>
        <div className="ds-title">
          <span className="ds-title-main">Write it yourself</span>
          <span className="ds-title-sub vh-mono">{mmW} × {mmH} mm · {strokes} {strokes === 1 ? 'stroke' : 'strokes'}</span>
        </div>
        <button className="vh-btn vh-btn--primary vh-btn--sm" onClick={finish} disabled={strokes === 0}>
          Use this drawing
        </button>
      </header>

      <div className="ds-tools" role="toolbar" aria-label="Canvas tools">
        <div className="ds-group" role="radiogroup" aria-label="Paper size">
          {CANVAS_SIZES.map((s) => (
            <button
              key={s.id}
              role="radio"
              aria-checked={s.id === sizeId}
              className={`ds-chip${s.id === sizeId ? ' on' : ''}`}
              onClick={() => setSizeId(s.id)}
            >
              <span className="ds-chip-name">{s.label}</span>
              <span className="ds-chip-dim vh-mono">{s.w}×{s.h}</span>
            </button>
          ))}
        </div>

        <div className="ds-group" role="radiogroup" aria-label="Orientation">
          <button role="radio" aria-checked={!landscape} className={`ds-chip${!landscape ? ' on' : ''}`} onClick={() => setLandscape(false)}>
            <span className="ds-chip-name">Portrait</span>
          </button>
          <button role="radio" aria-checked={landscape} className={`ds-chip${landscape ? ' on' : ''}`} onClick={() => setLandscape(true)}>
            <span className="ds-chip-name">Landscape</span>
          </button>
        </div>

        <div className="ds-group ds-group--end">
          <button className="ds-act" onClick={undo} disabled={!canUndo}>Undo</button>
          <button className="ds-act" onClick={clear} disabled={strokes === 0}>Clear</button>
        </div>
      </div>

      <div
        className="ds-stage"
        ref={stageRef}
        style={{ backgroundSize: `${dotGap}px ${dotGap}px`, backgroundPosition: 'center' }}
      >
        <canvas
          ref={cvRef}
          className="ds-canvas"
          aria-label={`Drawing surface. The frame is ${mmW} by ${mmH} millimetres.`}
          onPointerDown={down}
          onPointerMove={move}
          onPointerUp={up}
          onPointerCancel={up}
        />

        <div
          className="ds-frame"
          aria-hidden
          style={{ width: frameW, height: frameH, ['--tick' as string]: `${dotGap}px` }}
        >
          <span className="ds-ruler ds-ruler--x" />
          <span className="ds-ruler ds-ruler--y" />
          <span className="ds-dim ds-dim--x vh-mono">{mmW} mm</span>
          <span className="ds-dim ds-dim--y vh-mono">{mmH} mm</span>
        </div>

        <div className="ds-dock" ref={dockRef}>
          {menu && (
            <div className="ds-pop" role="dialog" aria-label="Pen">
              <div className="ds-nibs" role="radiogroup" aria-label="Nib size">
                {NIB_MM.map((mm, i) => (
                  <button
                    key={mm}
                    role="radio"
                    aria-checked={i === nib}
                    aria-label={`${mm} mm`}
                    className={`ds-nib${i === nib ? ' on' : ''}`}
                    onClick={() => setNib(i)}
                  >
                    <span style={{ height: 1 + i * 1.6 }} />
                  </button>
                ))}
              </div>
              <ul className="ds-pens">
                {PENS.map((p) => (
                  <li key={p.id}>
                    <button className={`ds-pen-row${p.id === pen ? ' on' : ''}`} onClick={() => { setPen(p.id); setMenu(false) }}>
                      <span className="ds-pen-check" aria-hidden>{p.id === pen ? '✓' : ''}</span>
                      <span className={`ds-pen-swatch ds-pen-swatch--${p.id}`} aria-hidden />
                      <span>{p.name}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <button className="ds-dock-btn" aria-haspopup="dialog" aria-expanded={menu} onClick={() => setMenu((m) => !m)}>
            <span className={`ds-pen-swatch ds-pen-swatch--${pen}`} aria-hidden />
            <span className="ds-dock-name">{PENS.find((p) => p.id === pen)!.name}</span>
            <span className="ds-dock-size vh-mono">{NIB_MM[nib]} mm</span>
          </button>
        </div>
      </div>
    </div>
  )
}
