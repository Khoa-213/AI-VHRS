import { useRef, useState } from 'react'
import { PencilSimple } from '@phosphor-icons/react'
import type { Job, Run } from '../../services/async'
import { useAsync } from '../../hooks/useAsync'
import { useT } from '../../i18n'
import { orderErrorKey, errText } from '../../services/orders'
import { ApiError } from '../../services/api'
import {
  COMPLEXITIES, finalizeSketch, generateSketch, listSketches, patchSketch, sketchFileBytes, sketchTrajectory, uploadTrajectory,
  type Complexity, type Sketch, type WorkOrder,
} from '../../services/workshop'
import SketchEditor from './SketchEditor'
import { blankPage, pagesFromTrajectory, trajectoryFromPages, type EditorPage } from './sketchPages'

const SIZES = ['', 'A6', 'A5', 'A4'] as const
/** Preview links last 10 minutes; ask again before they run out. */
const REFRESH_MS = 8 * 60_000

/** The AI sketch of an accepted order: generate versions, adjust complexity and notes, and finalize one (BR-22 needs this before a quotation). */
export default function SketchPanel({ order, onChanged }: { order: WorkOrder; onChanged: () => void }) {
  const t = useT()
  const list = useAsync(() => listSketches(order.id), [order.id], REFRESH_MS)
  const [size, setSize] = useState<(typeof SIZES)[number]>('')
  const file = useRef<HTMLInputElement>(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [detail, setDetail] = useState('')
  const [editing, setEditing] = useState<EditorPage[] | null>(null)
  const sketches = [...(list.data ?? [])].sort((a, b) => b.version - a.version)
  const unsupported = order.type === 'OT2_LEARNED_STYLE'

  // A broken preview usually means its link expired. Ask once in a while, so a link that never works cannot loop.
  const lastRefresh = useRef(0)
  const refreshLinks = () => {
    if (Date.now() - lastRefresh.current < 30_000) return
    lastRefresh.current = Date.now()
    void list.reload()
  }

  const run = async (job: Job) => {
    if (busy) return
    setBusy(true)
    setErr('')
    setDetail('')
    try {
      await job()
      await list.reload()
      onChanged()
    } catch (e) {
      // Errors from outside the API (the storage download) already carry a translation key.
      setErr(!(e instanceof ApiError) && e instanceof Error && e.message.startsWith('wk.') ? e.message : orderErrorKey(e))
      // UNSUPPORTED_CHARS lists the characters the single-line fonts cannot draw.
      if (e instanceof ApiError && e.details && !Array.isArray(e.details)) setDetail(JSON.stringify(e.details))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="wk-block" aria-label={t('wk.sketch')}>
      <h3>{t('wk.sketch')}</h3>
      <p className="sd-sub">{t(unsupported ? 'wk.sketchOt2' : 'wk.sketchLede')}</p>

      <div className="wk-actions">
        <button className="vh-btn vh-btn--ghost vh-btn--sm" disabled={busy || !!editing} onClick={() => setEditing([blankPage()])}>
          <PencilSimple size={16} /> {t('wk.draw')}
        </button>
        <input
          ref={file}
          type="file"
          accept="application/json,.json"
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0]
            e.target.value = ''
            if (!f) return
            void run(async () => uploadTrajectory(order.id, JSON.parse(await f.text()) as unknown, note))
          }}
        />
        <button className="vh-btn vh-btn--ghost vh-btn--sm" disabled={busy} onClick={() => file.current?.click()}>{t('wk.uploadTrajectory')}</button>
      </div>
      {editing && (
        <SketchEditor
          initial={editing}
          busy={busy}
          onCancel={() => setEditing(null)}
          onSave={(pages) => void run(async () => {
            await uploadTrajectory(order.id, trajectoryFromPages(pages), note)
            setEditing(null)
          })}
        />
      )}
      {!unsupported && (
        <div className="wk-form">
          <label className="vh-label">
            {t('wk.paperSize')}
            <select className="vh-select" value={size} onChange={(e) => setSize(e.target.value as (typeof SIZES)[number])}>
              {SIZES.map((s) => <option key={s || 'auto'} value={s}>{s || t('wk.paperAuto')}</option>)}
            </select>
          </label>
          <label className="vh-label wk-grow">
            {t('wk.approach')}
            <input className="vh-input" value={note} maxLength={2000} placeholder={t('wk.approachPh')} onChange={(e) => setNote(e.target.value)} />
          </label>
          <button className="vh-btn vh-btn--primary vh-btn--md" disabled={busy} onClick={() => void run(() => generateSketch(order.id, {
            ...(size ? { paper_size: size } : {}),
            ...(note.trim() ? { approach_note: note.trim() } : {}),
            // A new seed gives another variation of the same input.
            ...(sketches.length ? { seed: Math.floor(Math.random() * 1_000_000) } : {}),
          }))}>
            {t(busy ? 'wk.generating' : sketches.length ? 'wk.regenerate' : 'wk.generate')}
          </button>
        </div>
      )}
      {err && <p className="lg-error" role="alert">{errText(t, err)}{detail ? ` ${detail}` : ''}</p>}
      {list.loading && !list.data && <p className="sd-sub" role="status">{t('co.loading')}</p>}

      <div className="wk-sketches">
        {sketches.map((s) => <SketchCard key={s.id} s={s} orderId={order.id} busy={busy || !!editing} run={run} onEdit={setEditing} onExpired={refreshLinks} />)}
      </div>
      {list.data && !sketches.length && !unsupported && <p className="sd-sub">{t('wk.noSketch')}</p>}
    </section>
  )
}

