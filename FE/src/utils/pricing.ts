import { INKS, PAPERS, PENS, TYPES } from '../constants/catalog'
import type { InputMode } from '../types'
import type { TFn } from '../i18n'
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
export function quote(q: QuoteInput, t: TFn, tn: (s: string) => string, locale: string) {
  const T = TYPES.find((t) => t.id === q.type)
  const P = PAPERS.find((t) => t.id === q.paper)
  const N = PENS.find((t) => t.id === q.pen)
  const I = INKS.find((t) => t.id === q.ink)

  let contentFee = 0
  let contentLabel = ''
  if (q.mode === 'text') {
    const extra = Math.max(0, q.text.length - 120)
    contentFee = extra * 200
    contentLabel = t('q.longText', { n: extra })
  } else if (q.mode === 'upload' && q.hasUpload) {
    contentFee = 30000
    contentLabel = t('q.vectorize')
  } else if (q.mode === 'draw' && q.strokes) {
    contentFee = 15000
    contentLabel = t('q.liveStroke')
  }

  const unit = (T?.base ?? 0) + (P?.price ?? 0) + (N?.price ?? 0) + (I?.price ?? 0)
  const rate = q.qty >= 50 ? 0.2 : q.qty >= 10 ? 0.1 : 0
  const discount = Math.round((unit * q.qty * rate) / 1000) * 1000
  const total = unit * q.qty + contentFee - discount

  const lines: QuoteLine[] = []
  if (T) lines.push({ label: `${tn(T.name)} × ${q.qty}`, value: fmt(T.base * q.qty) })
  if (P) lines.push({ label: t('q.paper', { name: tn(P.name) }), value: P.price ? fmt(P.price * q.qty) : t('q.included') })
  if (N) lines.push({ label: t('q.pen', { name: tn(N.name) }), value: N.price ? fmt(N.price * q.qty) : t('q.included') })
  if (I) lines.push({ label: t('q.ink', { name: tn(I.name) }), value: I.price ? fmt(I.price * q.qty) : t('q.included') })
  if (contentFee) lines.push({ label: contentLabel, value: fmt(contentFee) })
  if (discount) lines.push({ label: t('q.discount', { pct: rate * 100 }), value: '−' + fmt(discount), good: true })

  const mins = T ? T.mins * q.qty : 0
  const robotTime = !T ? '-' : mins < 60 ? t('q.min', { n: mins }) : t('q.hour', { n: (mins / 60).toFixed(1).replace('.0', '') })
  const days = 2 + Math.ceil(mins / 480)
  const eta = !T
    ? '-'
    : new Date(Date.now() + days * 864e5).toLocaleDateString(locale, { weekday: 'short', day: 'numeric', month: 'short' })

  return { T, P, N, I, total, lines, robotTime, eta }
}
