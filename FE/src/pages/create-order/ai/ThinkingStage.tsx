import { useEffect, useRef, useState } from 'react'

/**
 * The assistant's turn while it is being answered, as a row of the conversation (after the "thinking orb" pattern): a ball
 * leaves the send button, flies to the place of the coming answer and opens into a turning sphere of dots, lit in turn by
 * four light programs, with the current step beside it. When the answer is in, the sphere turns green from the top,
 * collapses into a green ball with a ring, and the ball settles where the answer's avatar is; the answer then unfolds
 * from there. One requestAnimationFrame loop writes every style, colours come from the theme, and with reduced motion it
 * is a still sphere with a short colour change.
 */

const TAU = Math.PI * 2
const RINGS = 13
const ORB_D = 84
const ORB_R = ORB_D / 2
/** The canvas is the row's first box; the sphere sits in its middle. */
const CANVAS = 120
const C0 = CANVAS / 2
const BALL = 34
const GREEN = 48
/** Where the answer's avatar will be, from the row's corner (the row is pulled 18px left, the avatar is 30px). */
const AVATAR_X = 33
const AVATAR_Y = 15
const AVATAR = 30
/** Milliseconds: the flight, then the sphere builds; the answer is not shown before the sphere stood for a moment. */
const FLY = 700
const MIN_THINK = FLY + 700
const RESOLVE = 700
const CONDENSE = 640
const OUT = 320
const PROGRAM_MS = 1150

