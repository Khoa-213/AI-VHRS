import { useMemo } from 'react'
import { useT } from '../../../i18n'
import type { SketchPage } from '../../../services/sketch'
import { strokesOf, unitOfStroke, type SelectMode } from './select'

/** Bounding boxes of the selected units, for the dashed frames. */
function boxesOf(page: SketchPage, mode: SelectMode, sel: string[]): [number, number, number, number][] {
  if (mode === 'word') return page.words.filter((w) => sel.includes(w.id)).map((w) => w.bbox)
  if (mode === 'line') return (page.lines ?? []).filter((l) => sel.includes(l.id)).map((l) => l.bbox)
  if (mode === 'para') return (page.paragraphs ?? []).filter((p) => sel.includes(p.id)).map((p) => p.bbox)
  return []
}

/** The vector page (mm, origin top left). Click a stroke to select it, its word, line or paragraph. */
export default function SketchCanvas({ page, mode, sel, ink, onPick }: {
  page: SketchPage
  mode: SelectMode
  sel: string[]
  ink: string
  onPick: (unit: string | null, add: boolean) => void
}) {
  const t = useT()
  const picked = useMemo(() => strokesOf(page, mode, sel), [page, mode, sel])
  const boxes = boxesOf(page, mode, sel)
  const pad = 1.2
  return (
    <svg
      className="sk-svg"
      viewBox={`0 0 ${page.width_mm} ${page.height_mm}`}
      role="img"
      aria-label={t('sk.canvasAlt', { n: page.no })}
      onClick={(e) => {
        if (e.target === e.currentTarget) onPick(null, false)
      }}
    >
      <rect x={0} y={0} width={page.width_mm} height={page.height_mm} className="sk-paper" onClick={() => onPick(null, false)} />
      {page.strokes.map((s) => {
        const pts = s.points.map((p) => `${p[0]},${p[1]}`).join(' ')
        const by = s.edited_by?.[s.edited_by.length - 1]
        const cls = picked.has(s.id) ? 'sk-stroke on' : by === 'AI' ? 'sk-stroke ai' : by === 'CUSTOMER' ? 'sk-stroke me' : 'sk-stroke'
        return (
          <g key={s.id} onClick={(e) => { e.stopPropagation(); onPick(unitOfStroke(page, s.id, mode), e.shiftKey) }}>
            <polyline points={pts} className="sk-hit" />
            <polyline points={pts} className={cls} style={cls === 'sk-stroke' ? { stroke: ink } : undefined} />
          </g>
        )
      })}
      {boxes.map((b, i) => (
        <rect key={i} className="sk-box" x={b[0] - pad} y={b[1] - pad} width={b[2] - b[0] + pad * 2} height={b[3] - b[1] + pad * 2} rx={1} />
      ))}
    </svg>
  )
}
