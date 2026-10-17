import { useRef, useState } from 'react'
import type { Job, Run } from '../../services/async'
import { useAsync } from '../../hooks/useAsync'
import { useT } from '../../i18n'
import { orderErrorKey, errText } from '../../services/orders'
import { ApiError } from '../../services/api'
import {
  COMPLEXITIES, finalizeSketch, generateSketch, listSketches, patchSketch, sketchTrajectory, uploadTrajectory,
  type Complexity, type Sketch, type WorkOrder,
} from '../../services/workshop'

const SIZES = ['', 'A6', 'A5', 'A4'] as const

/** The AI sketch of an accepted order: generate versions, adjust complexity and notes, and finalize one (BR-22 needs this before a quotation). */
export default function SketchPanel({ order, onChanged }: { order: WorkOrder; onChanged: () => void }) {
  const t = useT()
  const list = useAsync(() => listSketches(order.id), [order.id])
  const [size, setSize] = useState<(typeof SIZES)[number]>('')
  const file = useRef<HTMLInputElement>(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [detail, setDetail] = useState('')
  const sketches = [...(list.data ?? [])].sort((a, b) => b.version - a.version)
  const unsupported = order.type === 'OT2_LEARNED_STYLE'

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
      setErr(orderErrorKey(e))
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
        {sketches.map((s) => <SketchCard key={s.id} s={s} orderId={order.id} busy={busy} run={run} />)}
      </div>
      {list.data && !sketches.length && !unsupported && <p className="sd-sub">{t('wk.noSketch')}</p>}
    </section>
  )
}

function SketchCard({ s, orderId, busy, run }: { s: Sketch; orderId: number; busy: boolean; run: Run }) {
  const t = useT()
  const [note, setNote] = useState(s.note ?? '')
  return (
    <article className={`wk-sketch${s.isFinal ? ' final' : ''}`}>
      <header>
        <b>{t('ov.sketch', { v: s.version })}</b>
        {s.isFinal && <span className="wk-final">{t('wk.final')}</span>}
      </header>
      <div className="wk-previews">
        {s.previewUrls.map((u, i) => <img key={u} src={u} alt={t('opv.sketch', { n: i + 1 })} />)}
        {!s.previewUrls.length && <span className="sd-sub">{t('wk.noPreview')}</span>}
      </div>
      <dl className="wk-rows">
        {s.similarity !== null && <div><dt>{t('wk.similarity')}</dt><dd>{Math.round(s.similarity * 100) / 100}%</dd></div>}
        {s.writingSec !== null && <div><dt>{t('wk.writingTime')}</dt><dd>{t('wk.minutes', { n: Math.max(1, Math.round(s.writingSec / 60)) })}</dd></div>}
        {s.strokeMm !== null && <div><dt>{t('wk.strokeLength')}</dt><dd>{Math.round(s.strokeMm)} mm</dd></div>}
        {s.penLifts !== null && <div><dt>{t('wk.penLifts')}</dt><dd>{s.penLifts}</dd></div>}
      </dl>
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
        <button className="vh-btn vh-btn--ghost vh-btn--sm" disabled={busy} onClick={() => void run(async () => download(orderId, s.version))}>{t('wk.downloadTrajectory')}</button>
        {!s.isFinal && <button className="vh-btn vh-btn--primary vh-btn--sm" disabled={busy} onClick={() => void run(() => finalizeSketch(orderId, s.version))}>{t('wk.finalize')}</button>}
      </div>
    </article>
  )
}

/** Saves the pen path of a version as a JSON file. */
async function download(orderId: number, version: number) {
  const data = await sketchTrajectory(orderId, version)
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }))
  const a = document.createElement('a')
  a.href = url
  a.download = `order-${orderId}-sketch-v${version}.json`
  a.click()
  URL.revokeObjectURL(url)
}
