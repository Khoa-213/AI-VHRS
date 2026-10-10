import { useCallback, useEffect, useRef } from 'react'

interface View {
  rx: number
  ry: number
  z: number
  px: number
  py: number
}

const clampZ = (z: number) => Math.max(0.6, Math.min(4, z))
const clampX = (x: number) => Math.max(-85, Math.min(85, x))

/**
 * Drag-to-rotate, pinch/wheel-to-zoom viewer for a flat object. Returns refs
 * for the stage (receives input), the object (gets the transform) and the
 * zoom label (updated directly, so no React re-render per frame).
 */
export function useViewer(enabled: boolean) {
  const stage = useRef<HTMLDivElement>(null)
  const obj = useRef<HTMLDivElement>(null)
  const zoom = useRef<HTMLSpanElement>(null)
  const cur = useRef<View>({ rx: 0, ry: 0, z: 1, px: 0, py: 0 })
  const tgt = useRef<View>({ rx: 0, ry: 0, z: 1, px: 0, py: 0 })
  const vel = useRef({ rx: 0, ry: 0 })

  useEffect(() => {
    const st = stage.current
    if (!st || !enabled) return
    const c = cur.current
    const t = tgt.current
    const v = vel.current
    const ptrs = new Map<number, { x: number; y: number }>()
    let pinch: { d: number; z: number; mx: number; my: number; px: number; py: number } | null = null

    const down = (e: PointerEvent) => {
      if ((e.target as Element).closest?.('button')) return
      st.setPointerCapture(e.pointerId)
      ptrs.set(e.pointerId, { x: e.clientX, y: e.clientY })
      v.rx = 0
      v.ry = 0
      st.style.cursor = 'grabbing'
      if (ptrs.size === 2) {
        const [a, b] = [...ptrs.values()]
        pinch = {
          d: Math.hypot(a.x - b.x, a.y - b.y), z: t.z,
          mx: (a.x + b.x) / 2, my: (a.y + b.y) / 2, px: t.px, py: t.py,
        }
      }
    }
    const move = (e: PointerEvent) => {
      const p = ptrs.get(e.pointerId)
      if (!p) return
      const dx = e.clientX - p.x
      const dy = e.clientY - p.y
      p.x = e.clientX
      p.y = e.clientY
      if (ptrs.size === 1) {
        const vy = dx * 0.45
        const vx = -dy * 0.3
        t.ry += vy
        t.rx = clampX(t.rx + vx)
        v.ry = vy * 0.6
        v.rx = vx * 0.6
      } else if (ptrs.size === 2 && pinch) {
        const [a, b] = [...ptrs.values()]
        t.z = clampZ((pinch.z * Math.hypot(a.x - b.x, a.y - b.y)) / pinch.d)
        t.px = pinch.px + (a.x + b.x) / 2 - pinch.mx
        t.py = pinch.py + (a.y + b.y) / 2 - pinch.my
      }
    }
    const up = (e: PointerEvent) => {
      ptrs.delete(e.pointerId)
      if (ptrs.size < 2) pinch = null
      if (!ptrs.size) st.style.cursor = 'grab'
    }
    const wheel = (e: WheelEvent) => {
      e.preventDefault()
      const mouseWheel = e.deltaMode === 1 || (Math.abs(e.deltaY) >= 80 && e.deltaX === 0 && Number.isInteger(e.deltaY))
      if (e.ctrlKey || mouseWheel) {
        t.z = clampZ(t.z * Math.exp(-e.deltaY * (e.ctrlKey ? 0.012 : 0.0016)))
      } else {
        t.ry -= e.deltaX * 0.35
        t.rx = clampX(t.rx + e.deltaY * 0.25)
        v.rx = 0
        v.ry = 0
      }
    }

    st.addEventListener('pointerdown', down)
    st.addEventListener('pointermove', move)
    st.addEventListener('pointerup', up)
    st.addEventListener('pointercancel', up)
    st.addEventListener('wheel', wheel, { passive: false })

    let raf = 0
    const loop = () => {
      if (!ptrs.size && (Math.abs(v.rx) > 0.01 || Math.abs(v.ry) > 0.01)) {
        t.ry += v.ry
        t.rx = clampX(t.rx + v.rx)
        v.ry *= 0.94
        v.rx *= 0.94
      }
      for (const k of ['rx', 'ry', 'z', 'px', 'py'] as const) c[k] += (t[k] - c[k]) * 0.2
      if (obj.current) {
        obj.current.style.transform =
          `translate3d(${c.px.toFixed(2)}px,${c.py.toFixed(2)}px,0) rotateX(${c.rx.toFixed(3)}deg) rotateY(${c.ry.toFixed(3)}deg) scale(${c.z.toFixed(4)})`
      }
      const label = Math.round(c.z * 100) + '%'
      if (zoom.current && zoom.current.textContent !== label) zoom.current.textContent = label
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)

    return () => {
      cancelAnimationFrame(raf)
      st.removeEventListener('pointerdown', down)
      st.removeEventListener('pointermove', move)
      st.removeEventListener('pointerup', up)
      st.removeEventListener('pointercancel', up)
      st.removeEventListener('wheel', wheel)
    }
  }, [enabled])

  const reset = useCallback(() => {
    Object.assign(tgt.current, { rx: 0, ry: 0, z: 1, px: 0, py: 0 })
    vel.current.rx = 0
    vel.current.ry = 0
  }, [])
  const zoomBy = useCallback((f: number) => {
    tgt.current.z = clampZ(tgt.current.z * f)
  }, [])

  return { stage, obj, zoom, reset, zoomBy }
}