function mulberry32(a: number) {
  return () => {
    a |= 0
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** Dots on rings of a unit sphere: position, height from the top (0 to 1) and a phase for the twinkle. */
const DOTS = (() => {
  const rand = mulberry32(7)
  const out: { x: number; y: number; z: number; u: number; seed: number }[] = []
  for (let k = 0; k < RINGS; k++) {
    const y = 1 - ((k + 0.5) / RINGS) * 2
    const r = Math.sqrt(1 - y * y)
    const m = Math.max(4, Math.round(24 * r))
    for (let j = 0; j < m; j++) {
      const a = (j / m) * TAU + k * 0.35
      out.push({ x: Math.cos(a) * r, y, z: Math.sin(a) * r, u: (1 - y) / 2, seed: rand() * TAU })
    }
  }
  return out
})()
const N = DOTS.length

const clamp01 = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v)
const lerp = (a: number, b: number, t: number) => a + (b - a) * t
const easeOut = (t: number) => 1 - Math.pow(1 - clamp01(t), 3)
const easeIn = (t: number) => Math.pow(clamp01(t), 2)
const easeIo = (t: number) => {
  const x = clamp01(t)
  return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2
}
const spring = (t: number) => {
  const x = clamp01(t) - 1
  return 1 + 2.4 * x * x * x + 1.4 * x * x
}
/** Progress of `t` between `a` and `b`, 0 before and 1 after. */
const span = (t: number, a: number, b: number) => clamp01((t - a) / (b - a))
const bez = (t: number, p0: number, c: number, p2: number) => (1 - t) * (1 - t) * p0 + 2 * (1 - t) * t * c + t * t * p2

function rgb(css: string): [number, number, number] {
  const m = css.match(/[\d.]+/g)
  return m && m.length >= 3 ? [Number(m[0]), Number(m[1]), Number(m[2])] : [128, 128, 128]
}

interface Orb { k: number; alpha: number; spin: number; pop: number; sweep: number; vortex: number; gain: number; floor: number; rad: number }

export type StageFinish = 'ok' | 'fail' | null

export default function ThinkingStage({ label, labels, doneLabel, finish, onFinished }: {
  /** The step the backend reports; without one the general labels take turns. */
  label: string | null
  labels: string[]
  doneLabel: string
  /** Set when the turn ended: `ok` plays the green ending, `fail` only fades. */
  finish: StageFinish
  onFinished: () => void
}) {
  const stage = useRef<HTMLDivElement>(null)
  const ball = useRef<HTMLSpanElement>(null)
  const green = useRef<HTMLSpanElement>(null)
  const ring = useRef<HTMLSpanElement>(null)
  const canvas = useRef<HTMLCanvasElement>(null)
  const status = useRef<HTMLDivElement>(null)
  const finishRef = useRef<StageFinish>(finish)
  const finished = useRef(onFinished)
  const [turn, setTurn] = useState(0)
  const [resolved, setResolved] = useState(false)

  useEffect(() => {
    finishRef.current = finish
    finished.current = onFinished
  })

  useEffect(() => {
    const id = window.setInterval(() => setTurn((n) => n + 1), PROGRAM_MS)
    return () => window.clearInterval(id)
  }, [])

  useEffect(() => {
    const root = stage.current
    const cv = canvas.current
    const ctx = cv?.getContext('2d')
    const b = ball.current
    const g = green.current
    const rg = ring.current
    const st = status.current
    if (!root || !cv || !ctx || !b || !g || !rg || !st) return

    const dpr = Math.min(2, window.devicePixelRatio || 1)
    cv.width = Math.round(CANVAS * dpr)
    cv.height = Math.round(CANVAS * dpr)
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    // The ball leaves from the send button (below the conversation, so it rises into view) and lands on the sphere's place.
    const box = root.getBoundingClientRect()
    const from = root.closest('.oa')?.querySelector('.oa-send')?.getBoundingClientRect()
    const startX = from ? from.left + from.width / 2 - box.left : box.width - 40
    const startY = from ? from.top + from.height / 2 - box.top : box.height + 80
    const ctrlX = lerp(startX, C0, 0.2)
    const ctrlY = lerp(startY, C0, 0.9)

    // The dots take the text colour and turn to the theme's green (read from the canvas' outline colour).
    const style = getComputedStyle(cv)
    let base = rgb(style.color)
    let good = rgb(style.outlineColor)
    const colors = new Map<number, string>()
    const tint = (k: number) => {
      const q = Math.round(k * 24)
      let c = colors.get(q)
      if (!c) {
        const m = q / 24
        c = `rgb(${Math.round(lerp(base[0], good[0], m))},${Math.round(lerp(base[1], good[1], m))},${Math.round(lerp(base[2], good[2], m))})`
        colors.set(q, c)
      }
      return c
    }

    const lit = new Float32Array(N)
    const sx = new Float32Array(N)
    const sy = new Float32Array(N)
    const sr = new Float32Array(N)
    const sa = new Float32Array(N)
    const sd = new Float32Array(N)
    const sg = new Float32Array(N)
    const weight = [1, 0, 0, 0]
    const tilt = 0.35
    const cp = Math.cos(tilt)
    const sp = Math.sin(tilt)
    let time = reduced ? 1.2 : 0
    let rot = 0
    let frames = 0

    /** One frame of the sphere. `k` builds it (top first), `sweep` turns it green, `vortex` twists it as it collapses. */
    const drawOrb = (dt: number, o: Orb) => {
      if (++frames % 40 === 0) {
        const s = getComputedStyle(cv)
        const nb = rgb(s.color)
        if (nb[0] !== base[0] || nb[1] !== base[1] || nb[2] !== base[2]) {
          base = nb
          good = rgb(s.outlineColor)
          colors.clear()
        }
      }
      ctx.clearRect(0, 0, CANVAS, CANVAS)
      if (o.alpha <= 0.002) return
      time += dt
      rot += o.spin * dt
      const yaw = rot + o.vortex
      const cyw = Math.cos(yaw)
      const syw = Math.sin(yaw)
      const program = Math.floor((time * 1000) / PROGRAM_MS) % 4
      const step = dt / 0.35
      for (let q = 0; q < 4; q++) {
        const d = (q === program ? 1 : 0) - weight[q]
        weight[q] += Math.abs(d) <= step ? d : d > 0 ? step : -step
      }
      const decay = Math.exp(-dt / 0.5)
      const h0 = (time * 300) % N
      const h3 = (time * 480) % N
      const a1 = time * 0.8
      const b1 = Math.sin(time * 0.5) * 0.9
      const f1x = Math.cos(b1) * Math.cos(a1)
      const f1y = Math.sin(b1)
      const f1z = Math.cos(b1) * Math.sin(a1)
      const a2 = time * 0.55 + 2.1
      const b2 = Math.cos(time * 0.42) * 0.9
      const f2x = Math.cos(b2) * Math.cos(a2)
      const f2y = Math.sin(b2)
      const f2z = Math.cos(b2) * Math.sin(a2)
      const band = Math.sin(time * 2.2)
      const swirl = o.vortex * 1.5

      for (let n = 0; n < N; n++) {
        const p = DOTS[n]
        let pulse = 0
        if (weight[0] > 0.001) {
          let dd = Math.abs(n - h0)
          if (dd > N - dd) dd = N - dd
          const v = Math.max(0, 1 - dd / 16)
          pulse = Math.max(pulse, v * v * weight[0])
        }
        if (weight[1] > 0.001) {
          const v1 = Math.max(0, (p.x * f1x + p.y * f1y + p.z * f1z - 0.72) / 0.28)
          const v2 = Math.max(0, (p.x * f2x + p.y * f2y + p.z * f2z - 0.72) / 0.28)
          const v = Math.max(v1, v2)
          pulse = Math.max(pulse, v * v * weight[1])
        }
        if (weight[2] > 0.001) {
          const e = p.y - band
          const v = Math.max(0, 1 - (e * e) / 0.02)
          pulse = Math.max(pulse, v * v * weight[2])
        }
        if (weight[3] > 0.001) {
          let dd = Math.abs(n - h3)
          if (dd > N - dd) dd = N - dd
          const v = Math.max(0, 1 - dd / 22)
          pulse = Math.max(pulse, v * v * weight[3])
        }
        const l = Math.max(lit[n] * decay, pulse * o.gain)
        lit[n] = l

        const ki = clamp01(o.k * 1.6 - 0.6 * p.u)
        if (ki <= 0.001) {
          sa[n] = 0
          continue
        }
        const eo = easeOut(ki)
        const kk = eo * o.pop
        const x1 = p.x * cyw + p.z * syw
        const z1 = -p.x * syw + p.z * cyw
        const y2 = p.y * cp - z1 * sp
        const z2 = p.y * sp + z1 * cp
        const f = 2.8 / (2.8 - z2)
        const depth = (z2 + 1) / 2
        let ox = x1 * ORB_R * kk * f
        let oy = -y2 * ORB_R * kk * f
        if (swirl > 0.001) {
          const sw = (1 - ki) * swirl
          const cc = Math.cos(sw)
          const ss = Math.sin(sw)
          const tx = ox * cc - oy * ss
          oy = ox * ss + oy * cc
          ox = tx
        }
        const gr = clamp01((o.sweep * 1.4 - p.u) / 0.4)
        let a = 0.14 + 0.04 * Math.sin(p.seed + time * 1.6) * (1 - gr) + 0.34 * depth * depth + 0.75 * l * (1 - gr) + gr * (0.55 + 0.4 * depth) + 2 * gr * (1 - gr)
        a = Math.max(a, o.floor * (0.7 + 0.3 * depth))
        sx[n] = C0 + ox
        sy[n] = C0 + oy
        sd[n] = depth
        sg[n] = gr
        sr[n] = (0.95 * (0.45 + 0.75 * depth) * f + 0.8 * l + gr * 0.22) * (1 + o.rad) * (0.4 + 0.6 * eo)
        sa[n] = Math.min(1, a) * eo * o.alpha
      }

      // Back half first, then the front half over it.
      for (let pass = 0; pass < 2; pass++) {
        for (let n = 0; n < N; n++) {
          if (sa[n] <= 0.01 || (sd[n] >= 0.5) !== (pass === 1)) continue
          ctx.globalAlpha = sa[n]
          ctx.fillStyle = tint(sg[n])
          ctx.beginPath()
          ctx.arc(sx[n], sy[n], sr[n], 0, TAU)
          ctx.fill()
        }
      }
      ctx.globalAlpha = 1
    }

    let raf = 0
    let timer = 0
    let over = false
    const end = () => {
      if (over) return
      over = true
      finished.current()
    }

    if (reduced) {
      // A still sphere; the ending is a short colour change, with nothing moving.
      b.style.opacity = '0'
      st.style.opacity = '1'
      const still: Orb = { k: 1, alpha: 1, spin: 0, pop: 1, sweep: 0, vortex: 0, gain: 1, floor: 0, rad: 0 }
      drawOrb(0, still)
      const poll = window.setInterval(() => {
        const f = finishRef.current
        if (!f) return
        window.clearInterval(poll)
        if (f === 'fail') return end()
        setResolved(true)
        drawOrb(0, { ...still, sweep: 1, floor: 0.95 })
        timer = window.setTimeout(end, 450)
      }, 80)
      return () => {
        window.clearInterval(poll)
        window.clearTimeout(timer)
      }
    }

    const t0 = performance.now()
    let last = t0
    /** When the ending started, on the stage clock. */
    let endAt = -1
    let failed = false

    const frame = (now: number) => {
      const dt = Math.max(0, Math.min(0.05, (now - last) / 1000))
      last = now
      const t = now - t0

      if (endAt < 0 && finishRef.current) {
        if (finishRef.current === 'fail') {
          failed = true
          endAt = t
        } else if (t >= MIN_THINK) {
          endAt = t
          setResolved(true)
        }
      }

      // Flight: a ball from the send button to the sphere's place, on a curve, growing on the way.
      const u = easeIo(span(t, 0, FLY))
      const d = t < FLY * 0.82 ? lerp(BALL, ORB_D * 1.06, easeIo(span(t, 0, FLY * 0.82))) : lerp(ORB_D * 1.06, ORB_D, easeOut(span(t, FLY * 0.82, FLY)))
      const bx = bez(u, startX, ctrlX, C0)
      const by = bez(u, startY, ctrlY, C0)
      let ballOp = easeOut(span(t, 0, 120)) * (1 - easeOut(span(t, FLY, FLY + 240)))

      const a = t - FLY
      let labelOp = easeOut(span(a, 200, 520))
      const o: Orb = {
        k: easeOut(span(a, 0, 700)),
        alpha: a <= 0 ? 0 : easeOut(span(a, 0, 700)),
        spin: 0.9 * easeOut(span(a, 0, 700)),
        pop: a < 380 ? lerp(1, 1.05, easeOut(span(a, 0, 380))) : lerp(1.05, 1, easeIo(span(a, 380, 700))),
        sweep: 0, vortex: 0, gain: 1, floor: 0, rad: 0,
      }
      let greenOp = 0
      let greenScale = 0.55
      let greenX = C0
      let greenY = C0
      let ringT = -1

      if (endAt >= 0 && failed) {
        const f = 1 - easeOut(span(t, endAt, endAt + 220))
        o.alpha *= f
        labelOp *= f
        ballOp *= f
        if (t >= endAt + 220) end()
      } else if (endAt >= 0) {
        // The sphere turns green from the top and settles.
        const r = t - endAt
        o.sweep = easeIo(span(r, 0, 560))
        o.spin = lerp(0.9, 0.3, easeOut(span(r, 0, 560)))
        o.gain = 1 - easeOut(span(r, 0, 560))
        o.floor = 0.95 * easeOut(span(r, 300, RESOLVE))
        o.rad = 0.15 * easeOut(span(r, 300, RESOLVE))
        o.pop = r < 480 ? 1 : r < 620 ? lerp(1, 1.04, easeOut(span(r, 480, 620))) : lerp(1.04, 1, easeOut(span(r, 620, RESOLVE)))
        // It collapses in a twist into a green ball, with one ring going out.
        const c = r - RESOLVE
        if (c > 0) {
          const v = easeIo(span(c, 80, 520))
          o.pop = c < 80 ? lerp(1, 1.06, easeOut(span(c, 0, 80))) : 1.06
          o.k = 1 - v
          o.vortex = 1.6 * v
          o.alpha = 1 - easeOut(span(c, 400, CONDENSE))
          labelOp = 1 - easeIn(span(c, 0, 160))
          greenOp = easeOut(span(c, 200, 420))
          greenScale = lerp(0.55, 1, spring(span(c, 200, 580)))
          ringT = c >= 260 ? span(c, 260, CONDENSE) : -1
        }
        // The green ball settles where the answer's avatar is, and the answer unfolds from there.
        const x = c - CONDENSE
        if (x > 0) {
          const f = easeIo(span(x, 0, OUT))
          greenX = lerp(C0, AVATAR_X, f)
          greenY = lerp(C0, AVATAR_Y, f)
          greenScale = lerp(1, AVATAR / GREEN, f)
          if (x >= OUT) end()
        }
      }

      drawOrb(dt, o)
      b.style.width = b.style.height = `${d.toFixed(1)}px`
      b.style.transform = `translate3d(${(bx - d / 2).toFixed(1)}px,${(by - d / 2).toFixed(1)}px,0)`
      b.style.opacity = ballOp.toFixed(3)
      st.style.opacity = labelOp.toFixed(3)
      g.style.opacity = clamp01(greenOp).toFixed(3)
      g.style.transform = `translate3d(${(greenX - GREEN / 2).toFixed(1)}px,${(greenY - GREEN / 2).toFixed(1)}px,0) scale(${greenScale.toFixed(3)})`
      rg.style.opacity = ringT < 0 ? '0' : (0.5 * (1 - ringT)).toFixed(3)
      rg.style.transform = `translate3d(${C0 - GREEN / 2}px,${C0 - GREEN / 2}px,0) scale(${(1 + 0.9 * Math.max(0, ringT)).toFixed(3)})`
      if (!over) raf = requestAnimationFrame(frame)
    }
    raf = requestAnimationFrame(frame)
    return () => cancelAnimationFrame(raf)
  }, [])

  const text = resolved ? doneLabel : label ?? labels[turn % labels.length]

  return (
    <div className="oa-think" ref={stage}>
      <span className="oa-think-ball" ref={ball} aria-hidden="true" />
      <canvas className="oa-think-orb" ref={canvas} style={{ width: CANVAS, height: CANVAS }} aria-hidden="true" />
      <span className="oa-think-ring" ref={ring} aria-hidden="true" />
      <span className="oa-think-green" ref={green} aria-hidden="true" />
      <div className="oa-wait" ref={status} role="status" aria-live="polite">
        <span key={text} className={`oa-wait-text${resolved ? ' done' : ''}`}>{text}</span>
      </div>
    </div>
  )
}