function SketchCard({ s, orderId, busy, run, onEdit, onExpired }: {
  s: Sketch; orderId: number; busy: boolean; run: Run; onEdit: (pages: EditorPage[]) => void; onExpired: () => void
}) {
  const t = useT()
  const [note, setNote] = useState(s.note ?? '')
  return (
    <article className={`wk-sketch${s.isFinal ? ' final' : ''}`}>
      <header>
        <b>{t('ov.sketch', { v: s.version })}</b>
        {s.isFinal && <span className="wk-final">{t('wk.final')}</span>}
      </header>
      <div className="wk-outputs">
        <RobotFile s={s} orderId={orderId} />
        <section className="wk-output" aria-label={t('wk.out.image')}>
          <h4>{t('wk.out.image')}</h4>
          <p className="sd-sub">{t('wk.out.imageLede')}</p>
          <div className="wk-previews">
            {s.imageUrls.map((u, i) => <img key={u} src={u} alt={t('opv.sketch', { n: i + 1 })} onError={onExpired} />)}
            {!s.imageUrls.length && <span className="sd-sub">{t('wk.out.noImage')}</span>}
          </div>
        </section>
      </div>
      {s.warnings.map((w) => <p key={w} className="wk-warn">{w}</p>)}
      <div className="wk-form">
        <label className="vh-label">
          {t('wk.complexity')}
          <select
            className="vh-select"
            value={s.complexity ?? ''}
            disabled={busy}
            onChange={(e) => void run(() => patchSketch(orderId, s.version, { suggested_complexity: (e.target.value || null) as Complexity | null }))}
          >
            <option value="">{t('wk.complexity.auto')}</option>
            {COMPLEXITIES.map((c) => <option key={c} value={c}>{t(`cx.${c}`)}</option>)}
          </select>
        </label>
        <label className="vh-label wk-grow">
          {t('wk.approach')}
          <input className="vh-input" value={note} maxLength={2000} onChange={(e) => setNote(e.target.value)} />
        </label>
        <button className="vh-btn vh-btn--ghost vh-btn--sm" disabled={busy || note === (s.note ?? '')} onClick={() => void run(() => patchSketch(orderId, s.version, { approach_note: note.trim() || null }))}>{t('wk.saveNote')}</button>
        <button className="vh-btn vh-btn--ghost vh-btn--sm" disabled={busy || !s.trajectoryUrl} onClick={() => void run(async () => download(s, orderId, onExpired))}>{t('wk.file.download')}</button>
        <button className="vh-btn vh-btn--ghost vh-btn--sm" disabled={busy} onClick={() => void run(async () => onEdit(pagesFromTrajectory(await sketchTrajectory(orderId, s.version))))}>{t('wk.editVersion')}</button>
        {!s.isFinal && <button className="vh-btn vh-btn--primary vh-btn--sm" disabled={busy} onClick={() => void run(() => finalizeSketch(orderId, s.version))}>{t('wk.finalize')}</button>}
      </div>
    </article>
  )
}

interface FilePage { paper?: { size?: string; width_mm?: number; height_mm?: number }; strokes?: { kind?: string; points?: [number, number][] }[] }
interface RobotTrajectory { format?: string; engine?: { name?: string }; pages?: FilePage[] }

const pts = (p: [number, number][]) => p.map(([x, y]) => `${x},${y}`).join(' ')

