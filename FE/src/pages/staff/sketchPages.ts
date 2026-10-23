/** Pages and strokes of a hand-edited sketch, in the `vhrs-trajectory/1` units (millimetres). */
export type PaperSize = 'A6' | 'A5' | 'A4'
export interface EditorStroke { kind: string; points: [number, number][] }
export interface EditorPage { size: PaperSize; strokes: EditorStroke[] }

/** Paper in millimetres, the unit of `vhrs-trajectory/1` (origin top-left, y down). */
export const PAPER_MM: Record<PaperSize, [number, number]> = { A6: [105, 148], A5: [148, 210], A4: [210, 297] }
export const SIZES: PaperSize[] = ['A6', 'A5', 'A4']
export const MAX_PAGES = 10
/** A point closer than this to the last one adds nothing to the pen path. */
export const MIN_STEP_MM = 0.4
export const PEN_MM = 0.7
export const HIT_MM = 3

export const blankPage = (size: PaperSize = 'A4'): EditorPage => ({ size, strokes: [] })

/** Reads a stored trajectory into editable pages; anything that is not a valid page or stroke is skipped. */
export function pagesFromTrajectory(data: unknown): EditorPage[] {
  const raw = (data as { pages?: unknown })?.pages
  if (!Array.isArray(raw)) return []
  const out: EditorPage[] = []
  for (const rp of raw as { paper?: { size?: string }; strokes?: unknown }[]) {
    const size = rp?.paper?.size as PaperSize | undefined
    if (!size || !(size in PAPER_MM)) continue
    const strokes: EditorStroke[] = []
    if (Array.isArray(rp.strokes)) {
      for (const rs of rp.strokes as { kind?: string; points?: unknown }[]) {
        if (!Array.isArray(rs?.points)) continue
        const points = (rs.points as unknown[]).flatMap((p) => (Array.isArray(p) && Number.isFinite(p[0]) && Number.isFinite(p[1]) ? [[Number(p[0]), Number(p[1])] as [number, number]] : []))
        if (points.length >= 2) strokes.push({ kind: rs.kind ?? 'manual', points })
      }
    }
    out.push({ size, strokes })
  }
  return out
}

/** The body for `POST /sketches`. Empty pages are dropped because the backend refuses a page without strokes. */
export function trajectoryFromPages(pages: EditorPage[]) {
  return {
    format: 'vhrs-trajectory/1',
    pages: pages.filter((p) => p.strokes.length).map((p) => ({
      paper: { size: p.size },
      strokes: p.strokes.map((s) => ({ kind: s.kind, points: s.points.map(([x, y]) => [Math.round(x * 100) / 100, Math.round(y * 100) / 100]) })),
    })),
  }
}
