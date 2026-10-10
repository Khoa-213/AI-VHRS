import { useEffect, useRef, type PointerEvent } from 'react'

const PAPER = '#f4eee0'

interface DrawPadProps {
  /** Saved drawing, used to restore the canvas after a tab switch. */
  url: string | null
  onStroke: (dataUrl: string) => void
}

/** Pointer-driven canvas. Pen pressure sets the line width when the device reports it. */
export default function DrawPad({ url, onStroke }: DrawPadProps) {
  const ref = useRef<HTMLCanvasElement>(null)
  const drawing = useRef(false)
  const last = useRef<[number, number]>([0, 0])

  // Paint the sheet once on mount, then restore the previous drawing if there is one.
  // The parent remounts this component (via `key`) to clear it.
  useEffect(() => {
    const cv = ref.current
    if (!cv) return
    const ctx = cv.getContext('2d')!
    ctx.fillStyle = PAPER
    ctx.fillRect(0, 0, cv.width, cv.height)
    if (url) {
      const im = new Image()
      im.onload = () => ctx.drawImage(im, 0, 0)
      im.src = url
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const point = (e: PointerEvent<HTMLCanvasElement>): [number, number] => {
    const cv = ref.current!
    const r = cv.getBoundingClientRect()
    return [((e.clientX - r.left) * cv.width) / r.width, ((e.clientY - r.top) * cv.height) / r.height]
  }

  const down = (e: PointerEvent<HTMLCanvasElement>) => {
    try {
      e.currentTarget.setPointerCapture(e.pointerId)
    } catch {
      /* not all devices support capture */
    }
    drawing.current = true
    last.current = point(e)
  }

  const move = (e: PointerEvent<HTMLCanvasElement>) => {
    if (!drawing.current) return
    const ctx = ref.current!.getContext('2d')!
    const p = point(e)
    ctx.strokeStyle = '#1b2440'
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'
    ctx.lineWidth = e.pointerType === 'pen' && e.pressure ? 1 + e.pressure * 6 : 3.4
    ctx.beginPath()
    ctx.moveTo(last.current[0], last.current[1])
    ctx.lineTo(p[0], p[1])
    ctx.stroke()
    last.current = p
  }

  const up = () => {
    if (!drawing.current) return
    drawing.current = false
    onStroke(ref.current!.toDataURL('image/png'))
  }

  return (
    <div className="co-draw">
      <canvas
        ref={ref}
        width={900}
        height={340}
        onPointerDown={down}
        onPointerMove={move}
        onPointerUp={up}
        onPointerLeave={up}
      />
    </div>
  )
}