/** What the robot will run: the stored `trajectory.json` drawn as it is (pen down, pen travel, stroke starts) with its numbers. */
function RobotFile({ s, orderId }: { s: Sketch; orderId: number }) {
  const t = useT()
  // The file of a version never changes, so it is read once.
  const file = useAsync(async () => (await sketchTrajectory(orderId, s.version)) as RobotTrajectory, [orderId, s.version])
  const [cur, setCur] = useState(0)
  const pages = file.data?.pages ?? []
  const page = pages[Math.min(cur, pages.length - 1)]
  const strokes = (page?.strokes ?? []).filter((k) => Array.isArray(k.points) && k.points.length >= 2)
  const w = page?.paper?.width_mm ?? 210
  const h = page?.paper?.height_mm ?? 297
  const strokeTotal = pages.reduce((n, p) => n + (p.strokes?.length ?? 0), 0)

  return (
    <section className="wk-output wk-output--robot" aria-label={t('wk.out.robot')}>
      <h4>{t('wk.out.robot')}</h4>
      <p className="sd-sub">{t('wk.out.robotLede')}</p>
      {file.loading && !file.data && <p className="sd-sub" role="status">{t('wk.file.loading')}</p>}
      {!!file.error && !file.data && (
        <p className="lg-error" role="alert">
          {errText(t, orderErrorKey(file.error))} <button className="vh-link" onClick={() => void file.reload()}>{t('wk.file.retry')}</button>
        </p>
      )}
      {page && (
        <>
          {pages.length > 1 && (
            <div className="wk-editor-pages" role="tablist" aria-label={t('wk.file.pages')}>
              {pages.map((_, i) => (
                <button key={i} role="tab" aria-selected={i === cur} className={i === cur ? 'on' : ''} onClick={() => setCur(i)}>{t('wk.file.page', { n: i + 1 })}</button>
              ))}
            </div>
          )}
          <svg className="wk-robot" viewBox={`0 0 ${w} ${h}`} role="img" aria-label={t('wk.file.svg', { n: cur + 1 })}>
            <rect width={w} height={h} className="wk-robot-paper" />
            {strokes.slice(1).map((k, i) => {
              const [x1, y1] = strokes[i].points!.at(-1)!
              const [x2, y2] = k.points![0]
              return <line key={`m${i}`} x1={x1} y1={y1} x2={x2} y2={y2} className="wk-robot-move" />
            })}
            {strokes.map((k, i) => <polyline key={i} points={pts(k.points!)} className="wk-robot-down" />)}
            {strokes.map((k, i) => <circle key={`s${i}`} cx={k.points![0][0]} cy={k.points![0][1]} r={0.9} className="wk-robot-start" />)}
          </svg>
          <ul className="wk-robot-legend">
            <li><i className="down" />{t('wk.file.down')}</li>
            <li><i className="move" />{t('wk.file.move')}</li>
            <li><i className="start" />{t('wk.file.start')}</li>
          </ul>
        </>
      )}
      <dl className="wk-rows">
        {file.data?.format && <div><dt>{t('wk.file.format')}</dt><dd>{file.data.format}</dd></div>}
        {file.data?.engine?.name && <div><dt>{t('wk.file.engine')}</dt><dd>{file.data.engine.name}</dd></div>}
        {file.data && <div><dt>{t('wk.file.pages')}</dt><dd>{pages.length}</dd></div>}
        {file.data && <div><dt>{t('wk.file.strokes')}</dt><dd>{strokeTotal}</dd></div>}
        {s.strokeMm !== null && <div><dt>{t('wk.strokeLength')}</dt><dd>{Math.round(s.strokeMm)} mm</dd></div>}
        {s.penLifts !== null && <div><dt>{t('wk.penLifts')}</dt><dd>{s.penLifts}</dd></div>}
        {s.writingSec !== null && <div><dt>{t('wk.writingTime')}</dt><dd>{t('wk.minutes', { n: Math.max(1, Math.round(s.writingSec / 60)) })}</dd></div>}
        {s.similarity !== null && <div><dt>{t('wk.similarity')}</dt><dd>{Math.round(s.similarity * 100) / 100}%</dd></div>}
        {s.contentHash && <div><dt>{t('wk.file.hash')}</dt><dd title={s.contentHash}><code>{s.contentHash.slice(0, 12)}</code></dd></div>}
      </dl>
    </section>
  )
}

/** Saves the stored robot file byte for byte, so its SHA-256 matches the one the job checks. */
async function download(s: Sketch, orderId: number, onExpired: () => void) {
  let blob: Blob
  try {
    blob = await sketchFileBytes(s.trajectoryUrl!)
  } catch (e) {
    onExpired()
    throw e
  }
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `order-${orderId}-sketch-v${s.version}.trajectory.json`
  a.click()
  URL.revokeObjectURL(url)
}
