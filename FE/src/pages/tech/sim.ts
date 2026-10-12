import { layoutById } from '../../constants/catalog'
import type { Order } from '../../types'
import { fontScale } from '../../utils/format'
import { recognizedText } from '../staff/evaluate'

/**
 * In-browser stand-in for the Isaac Sim viewport. Nothing here talks to a
 * simulator: the pen path is derived from the order text and a 2-link arm
 * follows it with inverse kinematics, so every order option has a visible effect.
 */

export interface Tuning {
  /** Pen speed on paper, mm/s. */
  speed: number
  /** Contact force, N. Wider and darker lines at higher force. */
  force: number
  /** How far the pen rises between words, mm. */
  lift: number
}

export const DEFAULT_TUNING: Tuning = { speed: 60, force: 1.2, lift: 8 }

export interface ViewFlags {
  trajectory: boolean
  reach: boolean
  joints: boolean
}

export const W = 1200
export const H = 720
/** Pixels per millimetre in the viewport. */
export const PX = 2.6
const ORIGIN = { x: 660, y: 380 }
const L1 = 200
const L2 = 200

export interface Plan {
  text: string
  paperW: number
  paperH: number
  lines: { text: string; y: number; x0: number; x1: number; startChar: number }[]
  fontPx: number
  lineH: number
  chars: number
}

export interface Viewport {
  paper: { x: number; y: number; w: number; h: number }
  base: { x: number; y: number }
}

export const planText = (order: Order) => recognizedText(order, undefined).trim() || 'Xin chào'

/** Paper footprint in mm. Aspect already includes orientation. */
export function paperMm(aspect: string) {
  const [a, b] = aspect.split('/').map(Number)
  const ratio = a && b ? a / b : 0.72
  const w = ratio >= 1 ? 220 : 148
  return { w, h: w / ratio }
}

export function viewportFor(aspect: string): Viewport {
  const { w, h } = paperMm(aspect)
  const pw = w * PX
  const ph = h * PX
  return {
    paper: { x: ORIGIN.x - pw / 2, y: ORIGIN.y - ph / 2, w: pw, h: ph },
    base: { x: ORIGIN.x - pw / 2 - 95 * PX, y: ORIGIN.y },
  }
}

/** Lays the text out inside the paper the way the order layout asks, in viewport pixels. */
export function buildPlan(ctx: CanvasRenderingContext2D, order: Order, vp: Viewport): Plan {
  const sp = order.spec
  const L = layoutById(order.layout)
  const text = planText(order)
  const { w, h } = vp.paper
  const padX = (L.id === 'letter' ? 0.1 : L.frame ? 0.14 : 0.1) * w
  const padY = (L.id === 'letter' ? 0.12 : L.frame ? 0.14 : 0.1) * w
  const inner = w - padX * 2
  let fontPx = (fontScale(text.length) / 100) * w * 0.82
  const font = (px: number) => `600 ${px}px ${sp.font || 'cursive'}`

  const wrap = (px: number) => {
    ctx.font = font(px)
    const out: string[] = []
    for (const para of text.split('\n')) {
      let cur = ''
      for (const word of para.split(/\s+/).filter(Boolean)) {
        const next = cur ? cur + ' ' + word : word
        if (cur && ctx.measureText(next).width > inner) {
          out.push(cur)
          cur = word
        } else cur = next
      }
      out.push(cur)
    }
    return out
  }

  let lines = wrap(fontPx)
  while (lines.length * fontPx * 1.25 > h - padY * 2 && fontPx > 10) {
    fontPx *= 0.92
    lines = wrap(fontPx)
  }
  ctx.font = font(fontPx)
  const lineH = fontPx * 1.25
  const total = lines.length * lineH
  const top = L.alignItems === 'flex-start' ? vp.paper.y + padY : vp.paper.y + (h - total) / 2
  let startChar = 0
  const out = lines.map((t, i) => {
    const lw = ctx.measureText(t).width
    const x0 = L.textAlign === 'left' ? vp.paper.x + padX : vp.paper.x + (w - lw) / 2
    const line = { text: t, y: top + i * lineH + lineH / 2, x0, x1: x0 + lw, startChar }
    startChar += t.length + 1
    return line
  })
  return { text, paperW: w, paperH: h, lines: out, fontPx, lineH, chars: Math.max(1, startChar - 1) }
}

