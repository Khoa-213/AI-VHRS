import type { TFn } from '../../i18n'
import type { InputMode, Order } from '../../types'

/**
 * Stand-in for the recognition and evaluation services. Scores are derived
 * from the order id (and the regenerate count), so an order always shows the
 * same numbers until staff regenerate it.
 */

export type Tone = 'plain' | 'mode' | 'good' | 'warn'

export interface Row {
  k: string
  v: string
  tone: Tone
}

export interface Check {
  k: string
  value: number
}

export const hashOf = (s: string) => {
  let h = 7
  for (const c of s) h = (h * 31 + c.charCodeAt(0)) % 9973
  return h
}

export const MODE_LABEL: Record<InputMode, string> = { text: 'TEXT', upload: 'IMAGE', draw: 'DRAWING' }
export const MODE_HEADING: Record<InputMode, string> = {
  text: 'Customer text',
  upload: 'Customer image',
  draw: 'Customer drawing',
}

export const REJECT_REASONS: Record<InputMode, string[]> = {
  text: ['Inappropriate content', 'Unsupported characters', 'Too long for format', 'Other'],
  upload: ['Blurry or low resolution', 'Not handwriting', 'Inappropriate content', 'Other'],
  draw: ['Too few samples', 'Illegible strokes', 'Inappropriate content', 'Other'],
}

/** Text staff are looking at: typed text, or what the photo or strokes were read as. */
export function recognizedText(order: Order, edited: string | undefined, t: TFn): string {
  const sp = order.spec
  if (sp.mode === 'text') return sp.text
  if (edited !== undefined) return edited
  if (order.ocrText !== undefined) return order.ocrText
  if (sp.mode === 'upload') return sp.simText ?? (sp.text || t('rec.unreadable'))
  return sp.simText ?? ''
}

export function recognitionRows(order: Order, text: string, t: TFn, tn: (s: string) => string): Row[] {
  const sp = order.spec
  const h = hashOf(order.id + (order.regen ?? 0))
  if (sp.mode === 'text') {
    const diacritics = (text.normalize('NFD').match(/[̀-ͯ]/g) ?? []).length
    const unsupported = (text.match(/[^\p{L}\p{N}\s.,!?&'"()\-:;/@#%+]/gu) ?? []).length
    return [
      { k: t('rec.detected'), v: t('rec.typed'), tone: 'mode' },
      { k: t('rec.language'), v: t(diacritics ? 'rec.vi' : 'rec.latin'), tone: 'plain' },
      { k: t('rec.characters'), v: String(text.length), tone: 'plain' },
      { k: t('rec.diacritics'), v: String(diacritics), tone: 'plain' },
      { k: t('rec.unsupported'), v: unsupported ? String(unsupported) : t('rec.none'), tone: unsupported ? 'warn' : 'good' },
      { k: t('rec.font'), v: t('rec.fontSingle', { name: tn(sp.fontName) }), tone: 'plain' },
    ]
  }
  if (sp.mode === 'upload') {
    return [
      { k: t('rec.detected'), v: t('rec.photo'), tone: 'mode' },
      { k: t('rec.file'), v: sp.fileName ?? 'customer-upload.jpg', tone: 'plain' },
      { k: t('rec.resolution'), v: sp.img ? t('rec.original') : '3024 × 4032', tone: 'plain' },
      { k: t('rec.sharpness'), v: `${78 + (h % 18)} / 100`, tone: 'good' },
      { k: t('rec.ocrConf'), v: `${86 + (h % 12)}%`, tone: 'good' },
    ]
  }
  return [
    { k: t('rec.detected'), v: t('rec.canvas'), tone: 'mode' },
    { k: t('rec.strokes'), v: String(40 + (h % 60)), tone: 'plain' },
    { k: t('rec.pressure'), v: t('rec.pencil'), tone: 'good' },
    { k: t('rec.samples'), v: t(h % 3 ? 'rec.sufficient' : 'rec.borderline'), tone: h % 3 ? 'good' : 'warn' },
  ]
}

export const PASS_SCORE = 80

export function evaluate(order: Order, text: string) {
  const h = hashOf(order.id + (order.regen ?? 0))
  const checks: Check[] = [
    { k: 'Legibility (OCR re-read)', value: 88 + (h % 11) },
    { k: 'Diacritic placement', value: 84 + ((h >> 2) % 15) },
    { k: 'Stroke continuity', value: 80 + ((h >> 3) % 18) },
    { k: 'Workspace fit (FR3 reach)', value: 97 + (h % 3) },
    { k: 'Ink load per piece', value: 76 + ((h >> 4) % 22) },
    { k: 'Layout balance', value: 82 + ((h >> 1) % 16) },
  ]
  const overall = Math.round(checks.reduce((a, c) => a + c.value, 0) / checks.length)
  const strokes = Math.round((text.length || 12) * 2.6 + 12)
  return { checks, overall, strokes, penLifts: Math.round(strokes * 0.32) }
}

export const checkTone = (v: number): 'good' | 'teal' | 'warn' => (v >= 90 ? 'good' : v >= 80 ? 'teal' : 'warn')
