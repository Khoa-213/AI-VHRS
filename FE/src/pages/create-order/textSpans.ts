/**
 * Styles of parts of the text (italic, underline, strikethrough, a letter height of their own), as the order form edits
 * them. They are the `spans` of the text input's `layout` (`BE/docs/FE_API_GUIDE.md`, `GET /catalog/text-styles`):
 * `{start, end, size_mm?, italic?, underline?: 'single' | 'double', strike?}`, where `start` / `end` count the code
 * points of the text in Unicode NFC, `[start, end)`. Spans never overlap and never say nothing. There is no bold: the
 * robot would have to go over each line again (owner's decision).
 *
 * The form keeps the spans beside the plain text of the textarea and moves them when the text is edited (`remapSpans`).
 * Nothing here draws letters: what a style looks like is only ever shown by the backend's preview picture.
 */
import type { TextLayout } from '../../services/orders'

export type Underline = 'single' | 'double'

export interface CharStyle {
  size_mm?: number
  italic?: boolean
  underline?: Underline
  strike?: boolean
}

export interface Span extends CharStyle {
  start: number
  end: number
}

/** The backend's limits (`text_layout.py`). */
export const SIZE_MIN = 4
export const SIZE_MAX = 100
export const MAX_SPANS = 200

export type StyleChange =
  | { toggle: 'italic' | 'strike' }
  | { underline: Underline }
  | { size: number }
  | { clear: true }

const points = (s: string): string[] => [...s.normalize('NFC')]

/** How many characters the backend counts in this text (code points of its NFC form). */
export const length = (text: string): number => points(text).length

/** The backend's offset of a position in the textarea (`index` counts UTF-16 units, as `selectionStart` does). */
export const offsetAt = (text: string, index: number): number => points(text.slice(0, index)).length

/** The textarea position of a backend offset: the first position whose offset reaches it. */
export function indexAt(text: string, offset: number): number {
  let lo = 0
  let hi = text.length
  while (lo < hi) {
    const mid = (lo + hi) >> 1
    if (offsetAt(text, mid) < offset) lo = mid + 1
    else hi = mid
  }
  return lo
}

const styleOf = (s: CharStyle): CharStyle => ({
  ...(typeof s.size_mm === 'number' ? { size_mm: s.size_mm } : {}),
  ...(s.italic ? { italic: true } : {}),
  ...(s.underline ? { underline: s.underline } : {}),
  ...(s.strike ? { strike: true } : {}),
})

const same = (a: CharStyle, b: CharStyle) => a.size_mm === b.size_mm && !!a.italic === !!b.italic && a.underline === b.underline && !!a.strike === !!b.strike
const plain = (s: CharStyle) => same(s, {})

/** One style per character, then back to the fewest spans. */
function expand(spans: Span[], n: number): CharStyle[] {
  const out: CharStyle[] = Array.from({ length: n }, () => ({}))
  for (const s of spans) for (let i = Math.max(0, s.start); i < Math.min(s.end, n); i++) out[i] = styleOf(s)
  return out
}

function collapse(chars: CharStyle[]): Span[] {
  const out: Span[] = []
  for (let i = 0; i < chars.length; i++) {
    if (plain(chars[i])) continue
    const last = out.at(-1)
    if (last && last.end === i && same(last, chars[i])) last.end = i + 1
    else out.push({ start: i, end: i + 1, ...chars[i] })
  }
  return out
}

/** The spans a stored layout holds, read defensively and kept inside a text of `n` characters. */
export function spansFromLayout(layout: TextLayout | null | undefined, n = Number.MAX_SAFE_INTEGER): Span[] {
  const raw = Array.isArray(layout?.spans) ? (layout.spans as Record<string, unknown>[]) : []
  const spans: Span[] = []
  for (const r of raw) {
    const start = Number(r?.start)
    const end = Math.min(Number(r?.end), n)
    if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end <= start) continue
    const style = styleOf({
      size_mm: typeof r.size_mm === 'number' ? r.size_mm : undefined,
      italic: r.italic === true,
      underline: r.underline === 'single' || r.underline === 'double' ? r.underline : undefined,
      strike: r.strike === true,
    })
    if (!plain(style)) spans.push({ start, end, ...style })
  }
  return spans.sort((a, b) => a.start - b.start)
}

/** The spans as the backend takes them, cut to a text of `n` characters. */
export const spansForApi = (spans: Span[], n = Number.MAX_SAFE_INTEGER): Span[] =>
  spans.filter((s) => s.start < n).map((s) => ({ start: s.start, end: Math.min(s.end, n), ...styleOf(s) }))

/** One string per distinct set of spans, for "did it change" checks. */
export const spansKey = (spans: Span[]): string => JSON.stringify(spansForApi(spans))

/**
 * A style change on the characters `[from, to)`. Toggles work like a word processor: when every character already has the
 * style it is taken off, otherwise it is put on all of them. `null` when the result would pass the backend's span limit.
 */
export function applyStyle(spans: Span[], n: number, from: number, to: number, change: StyleChange): Span[] | null {
  const a = Math.max(0, Math.min(from, to))
  const b = Math.min(n, Math.max(from, to))
  if (b <= a) return spans
  const chars = expand(spans, n)
  const range = chars.slice(a, b)
  for (let i = a; i < b; i++) {
    const c = { ...chars[i] }
    if ('clear' in change) {
      chars[i] = {}
      continue
    }
    if ('toggle' in change) {
      const on = !range.every((x) => x[change.toggle])
      if (on) c[change.toggle] = true
      else delete c[change.toggle]
    } else if ('underline' in change) {
      if (range.every((x) => x.underline === change.underline)) delete c.underline
      else c.underline = change.underline
    } else {
      c.size_mm = change.size
    }
    chars[i] = c
  }
  const out = collapse(chars)
  return out.length > MAX_SPANS ? null : out
}

/**
 * The spans after the text changed from `before` to `after` (one edit: typing, deleting, pasting over a selection).
 * What sits before the edit stays, what sits after it moves along, text typed inside a styled part takes its style, and
 * a part whose characters were all removed goes.
 */
export function remapSpans(spans: Span[], before: string, after: string): Span[] {
  if (!spans.length) return spans
  const a = points(before)
  const b = points(after)
  let p = 0
  while (p < a.length && p < b.length && a[p] === b[p]) p++
  let s = 0
  while (s < a.length - p && s < b.length - p && a[a.length - 1 - s] === b[b.length - 1 - s]) s++
  const removed = a.length - p - s
  const added = b.length - p - s
  const delta = added - removed
  const cut = p + removed
  const out: Span[] = []
  for (const span of spans) {
    let { start, end } = span
    if (end <= p) {
      // before the edit
    } else if (start >= cut) {
      start += delta
      end += delta
    } else {
      start = start < p ? start : p + added
      end = end > cut ? end + delta : p + added
    }
    end = Math.min(end, b.length)
    if (end > start) out.push({ ...span, start, end })
  }
  return out
}
