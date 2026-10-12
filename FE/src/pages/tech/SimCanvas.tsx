import { useEffect, useRef } from 'react'
import { layoutById } from '../../constants/catalog'
import type { Order } from '../../types'
import {
  H, PX, W,
  type Arm, type PenState, type Plan, type Tuning, type ViewFlags, type Viewport,
} from './sim'

interface Props {
  order: Order
  plan: Plan
  vp: Viewport
  pen: PenState
  arm: Arm
  tuning: Tuning
  flags: ViewFlags
  /** Bumps when a web font finishes loading so the ink layer is redrawn. */
  fontTick: number
  live: boolean
}

const ACCENT = '#e8a23a'

/** Draws the bench, paper, ink so far, the FR3 arm and the side view. Pure canvas, redrawn on every progress change. */
export default function SimCanvas({ order, plan, vp, pen, arm, tuning, flags, fontTick, live }: Props) {
  const ref = useRef<HTMLCanvasElement>(null)
  const ink = useRef<HTMLCanvasElement | null>(null)
  const z = useRef(0)

  // Ink layer: the whole text once, revealed later with clip rects.
  useEffect(() => {
    const c = (ink.current ??= document.createElement('canvas'))
    c.width = W
    c.height = H
    const g = c.getContext('2d')
    if (!g) return
    const sp = order.spec
    g.clearRect(0, 0, W, H)
    g.fillStyle = sp.inkColor
    g.strokeStyle = sp.inkColor
    g.lineJoin = 'round'
    g.font = `600 ${plan.fontPx}px ${sp.font || 'cursive'}`
    g.textBaseline = 'middle'
    g.lineWidth = Math.max(0.3, (sp.penW || 2) * 0.35 * (tuning.force / 1.2))
    for (const l of plan.lines) {
      g.fillText(l.text, l.x0, l.y)
      g.strokeText(l.text, l.x0, l.y)
    }
    if (layoutById(order.layout).frame) {
      const m = vp.paper.w * 0.05
      g.lineWidth = 1.4
      g.strokeRect(vp.paper.x + m, vp.paper.y + m, vp.paper.w - m * 2, vp.paper.h - m * 2)
      g.strokeRect(vp.paper.x + m + 5, vp.paper.y + m + 5, vp.paper.w - m * 2 - 10, vp.paper.h - m * 2 - 10)
    }
  }, [order, plan, vp, tuning.force, fontTick])

  useEffect(() => {
    const cv = ref.current
    const g = cv?.getContext('2d')
    if (!cv || !g) return
    g.clearRect(0, 0, W, H)

    // Floor and bench
    g.fillStyle = '#0b0d12'
    g.fillRect(0, 0, W, H)
    g.strokeStyle = 'rgba(255,255,255,.035)'
    g.lineWidth = 1
    for (let x = 0; x <= W; x += 40) { g.beginPath(); g.moveTo(x, 0); g.lineTo(x, H); g.stroke() }
    for (let y = 0; y <= H; y += 40) { g.beginPath(); g.moveTo(0, y); g.lineTo(W, y); g.stroke() }
    g.fillStyle = '#151922'
    g.beginPath()
    g.roundRect(30, 50, W - 60, H - 100, 18)
    g.fill()
    g.strokeStyle = 'rgba(255,255,255,.07)'
    g.stroke()

    // Reach envelope
    if (flags.reach) {
      g.save()
      g.setLineDash([6, 8])
      g.strokeStyle = 'rgba(232,162,58,.45)'
      g.beginPath()
      g.arc(vp.base.x, vp.base.y, 400 * PX, -1.2, 1.2)
      g.stroke()
      g.restore()
    }

    // Paper
    const p = vp.paper
    g.save()
    g.shadowColor = 'rgba(0,0,0,.55)'
    g.shadowBlur = 24
    g.shadowOffsetY = 10
    g.fillStyle = order.spec.paperColor
    g.fillRect(p.x, p.y, p.w, p.h)
    g.restore()
    g.fillStyle = order.spec.paperColor
    g.fillRect(p.x, p.y, p.w, p.h)

    // Planned path, dotted, for the lines not written yet
    if (flags.trajectory) {
      g.save()
      g.setLineDash([2, 6])
      g.strokeStyle = 'rgba(57,135,229,.7)'
      g.lineWidth = 1.5
      plan.lines.forEach((l, i) => {
        if (i < pen.line) return
        const from = i === pen.line ? pen.x : l.x0
        g.beginPath()
        g.moveTo(from, l.y)
        g.lineTo(l.x1, l.y)
        g.stroke()
      })
      g.restore()
    }

    // Ink written so far
    const layer = ink.current
    if (layer && pen.char > 0) {
      const frameOn = layoutById(order.layout).frame
      if (frameOn) {
        const m = p.w * 0.05
        g.save()
        g.beginPath()
        g.rect(p.x + m - 3, p.y + m - 3, p.w - m * 2 + 6, p.h - m * 2 + 6)
        g.rect(p.x + m + 8, p.y + m + 8, p.w - m * 2 - 16, p.h - m * 2 - 16)
        g.clip('evenodd')
        g.drawImage(layer, 0, 0)
        g.restore()
      }
      plan.lines.forEach((l, i) => {
        if (i > pen.line) return
        const right = i < pen.line ? l.x1 + 6 : pen.x
        g.save()
        g.beginPath()
        g.rect(l.x0 - 6, l.y - plan.lineH / 2, Math.max(0, right - l.x0 + 6), plan.lineH)
        g.clip()
        g.drawImage(layer, 0, 0)
        g.restore()
      })
    }

    // Arm
    const a = arm
    const link = (from: { x: number; y: number }, to: { x: number; y: number }, w: number) => {
      g.lineCap = 'round'
      g.strokeStyle = 'rgba(0,0,0,.35)'
      g.lineWidth = w + 6
      g.beginPath(); g.moveTo(from.x + 6, from.y + 10); g.lineTo(to.x + 6, to.y + 10); g.stroke()
      g.strokeStyle = '#d7dae1'
      g.lineWidth = w
      g.beginPath(); g.moveTo(from.x, from.y); g.lineTo(to.x, to.y); g.stroke()
      g.strokeStyle = '#f4f5f8'
      g.lineWidth = w * 0.35
      g.beginPath(); g.moveTo(from.x, from.y - w * 0.15); g.lineTo(to.x, to.y - w * 0.15); g.stroke()
    }
    g.fillStyle = '#20232c'
    g.beginPath(); g.roundRect(a.base.x - 34, a.base.y - 34, 68, 68, 10); g.fill()
    link(a.base, a.elbow, 30)
    link(a.elbow, a.tip, 20)
    const joint = (pt: { x: number; y: number }, r: number) => {
      g.fillStyle = '#1b1e26'
      g.beginPath(); g.arc(pt.x, pt.y, r, 0, 7); g.fill()
      g.strokeStyle = live ? '#34d399' : ACCENT
      g.lineWidth = 2.5
      g.beginPath(); g.arc(pt.x, pt.y, r - 4, 0, 7); g.stroke()
    }
    joint(a.base, 22)
    joint(a.elbow, 17)
    joint(a.tip, 11)
    // Pen holder and pen
    g.strokeStyle = '#2b2f3a'
    g.lineWidth = 6
    g.beginPath(); g.moveTo(a.tip.x, a.tip.y); g.lineTo(a.tip.x + 22, a.tip.y - 14); g.stroke()
    g.fillStyle = pen.down ? order.spec.inkColor : '#9aa0ad'
    g.strokeStyle = '#fff'
    g.lineWidth = 1.5
    g.beginPath(); g.arc(a.tip.x, a.tip.y, pen.down ? 4 : 3, 0, 7); g.fill(); g.stroke()
    if (flags.joints) {
      g.font = '600 12px "JetBrains Mono", monospace'
      g.fillStyle = '#c9ced8'
      g.fillText(`J1 ${a.q[0].toFixed(0)}°`, a.base.x - 30, a.base.y + 52)
      g.fillText(`J4 ${a.q[3].toFixed(0)}°`, a.elbow.x + 14, a.elbow.y - 12)
      g.fillText(`${((a.tip.x - p.x) / PX).toFixed(0)}, ${((a.tip.y - p.y) / PX).toFixed(0)} mm`, a.tip.x + 18, a.tip.y + 26)
    }

    // Side view inset: pen height over the paper
    const bx = W - 270
    const by = H - 150
    g.fillStyle = 'rgba(10,12,17,.82)'
    g.beginPath(); g.roundRect(bx, by, 230, 90, 8); g.fill()
    g.fillStyle = '#8b92a1'
    g.font = '700 11px "JetBrains Mono", monospace'
    g.fillText('SIDE VIEW · Z', bx + 12, by + 20)
    const target = pen.down ? 0 : tuning.lift
    z.current += (target - z.current) * 0.4
    g.fillStyle = order.spec.paperColor
    g.fillRect(bx + 12, by + 70, 206, 4)
    const penTop = by + 70 - 12 - z.current * 2.6
    g.strokeStyle = '#d7dae1'
    g.lineWidth = 7
    g.lineCap = 'round'
    g.beginPath(); g.moveTo(bx + 115, penTop - 26); g.lineTo(bx + 115, penTop); g.stroke()
    g.fillStyle = order.spec.inkColor === '#000' ? '#fff' : order.spec.inkColor
    g.beginPath(); g.arc(bx + 115, penTop + 3, 3, 0, 7); g.fill()
    g.fillStyle = '#c9ced8'
    g.fillText(`Z +${z.current.toFixed(1)} mm`, bx + 150, by + 20)
  }, [order, plan, vp, pen, arm, tuning.lift, flags, live, fontTick])

  return (
    <canvas
      ref={ref}
      width={W}
      height={H}
      className="tp-canvas"
      role="img"
      aria-label={`Simulated FR3 writing ${order.id}, ${Math.round((pen.char / plan.chars) * 100)} percent`}
    />
  )
}

