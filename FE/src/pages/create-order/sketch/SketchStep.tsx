import { useCallback, useEffect, useMemo, useState } from 'react'
import { useT } from '../../../i18n'
import { ApiError } from '../../../services/api'
import { errText, orderErrorKey } from '../../../services/orders'
import {
  editSketch, generateSketch, getApplied, getSketch, listRevisions, moveTo, pathTo, redoSketch, setApplied, undoSketch,
  type Selection, type SketchLimits, type SketchOp, type SketchRevision, type WorkingSketch } from '../../../services/sketch'
import AssistantPanel from './AssistantPanel'
import SketchCanvas from './SketchCanvas'
import type { SelectMode } from './select'
import './sketch.css'

const QUICK: SketchOp[] = ['translate', 'rotate', 'scale', 'slant']
const MORE: SketchOp[] = ['curvature', 'smooth', 'extend', 'trim', 'join', 'split']
const MODES: SelectMode[] = ['stroke', 'word', 'line', 'para']
const AI_OPEN_KEY = 'aivhrs-sketch-ai-open'

interface Param { key: string; min: number; max: number; step: number; def: number; unit: string }

/** Slider ranges of an operation, from the backend's limits for this order type. */
function paramsOf(op: SketchOp, l: SketchLimits): Param[] {
  const shift = l.max_shift_mm ?? 3
  switch (op) {
    case 'translate': return [
      { key: 'dx_mm', min: -shift, max: shift, step: 0.1, def: 0, unit: 'mm' },
      { key: 'dy_mm', min: -shift, max: shift, step: 0.1, def: 0, unit: 'mm' },
    ]
    case 'rotate': return [{ key: 'degrees', min: -(l.max_rotate_deg ?? 15), max: l.max_rotate_deg ?? 15, step: 0.5, def: 0, unit: '°' }]
    case 'scale': return [{ key: 'factor', min: l.scale_range?.[0] ?? 0.8, max: l.scale_range?.[1] ?? 1.25, step: 0.01, def: 1, unit: '×' }]
    case 'slant': return [{ key: 'degrees', min: -(l.max_slant_deg ?? 15), max: l.max_slant_deg ?? 15, step: 0.5, def: 0, unit: '°' }]
    case 'curvature': return [{ key: 'factor', min: l.curvature_range?.[0] ?? 0.5, max: l.curvature_range?.[1] ?? 1.5, step: 0.05, def: 1, unit: '×' }]
    case 'smooth': return [{ key: 'passes', min: 1, max: 5, step: 1, def: 1, unit: '' }]
    case 'extend':
    case 'trim': return [{ key: 'mm', min: 0.1, max: l.max_extend_mm ?? 3, step: 0.1, def: 1, unit: 'mm' }]
    case 'split': return [{ key: 'at', min: 0.05, max: 0.95, step: 0.05, def: 0.5, unit: '' }]
    default: return []
  }
}

type Confirm =
  | { kind: 'redraw'; edited: number; kept: number; dropped: number }
  | { kind: 'undrawn'; retry(): Promise<void> }

/** A write from the canvas. */
interface Work { (): Promise<WorkingSketch | null> }

/** Open beside the canvas on wide screens; on narrow ones it is a drawer the customer opens. */
const readAiOpen = () => {
  if (typeof window !== 'undefined' && window.innerWidth <= 1100) return false
  try {
    return localStorage.getItem(AI_OPEN_KEY) !== '0'
  } catch {
    return true
  }
}

/**
 * Step "Sketch" of the create-order flow: the working sketch on a canvas, compact manual tools and the assistant beside
 * it. The canvas shows the applied revision (see `services/sketch.ts`).
 */
