import type { SketchPage } from '../../../services/sketch'

export type SelectMode = 'stroke' | 'word' | 'line' | 'para'

/** Which units of the page a click on a stroke selects, by mode. */
export function unitOfStroke(page: SketchPage, strokeId: string, mode: SelectMode): string | null {
  if (mode === 'stroke') return strokeId
  const word = page.strokes.find((s) => s.id === strokeId)?.word ?? null
  if (!word) return null
  if (mode === 'word') return word
  const line = page.lines?.find((l) => l.word_ids.includes(word))
  if (!line) return null
  return mode === 'line' ? line.id : line.paragraph
}

/** Stroke ids covered by the selection, to colour them. */
export function strokesOf(page: SketchPage, mode: SelectMode, sel: string[]): Set<string> {
  if (mode === 'stroke') return new Set(sel)
  let words: string[] = []
  if (mode === 'word') words = sel
  else if (mode === 'line') words = (page.lines ?? []).filter((l) => sel.includes(l.id)).flatMap((l) => l.word_ids)
  else {
    const lines = (page.paragraphs ?? []).filter((p) => sel.includes(p.id)).flatMap((p) => p.line_ids)
    words = (page.lines ?? []).filter((l) => lines.includes(l.id)).flatMap((l) => l.word_ids)
  }
  return new Set(page.words.filter((w) => words.includes(w.id)).flatMap((w) => w.stroke_ids))
}