export interface PenState {
  x: number
  y: number
  down: boolean
  line: number
  char: number
  /** Strokes completed so far (words, as pen lifts). */
  words: number
}

export function penAt(ctx: CanvasRenderingContext2D, plan: Plan, order: Order, p: number): PenState {
  const target = Math.min(plan.chars, Math.max(0, p * plan.chars))
  let li = plan.lines.findIndex((l, i) => target <= l.startChar + l.text.length + (i < plan.lines.length - 1 ? 0 : 1))
  if (li < 0) li = plan.lines.length - 1
  const line = plan.lines[li]
  const c = Math.min(line.text.length, Math.max(0, target - line.startChar))
  ctx.font = `600 ${plan.fontPx}px ${order.spec.font || 'cursive'}`
  const before = ctx.measureText(line.text.slice(0, Math.floor(c))).width
  const next = ctx.measureText(line.text.slice(0, Math.ceil(c))).width
  const x = line.x0 + before + (next - before) * (c - Math.floor(c))
  const ch = line.text[Math.min(line.text.length - 1, Math.floor(c))] ?? ' '
  const wob = Math.sin(x * 0.17) * plan.lineH * 0.16 + Math.sin(x * 0.05 + li) * plan.lineH * 0.08
  const before_ = plan.text.slice(0, Math.floor(target))
  return {
    x,
    y: line.y + wob,
    down: ch !== ' ' && p < 1 && p > 0,
    line: li,
    char: Math.floor(target),
    words: before_.split(/\s+/).filter(Boolean).length,
  }
}

export interface Arm {
  base: { x: number; y: number }
  elbow: { x: number; y: number }
  tip: { x: number; y: number }
  /** Angles in degrees: shoulder yaw, elbow, then wrist terms. */
  q: number[]
  reachable: boolean
}

/** Two-link planar IK with the elbow kept up, in viewport pixels. */
export function solveArm(vp: Viewport, tip: { x: number; y: number }, wobble: number): Arm {
  const l1 = L1 * PX
  const l2 = L2 * PX
  const dx = tip.x - vp.base.x
  const dy = tip.y - vp.base.y
  const raw = Math.hypot(dx, dy)
  const d = Math.min(l1 + l2 - 0.5, Math.max(Math.abs(l1 - l2) + 8, raw))
  const a = Math.atan2(dy, dx)
  const sh = a - Math.acos(Math.min(1, Math.max(-1, (d * d + l1 * l1 - l2 * l2) / (2 * d * l1))))
  const elbow = { x: vp.base.x + l1 * Math.cos(sh), y: vp.base.y + l1 * Math.sin(sh) }
  const el = Math.acos(Math.min(1, Math.max(-1, (l1 * l1 + l2 * l2 - d * d) / (2 * l1 * l2))))
  const deg = (r: number) => (r * 180) / Math.PI
  return {
    base: vp.base,
    elbow,
    tip: { x: vp.base.x + d * Math.cos(a), y: vp.base.y + d * Math.sin(a) },
    q: [
      deg(a),
      deg(sh) + 60,
      -deg(sh) * 0.4,
      deg(Math.PI - el) - 90,
      Math.sin(wobble) * 3,
      90 - deg(a) * 0.3,
      Math.cos(wobble * 0.7) * 2,
    ],
    reachable: raw <= l1 + l2,
  }
}

export const mmOf = (px: number) => px / PX

/** Real seconds one piece takes at the tuned speed (arc length of the text over pen speed, plus lifts). */
export function pieceSeconds(plan: Plan, t: Tuning): number {
  const inkPx = plan.lines.reduce((a, l) => a + (l.x1 - l.x0), 0) * 3.1
  const mm = inkPx / PX
  const lifts = plan.text.split(/\s+/).filter(Boolean).length
  return Math.max(10, mm / t.speed + lifts * (0.6 + t.lift / 40) + 4 * plan.lines.length)
}
