import { INKS, PAPERS, PENS, TYPES } from '../constants/catalog'
import type { InputMode } from '../types'
import { fmt } from './format'

export interface QuoteInput {
  type: string | null
  paper: string | null
  pen: string | null
  ink: string | null
  qty: number
  mode: InputMode
  text: string
  hasUpload: boolean
  strokes: number
}

export interface QuoteLine {
  label: string
  value: string
  good?: boolean
}

/** Live estimate shown beside the create-order form. Price locks at submit. */
export function quote(q: QuoteInput) {
  const T = TYPES.find((t) => t.id === q.type)
  const P = PAPERS.find((t) => t.id === q.paper)
  const N = PENS.find((t) => t.id === q.pen)
  const I = INKS.find((t) => t.id === q.ink)

  let contentFee = 0
  let contentLabel = ''
  if (q.mode === 'text') {
    const extra = Math.max(0, q.text.length - 120)
    contentFee = extra * 200
    contentLabel = `Long text +${extra} chars`
  } else if (q.mode === 'upload' && q.hasUpload) {
    contentFee = 30000
    contentLabel = 'AI vectorization'
  } else if (q.mode === 'draw' && q.strokes) {
    contentFee = 15000
    contentLabel = 'Live stroke capture'
  }

  const unit = (T?.base ?? 0) + (P?.price ?? 0) + (N?.price ?? 0) + (I?.price ?? 0)
  const rate = q.qty >= 50 ? 0.2 : q.qty >= 10 ? 0.1 : 0
  const discount = Math.round((unit * q.qty * rate) / 1000) * 1000
  const total = unit * q.qty + contentFee - discount

  const lines: QuoteLine[] = []
  if (T) lines.push({ label: `${T.name} × ${q.qty}`, value: fmt(T.base * q.qty) })
  if (P) lines.push({ label: `Paper · ${P.name}`, value: P.price ? fmt(P.price * q.qty) : 'Included' })
  if (N) lines.push({ label: `Pen · ${N.name}`, value: N.price ? fmt(N.price * q.qty) : 'Included' })
  if (I) lines.push({ label: `Ink · ${I.name}`, value: I.price ? fmt(I.price * q.qty) : 'Included' })
  if (contentFee) lines.push({ label: contentLabel, value: fmt(contentFee) })
  if (discount) lines.push({ label: `Volume discount ${rate * 100}%`, value: '−' + fmt(discount), good: true })

  const mins = T ? T.mins * q.qty : 0
  const robotTime = !T ? '—' : mins < 60 ? `${mins} min` : `${(mins / 60).toFixed(1).replace('.0', '')} h`
  const days = 2 + Math.ceil(mins / 480)
  const eta = !T
    ? '—'
    : new Date(Date.now() + days * 864e5).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })

  return { T, P, N, I, total, lines, robotTime, eta }
}
