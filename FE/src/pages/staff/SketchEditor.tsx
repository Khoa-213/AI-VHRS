import { useRef, useState } from 'react'
import { ArrowCounterClockwise, Eraser, PencilSimple, Plus, Trash } from '@phosphor-icons/react'
import { useT } from '../../i18n'
import { HIT_MM, MAX_PAGES, MIN_STEP_MM, PAPER_MM, PEN_MM, SIZES, blankPage, type EditorPage, type PaperSize } from './sketchPages'

const path = (pts: [number, number][]) => pts.map(([x, y]) => `${x},${y}`).join(' ')

/**
 * Draw or edit the pen path of a sketch. The paper is an SVG whose units are millimetres, so what is drawn
 * is exactly what is saved. Pen strokes are saved as `manual`; strokes that came from a version keep their kind.
 */
export default function SketchEditor({ initial, busy, onSave, onCancel }: {
  initial: EditorPage[]
  busy: boolean
  onSave: (pages: EditorPage[]) => void
  onCancel: () => void
}) {
  const t = useT()
  const [pages, setPages] = useState<EditorPage[]>(initial.length ? initial : [blankPage()])
  const [history, setHistory] = useState<EditorPage[][]>([])
  const [cur, setCur] = useState(0)
  const [tool, setTool] = useState<'pen' | 'erase'>('pen')
  const [live, setLive] = useState<[number, number][] | null>(null)
  const svg = useRef<SVGSVGElement>(null)
  const drawing = useRef<[number, number][] | null>(null)

  const page = pages[cur]
  const [w, h] = PAPER_MM[page.size]
  const strokeCount = pages.reduce((n, p) => n + p.strokes.length, 0)

  const commit = (next: EditorPage[]) => {
    setHistory((hs) => [...hs.slice(-49), pages])
    setPages(next)
  }
  const patchPage = (i: number, change: (p: EditorPage) => EditorPage) => commit(pages.map((p, j) => (j === i ? change(p) : p)))

  const toMm = (e: React.PointerEvent): [number, number] => {
    const r = svg.current!.getBoundingClientRect()
    const x = ((e.clientX - r.left) / r.width) * w
    const y = ((e.clientY - r.top) / r.height) * h
    return [Math.min(w, Math.max(0, x)), Math.min(h, Math.max(0, y))]
  }

  const down = (e: React.PointerEvent<SVGSVGElement>) => {
    if (tool !== 'pen' || e.button > 0) return
    e.currentTarget.setPointerCapture(e.pointerId)
    drawing.current = [toMm(e)]
    setLive(drawing.current)
  }
  const move = (e: React.PointerEvent<SVGSVGElement>) => {
    const pts = drawing.current
    if (!pts) return
    const p = toMm(e)
    const last = pts[pts.length - 1]
    if (Math.hypot(p[0] - last[0], p[1] - last[1]) < MIN_STEP_MM) return
    drawing.current = [...pts, p]
    setLive(drawing.current)
  }
  const up = () => {
    const pts = drawing.current
    drawing.current = null
    setLive(null)
    // A tap leaves one point; a stroke needs two.
    if (pts && pts.length >= 2) patchPage(cur, (p) => ({ ...p, strokes: [...p.strokes, { kind: 'manual', points: pts }] }))
  }

  const erase = (index: number) => patchPage(cur, (p) => ({ ...p, strokes: p.strokes.filter((_, i) => i !== index) }))

  const undo = () => {
    const prev = history[history.length - 1]
    if (!prev) return
    setHistory(history.slice(0, -1))
    setPages(prev)
    setCur((c) => Math.min(c, prev.length - 1))
  }

  const addPage = () => {
    commit([...pages, blankPage(page.size)])
    setCur(pages.length)
  }
  const removePage = () => {
    commit(pages.filter((_, i) => i !== cur))
    setCur((c) => Math.max(0, c - 1))
  }

  return (
    <section className="wk-editor" aria-label={t('wk.editorTitle')}>
      <header className="wk-editor-head">
        <h4>{t('wk.editorTitle')}</h4>
        <span className="sd-sub">{t('wk.editorHelp')}</span>
      </header>

      <div className="wk-editor-bar">
        <div className="wk-tabs" role="group" aria-label={t('wk.editorTool')}>
          <button type="button" className={tool === 'pen' ? 'on' : ''} aria-pressed={tool === 'pen'} onClick={() => setTool('pen')}>
            <PencilSimple size={16} /> {t('wk.toolPen')}
          </button>
          <button type="button" className={tool === 'erase' ? 'on' : ''} aria-pressed={tool === 'erase'} onClick={() => setTool('erase')}>
            <Eraser size={16} /> {t('wk.toolErase')}
          </button>
        </div>
        <button type="button" className="vh-btn vh-btn--ghost vh-btn--sm" disabled={!history.length} onClick={undo}>
          <ArrowCounterClockwise size={16} /> {t('wk.undo')}
        </button>
        <button type="button" className="vh-btn vh-btn--ghost vh-btn--sm" disabled={!page.strokes.length} onClick={() => patchPage(cur, (p) => ({ ...p, strokes: [] }))}>
          <Trash size={16} /> {t('wk.clearPage')}
        </button>
        <label className="vh-label wk-editor-size">
          {t('wk.paperSize')}
          <select
            className="vh-select"
            value={page.size}
            disabled={!!page.strokes.length}
            title={page.strokes.length ? t('wk.sizeLocked') : undefined}
            onChange={(e) => patchPage(cur, (p) => ({ ...p, size: e.target.value as PaperSize }))}
          >
            {SIZES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
      </div>

      <div className="wk-editor-pages" role="tablist" aria-label={t('wk.editorPages')}>
        {pages.map((p, i) => (
          <button key={i} role="tab" type="button" aria-selected={i === cur} className={i === cur ? 'on' : ''} onClick={() => setCur(i)}>
            {t('wk.pageN', { n: i + 1 })} <span className="vh-mono">{p.strokes.length}</span>
          </button>
        ))}
        <button type="button" className="vh-btn vh-btn--ghost vh-btn--sm" disabled={pages.length >= MAX_PAGES} onClick={addPage}>
          <Plus size={16} /> {t('wk.addPage')}
        </button>
        {pages.length > 1 && (
          <button type="button" className="vh-btn vh-btn--ghost vh-btn--sm" onClick={removePage}>
            <Trash size={16} /> {t('wk.removePage')}
          </button>
        )}
      </div>

      <svg
        ref={svg}
        className={`wk-paper${tool === 'erase' ? ' erase' : ''}`}
        viewBox={`0 0 ${w} ${h}`}
        role="img"
        aria-label={t('wk.paperAria', { size: page.size, n: cur + 1 })}
        style={{ aspectRatio: `${w} / ${h}` }}
        onPointerDown={down}
        onPointerMove={move}
        onPointerUp={up}
        onPointerCancel={up}
      >
        <rect x="0" y="0" width={w} height={h} fill="#fbfaf5" />
        {page.strokes.map((s, i) => (
          <g key={i}>
            <polyline points={path(s.points)} className={`wk-stroke${s.kind === 'manual' ? '' : ' keep'}`} strokeWidth={PEN_MM} />
            {tool === 'erase' && (
              <polyline
                points={path(s.points)}
                className="wk-hit"
                strokeWidth={HIT_MM * 2}
                onPointerDown={() => erase(i)}
                onPointerEnter={(e) => { if (e.buttons === 1) erase(i) }}
              />
            )}
          </g>
        ))}
        {live && <polyline points={path(live)} className="wk-stroke" strokeWidth={PEN_MM} />}
      </svg>

      <div className="wk-editor-foot">
        <span className="sd-sub" aria-live="polite">{strokeCount ? t('wk.strokeCount', { n: strokeCount }) : t('wk.editorEmpty')}</span>
        <div className="wk-actions">
          <button type="button" className="vh-btn vh-btn--ghost vh-btn--md" disabled={busy} onClick={onCancel}>{t('wk.cancelEdit')}</button>
          <button type="button" className="vh-btn vh-btn--primary vh-btn--md" disabled={busy || !strokeCount} onClick={() => onSave(pages)}>
            {t(busy ? 'wk.saving' : 'wk.saveVersion')}
          </button>
        </div>
      </div>
    </section>
  )
}