export default function SketchStep({ orderId, ink, onInputsRestored, onOrderChanged }: {
  orderId: number
  ink: string | null | undefined
  /** Undo / redo put the order form back to an earlier drawing: reload the form. */
  onInputsRestored: () => void
  /** The assistant changed the order's text or materials. */
  onOrderChanged: () => void
}) {
  const t = useT()
  const [shown, setShown] = useState<WorkingSketch | null>(null)
  const [cursor, setCursor] = useState<number | null>(null)
  const [revs, setRevs] = useState<SketchRevision[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [notice, setNotice] = useState('')
  const [pageIdx, setPageIdx] = useState(0)
  const [mode, setMode] = useState<SelectMode>('word')
  const [sel, setSel] = useState<string[]>([])
  const [op, setOp] = useState<SketchOp>('translate')
  const [values, setValues] = useState<Record<string, number>>({})
  const [moreOpen, setMoreOpen] = useState(false)
  const [confirm, setConfirm] = useState<Confirm | null>(null)
  const [aiOpen, setAiOpen] = useState(readAiOpen)
  const [proposals, setProposals] = useState<number[]>([])

  /** Shows `revisionId` (or the backend's current one) and makes it the applied revision. */
  const show = useCallback(async (revisionId?: number | null) => {
    const cur = await getSketch(orderId)
    if (!cur) {
      setShown(null)
      setCursor(null)
      setRevs([])
      setApplied(orderId, null)
      return
    }
    setCursor(cur.revision.id)
    let view = cur
    const want = revisionId ?? getApplied(orderId)
    if (want && want !== cur.revision.id) {
      try {
        view = (await getSketch(orderId, want)) ?? cur
      } catch {
        view = cur
      }
    }
    setApplied(orderId, view.revision.id)
    setShown(view)
    setRevs(await listRevisions(orderId))
  }, [orderId])

  useEffect(() => {
    show()
      .catch((e) => setErr(orderErrorKey(e)))
      .finally(() => setLoading(false))
  }, [show])

  const page = shown?.pages[Math.min(pageIdx, (shown?.pages.length ?? 1) - 1)] ?? null
  const params = paramsOf(op, shown?.limits ?? {})
  const applied = shown?.revision.id ?? null

  const selection: Selection | null = useMemo(() => {
    if (!sel.length) return null
    return mode === 'stroke' ? { stroke_ids: sel } : mode === 'word' ? { word_ids: sel } : mode === 'line' ? { line_ids: sel } : { paragraph_ids: sel }
  }, [mode, sel])

  const selectionLabel = !sel.length ? '' : t(`sk.sel.${mode}`, { n: sel.length })

  /** Runs a write from the canvas: first the backend cursor goes back to the applied revision. */
  const run = async (work: Work, after?: (s: WorkingSketch) => void) => {
    setErr('')
    setNotice('')
    setBusy(true)
    try {
      if (applied) await moveTo(orderId, applied)
      const res = await work()
      if (res) {
        await show(res.revision.id)
        if (res.inputsRestored) onInputsRestored()
        after?.(res)
      }
    } catch (e) {
      if (e instanceof ApiError && e.code === 'STALE_REVISION') {
        setNotice('sk.notice.stale')
        await show(null).catch(() => undefined)
      } else if (e instanceof ApiError && e.code === 'SKETCH_HAS_EDITS') {
        const d = (e.details ?? {}) as { edited_strokes?: number; reapplicable_edits?: unknown[]; edits?: unknown[] }
        const kept = d.reapplicable_edits?.length ?? 0
        setConfirm({ kind: 'redraw', edited: d.edited_strokes ?? 0, kept, dropped: Math.max(0, (d.edits?.length ?? 0) - kept) })
      } else {
        setErr(e instanceof ApiError && e.code === 'UNREACHABLE' ? 'sk.err.unreachable' : orderErrorKey(e))
      }
    } finally {
      setBusy(false)
    }
  }

  const generate = (discard = false) => run(() => generateSketch(orderId, discard), (s) => {
    setSel([])
    if (s.redraw) setNotice(t('sk.notice.redraw', { kept: s.redraw.reapplied.length, dropped: s.redraw.dropped.length }))
  })

  const step = (dir: 'undo' | 'redo', discard = false) => run(async () => {
    try {
      return await (dir === 'undo' ? undoSketch : redoSketch)(orderId, discard)
    } catch (e) {
      if (e instanceof ApiError && e.code === 'UNDRAWN_INPUT_CHANGES') {
        setConfirm({ kind: 'undrawn', retry: () => step(dir, true) })
        return null
      }
      throw e
    }
  })

  const applyEdit = (o: SketchOp = op) => {
    if (!applied || !selection) return
    const p: Record<string, unknown> = {}
    for (const x of paramsOf(o, shown?.limits ?? {})) p[x.key] = values[`${o}.${x.key}`] ?? x.def
    void run(() => editSketch(orderId, { base_revision_id: applied, op: o, params: p, ...selection }))
  }

  const pick = (unit: string | null, add: boolean) => {
    if (!unit) {
      setSel([])
      return
    }
    setSel((s) => (add ? (s.includes(unit) ? s.filter((x) => x !== unit) : [...s, unit]) : [unit]))
  }

  const toggleAi = (open: boolean) => {
    setAiOpen(open)
    try {
      localStorage.setItem(AI_OPEN_KEY, open ? '1' : '0')
    } catch {
      // ignore
    }
  }

  const reachable = (id: number) => cursor !== null && pathTo(revs, cursor, id) !== null

  if (loading) return <p className="co-lede" role="status">{t('co.loading')}</p>

  if (!shown || !page) {
    return (
      <div className="sk-empty">
        <h3 className="co-h3">{t('sk.emptyTitle')}</h3>
        <p className="co-sub-hint">{t('sk.emptyBody')}</p>
        <button type="button" className="co-btn co-btn--solid co-btn--sm" disabled={busy} onClick={() => void generate()}>
          {busy ? t('sk.drawing') : t('sk.generate')}
        </button>
        {err && <p className="lg-error" role="alert">{errText(t, err)}</p>}
      </div>
    )
  }

  const unitOk = mode !== 'stroke' || op !== 'join' || sel.length === 2
  const moreActive = MORE.includes(op)
  const proposalNo = proposals.indexOf(shown.revision.id) + 1
  const appliedBadge = proposalNo ? t('sk.ai.version', { n: proposalNo }) : shown.revision.author === 'ENGINE' ? t('sk.ver.original') : t('sk.ver.yours')
  const appliedName = proposalNo || shown.revision.author === 'AI' ? t('sk.ver.ai') : shown.revision.author === 'ENGINE' ? t('sk.ver.engine') : t('sk.ver.manual')

  return (
    <div className={`sk${aiOpen ? ' sk--ai' : ''}`}>
      {shown.inputsChanged && (
        <div className="sk-banner" role="status">
          <b>{t('sk.changedTitle')}</b>
          <span>{t('sk.changedBody')}</span>
          <button type="button" className="sk-btn sk-btn--solid" disabled={busy} onClick={() => void generate()}>{t('sk.regenerate')}</button>
        </div>
      )}

      <section className="sk-board" aria-label={t('sk.board')}>
        <div className="sk-bar">
          <div className="sk-seg" role="group" aria-label={t('sk.modeLabel')}>
            {MODES.map((m) => (
              <button key={m} type="button" className={mode === m ? 'on' : ''} aria-pressed={mode === m} onClick={() => { setMode(m); setSel([]) }}>
                {t(`sk.mode.${m}`)}
              </button>
            ))}
          </div>
          <span className="sk-sep" aria-hidden="true" />
          <div className="sk-tools" role="toolbar" aria-label={t('sk.tools')}>
            {QUICK.map((o) => (
              <button key={o} type="button" className={`sk-tool${op === o ? ' on' : ''}`} aria-pressed={op === o} onClick={() => { setOp(o); setMoreOpen(false) }}>
                {t(`sk.op.${o}`)}
              </button>
            ))}
            <div className="sk-more">
              <button type="button" className={`sk-tool sk-tool--more${moreActive ? ' on' : ''}`} aria-expanded={moreOpen} onClick={() => setMoreOpen((v) => !v)}>
                {moreActive ? t(`sk.op.${op}`) : t('sk.more')} ▾
              </button>
              {moreOpen && (
                <div className="sk-menu" role="menu">
                  {MORE.map((o) => (
                    <button key={o} type="button" role="menuitem" className={op === o ? 'on' : ''} onClick={() => { setOp(o); setMoreOpen(false) }}>
                      <b>{t(`sk.op.${o}`)}</b>
                      <span>{t(`sk.op.${o}.hint`)}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <button type="button" className="sk-tool sk-tool--del" disabled={busy || !selection} onClick={() => applyEdit('delete')}>{t('sk.op.delete')}</button>
          </div>
          <div className="sk-bar-end">
            <button type="button" className="sk-icon" aria-label={t('sk.undo')} title={t('sk.undo')} disabled={busy || !shown.canUndo} onClick={() => void step('undo')}>↶</button>
            <button type="button" className="sk-icon" aria-label={t('sk.redo')} title={t('sk.redo')} disabled={busy || !shown.canRedo} onClick={() => void step('redo')}>↷</button>
            <button type="button" className="sk-icon" aria-label={t('sk.redrawNow')} title={t('sk.redrawNow')} disabled={busy} onClick={() => void generate()}>⟳</button>
            {!aiOpen && <button type="button" className="sk-ai-open" onClick={() => toggleAi(true)}>{t('sk.ai.title')}</button>}
          </div>
        </div>

        <div className="sk-params">
          <span className="sk-params-title">{t(`sk.op.${op}`)} · {selectionLabel || t('sk.pickFirst')}</span>
          {params.map((x) => {
            const k = `${op}.${x.key}`
            const v = values[k] ?? x.def
            return (
              <label key={k} className="sk-range">
                {t(`sk.param.${x.key}`)}
                <input type="range" min={x.min} max={x.max} step={x.step} value={v} onChange={(e) => setValues((s) => ({ ...s, [k]: Number(e.target.value) }))} />
                <b>{Number(v.toFixed(2))}{x.unit}</b>
              </label>
            )
          })}
          {op === 'join' && <span className="sk-fine">{t('sk.joinHint')}</span>}
          <button type="button" className="sk-btn sk-btn--solid" disabled={busy || !selection || !unitOk} onClick={() => applyEdit()}>{t('sk.applyEdit')}</button>
        </div>

        <div className="sk-version">
          <span className="sk-badge">{appliedBadge}</span>
          <span className="sk-fine">{appliedName}</span>
          {shown.pages.length > 1 && (
            <span className="sk-pages">
              {shown.pages.map((p, i) => (
                <button key={p.no} type="button" className={i === pageIdx ? 'on' : ''} aria-pressed={i === pageIdx} onClick={() => { setPageIdx(i); setSel([]) }}>
                  {t('sk.page', { n: p.no })}
                </button>
              ))}
            </span>
          )}
        </div>

        <div className="sk-stage">
          <SketchCanvas page={page} mode={mode} sel={sel} ink={ink || '#1a2440'} onPick={pick} />
        </div>

        <div className="sk-legend">
          <span><i className="sk-key sk-key--sel" />{t('sk.legend.sel')}</span>
          <span><i className="sk-key sk-key--ai" />{t('sk.legend.ai')}</span>
          <span><i className="sk-key sk-key--me" />{t('sk.legend.me')}</span>
        </div>
        {notice && <p className="co-notice" role="status">{notice.startsWith('sk.') ? t(notice) : notice}</p>}
        {err && <p className="lg-error" role="alert">{errText(t, err)}</p>}
      </section>

      {aiOpen && (
        <AssistantPanel
          orderId={orderId}
          applied={applied}
          cursor={cursor}
          selection={selection}
          selectionLabel={selectionLabel}
          reachable={reachable}
          onBeforeSend={async (base) => {
            if (base !== cursor) await moveTo(orderId, base)
          }}
          onApply={(id) => {
            setErr('')
            setSel([])
            void show(id).catch((e) => setErr(orderErrorKey(e)))
          }}
          onTurn={(changed) => {
            // The canvas stays on the applied revision; only the list and the cursor move.
            void (async () => {
              const cur = await getSketch(orderId)
              setCursor(cur?.revision.id ?? null)
              setRevs(await listRevisions(orderId))
              if (!getApplied(orderId) && cur) await show(cur.revision.id)
            })().catch(() => undefined)
            if (changed) onOrderChanged()
          }}
          onClose={() => toggleAi(false)}
          onProposals={setProposals}
        />
      )}

      {confirm && (
        <div className="sk-dialog-back" role="presentation" onClick={() => setConfirm(null)}>
          <div className="sk-dialog" role="dialog" aria-modal="true" aria-labelledby="sk-dlg-t" onClick={(e) => e.stopPropagation()}>
            {confirm.kind === 'redraw' ? (
              <>
                <h3 id="sk-dlg-t">{t('sk.dlg.redrawTitle')}</h3>
                <p>{t('sk.dlg.redrawBody', { n: confirm.edited })}</p>
                <p className="sk-keep">{t('sk.dlg.keep', { n: confirm.kept })}</p>
                <p className="sk-lose">{t('sk.dlg.lose', { n: confirm.dropped })}</p>
                <p className="sk-fine">{t('sk.dlg.undoHint')}</p>
                <div className="sk-dialog-actions">
                  <button type="button" className="sk-btn" onClick={() => setConfirm(null)}>{t('sk.dlg.later')}</button>
                  <button type="button" className="sk-btn sk-btn--solid" onClick={() => { setConfirm(null); void generate(true) }}>{t('sk.dlg.redraw')}</button>
                </div>
              </>
            ) : (
              <>
                <h3 id="sk-dlg-t">{t('sk.dlg.undrawnTitle')}</h3>
                <p>{t('sk.dlg.undrawnBody')}</p>
                <div className="sk-dialog-actions">
                  <button type="button" className="sk-btn" onClick={() => setConfirm(null)}>{t('sk.dlg.keepText')}</button>
                  <button type="button" className="sk-btn sk-btn--danger" onClick={() => { const r = confirm.retry; setConfirm(null); void r() }}>{t('sk.dlg.discard')}</button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
