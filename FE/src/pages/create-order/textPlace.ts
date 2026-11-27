/**
 * Where the text sits on the sheet, as the order form edits it: top / middle / bottom, the four margins and the line
 * spacing. These are keys of the text input's `layout` (`BE/docs/FE_API_GUIDE.md`, `GET /catalog/text-styles`):
 * `vertical_align`, `margins_mm`, `line_spacing`. The styles of parts of the text (`spans`) are edited beside them
 * (`textSpans.ts`); per paragraph settings of a stored layout (made by the assistant or the studio) are carried along.
 */
import type { TextLayout } from '../../services/orders'

export type VerticalAlign = 'TOP' | 'MIDDLE' | 'BOTTOM'
export const VERTICAL_ALIGNS: VerticalAlign[] = ['TOP', 'MIDDLE', 'BOTTOM']
export const MARGIN_SIDES = ['top', 'bottom', 'left', 'right'] as const
export type MarginSide = (typeof MARGIN_SIDES)[number]

/** The backend's limits (`text_layout.py`): a margin is 5 to 80 mm, the line spacing 0.8 to 2.5. */
export const MARGIN_MIN = 5
export const MARGIN_MAX = 80
export const MARGIN_DEFAULT = 15
export const SPACING_MIN = 0.8
export const SPACING_MAX = 2.5
export const SPACING_DEFAULT = 1

/** The fields as typed: numbers stay text while the customer edits them. */
export interface Place {
  vertical: VerticalAlign
  top: string
  bottom: string
  left: string
  right: string
  spacing: string
}

export const DEFAULT_PLACE: Place = { vertical: 'MIDDLE', top: '15', bottom: '15', left: '15', right: '15', spacing: '1' }

const text = (n: number) => String(Math.round(n * 100) / 100)

const within = (raw: unknown, lo: number, hi: number, fallback: number): number => {
  const n = typeof raw === 'number' ? raw : typeof raw === 'string' && raw.trim() ? Number(raw) : NaN
  return Number.isFinite(n) ? Math.min(hi, Math.max(lo, n)) : fallback
}

/** The placement a stored layout holds; what it does not say is the backend's default (middle, 15 mm, spacing 1). */
export function placeFromLayout(layout: TextLayout | null | undefined): Place {
  const margins = (layout?.margins_mm ?? {}) as Record<string, unknown>
  const vertical = VERTICAL_ALIGNS.includes(layout?.vertical_align as VerticalAlign) ? (layout?.vertical_align as VerticalAlign) : 'MIDDLE'
  const side = (k: MarginSide) => text(within(margins[k], MARGIN_MIN, MARGIN_MAX, MARGIN_DEFAULT))
  return {
    vertical, top: side('top'), bottom: side('bottom'), left: side('left'), right: side('right'),
    spacing: text(within(layout?.line_spacing, SPACING_MIN, SPACING_MAX, SPACING_DEFAULT)),
  }
}

/** The layout to send: `base` (a stored layout, or null) with this placement written over it. Numbers are kept in range. */
export function layoutWithPlace(base: TextLayout | null | undefined, place: Place): TextLayout {
  return {
    ...(base ?? {}),
    version: 1,
    vertical_align: place.vertical,
    margins_mm: Object.fromEntries(MARGIN_SIDES.map((k) => [k, within(place[k], MARGIN_MIN, MARGIN_MAX, MARGIN_DEFAULT)])),
    line_spacing: within(place.spacing, SPACING_MIN, SPACING_MAX, SPACING_DEFAULT),
  }
}

/** One string per distinct placement, for "did it change" checks. */
export const placeKey = (place: Place): string => {
  const l = layoutWithPlace(null, place)
  return JSON.stringify([l.vertical_align, l.margins_mm, l.line_spacing])
}

/**
 * A stored layout with settings of single paragraphs (made by the assistant or the studio; this form does not edit them).
 * They are numbered by paragraph, so only the backend can carry them over an edit of the words (`keep_layout`).
 */
export const hasParagraphs = (layout: TextLayout | null | undefined): boolean =>
  Array.isArray(layout?.paragraphs) && layout.paragraphs.length > 0
