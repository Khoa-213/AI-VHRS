import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { useT } from '../../../i18n'
import { emptySelection, selectionSize, type AiSelection, type SketchInfo, type SketchPage } from '../../../services/orderAi'

type Unit = 'word' | 'line' | 'paragraph' | 'stroke'
const UNITS: Unit[] = ['word', 'line', 'paragraph', 'stroke']
const KEY: Record<Unit, keyof AiSelection> = { word: 'word_ids', line: 'line_ids', paragraph: 'paragraph_ids', stroke: 'stroke_ids' }

const toggle = (list: string[], id: string) => (list.includes(id) ? list.filter((x) => x !== id) : [...list, id])
const press = (fn: () => void) => (e: KeyboardEvent) => {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault()
    fn()
  }
}

/** The strokes covered by what is picked, so a picked word, line or paragraph lights up its ink. */
function lit(page: SketchPage, sel: AiSelection): Set<string> {
  const out = new Set(sel.stroke_ids)
  const words = new Set(sel.word_ids)
  const lines = new Set(sel.line_ids)
  for (const g of page.paragraphs) if (sel.paragraph_ids.includes(g.id)) g.lineIds.forEach((l) => lines.add(l))
  for (const l of page.lines) if (lines.has(l.id)) l.wordIds.forEach((w) => words.add(w))
  for (const w of page.words) if (words.has(w.id)) w.strokeIds.forEach((s) => out.add(s))
  return out
}

/**
 * The sketch as vectors, to pick strokes, words, lines or paragraphs for the assistant (`selection` of the message).
 * With a pick the assistant may change only that part. Opens as a dialog so the sketch is large enough to touch.
 */
export default function SketchPicker({ sketch, selection, onChange, onClose }: {
  sketch: SketchInfo
  selection: AiSelection
  onChange: (s: AiSelection) => void
  onClose: () => void
}) {
  const t = useT()
  const dialog = useRef<HTMLDialogElement>(null)
  const [unit, setUnit] = useState<Unit>('word')
  const [page, setPage] = useState(1)

  useEffect(() => {
    const d = dialog.current
    if (d && !d.open) d.showModal()
  }, [])

  const pages = sketch.document
  const at = Math.min(Math.max(1, page), Math.max(1, pages.length))
  const pg = pages[at - 1]
  const picked = selectionSize(selection)
  const k = KEY[unit]
  const flip = (id: string) => onChange({ ...selection, [k]: toggle(selection[k], id) })
  const on = (id: string) => selection[k].includes(id)

  const boxes: { id: string; bbox: [number, number, number, number]; label: string }[] = !pg ? []
    : unit === 'word' ? pg.words.map((w) => ({ id: w.id, bbox: w.bbox, label: w.text ?? `${t('oa.pick.word')} ${w.id}` }))
    : unit === 'line' ? pg.lines.map((l) => ({ id: l.id, bbox: l.bbox, label: `${t('oa.pick.line')} ${l.id}` }))
    : unit === 'paragraph' ? pg.paragraphs.map((g) => ({ id: g.id, bbox: g.bbox, label: `${t('oa.pick.paragraph')} ${g.id}` }))
    : []
  const marked = pg ? lit(pg, selection) : new Set<string>()
  const pad = 0.8

  return (
    <dialog ref={dialog} className="oa-pick" aria-labelledby="oa-pick-title" onClose={onClose} onCancel={onClose}>
      <header className="oa-pick-head">
        <b id="oa-pick-title">{t('oa.pick.title')}</b>
        <span className="oa-fine">{t('oa.pick.hint')}</span>
      </header>

      <div className="oa-pick-units" role="radiogroup" aria-label={t('oa.pick.unit')}>
        {UNITS.map((u) => (
          <button key={u} type="button" role="radio" aria-checked={unit === u} className={`co-btn co-btn--sm ${unit === u ? 'co-btn--solid' : 'co-btn--line'}`} onClick={() => setUnit(u)}>
            {t(`oa.pick.${u}`)}
          </button>
        ))}
      </div>

      <div className="oa-pick-stage">
        {pg ? (
          <svg className="oa-pick-svg" viewBox={`0 0 ${pg.width} ${pg.height}`} role="group" aria-label={t('oa.imgAlt')} preserveAspectRatio="xMidYMid meet">
            <rect x="0" y="0" width={pg.width} height={pg.height} className="oa-pick-paper" />
            {pg.strokes.map((s) => (
              <polyline key={s.id} className={marked.has(s.id) ? 'oa-pick-ink on' : 'oa-pick-ink'} points={s.points.map((p) => `${p[0]},${p[1]}`).join(' ')} />
            ))}
            {unit === 'stroke'
              ? pg.strokes.map((s) => (
                <polyline key={`hit-${s.id}`} className="oa-pick-hit oa-pick-hit--stroke" points={s.points.map((p) => `${p[0]},${p[1]}`).join(' ')}
                  role="button" tabIndex={0} aria-pressed={on(s.id)} aria-label={`${t('oa.pick.stroke')} ${s.id}`}
                  onClick={() => flip(s.id)} onKeyDown={press(() => flip(s.id))} />
              ))
              : boxes.map((b) => (
                <rect key={b.id} className={`oa-pick-hit${on(b.id) ? ' on' : ''}`} x={b.bbox[0] - pad} y={b.bbox[1] - pad}
                  width={b.bbox[2] - b.bbox[0] + pad * 2} height={b.bbox[3] - b.bbox[1] + pad * 2}
                  role="button" tabIndex={0} aria-pressed={on(b.id)} aria-label={b.label}
                  onClick={() => flip(b.id)} onKeyDown={press(() => flip(b.id))} />
              ))}
          </svg>
        ) : (
          <span className="co-hint">{t('oa.sketchEmpty')}</span>
        )}
      </div>

      {pages.length > 1 && (
        <div className="oa-pager">
          <button type="button" className="co-btn co-btn--line co-btn--sm" disabled={at <= 1} aria-label={t('oa.prevPage')} onClick={() => setPage(at - 1)}>‹</button>
          <span className="vh-mono">{t('oa.page', { n: at, total: pages.length })}</span>
          <button type="button" className="co-btn co-btn--line co-btn--sm" disabled={at >= pages.length} aria-label={t('oa.nextPage')} onClick={() => setPage(at + 1)}>›</button>
        </div>
      )}

      {unit !== 'stroke' && pg && !boxes.length && <p className="oa-fine" role="status">{t('oa.pick.none')}</p>}

      <footer className="oa-pick-foot">
        <span role="status">{picked ? t('oa.picked', { n: picked }) : t('oa.pick.empty')}</span>
        <button type="button" className="co-btn co-btn--line co-btn--sm" disabled={!picked} onClick={() => onChange(emptySelection())}>{t('oa.clearPick')}</button>
        <button type="button" className="co-btn co-btn--solid co-btn--sm" onClick={() => dialog.current?.close()}>{t('oa.pick.done')}</button>
      </footer>
    </dialog>
  )
}
