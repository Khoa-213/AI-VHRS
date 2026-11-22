import { CheckCircle, Question, WarningCircle } from '@phosphor-icons/react'
import { useRef, useState } from 'react'
import { useAsync } from '../../hooks/useAsync'
import { useLocale, useT } from '../../i18n'
import { evaluatePhoto, jobQuality, type ProductPhoto, type QualityEvaluation } from '../../services/technician'
import JobFeedback from './JobFeedback'
import { flowError } from './flow'

const TONE: Record<string, string> = { PASS: 'good', NEEDS_REVIEW: 'warn', FAIL: 'bad' }
const ICON: Record<string, typeof CheckCircle> = { PASS: CheckCircle, NEEDS_REVIEW: Question, FAIL: WarningCircle }
/** Measurements shown from `metrics`, in this order, when the backend sent them as numbers. */
const METRICS: [string, string][] = [['coverage_pct', '%'], ['extra_ink_pct', '%'], ['chamfer_mm', 'mm'], ['hd95_mm', 'mm'], ['hausdorff_mm', 'mm'], ['tol_mm', 'mm']]

/**
 * Service G: compares a product photo with the approved sketch (`POST .../photos/{id}/evaluate`) and lists the job's results
 * (`GET .../quality`). The verdict is the backend's; it does not change the photo's QC result, which the technician still sets.
 */
export default function JobQuality({ jobId, photos, disabled, revision }: { jobId: number; photos: ProductPhoto[]; disabled: boolean; revision: number }) {
  const t = useT()
  const locale = useLocale()
  const q = useAsync(() => jobQuality(jobId), [jobId, revision])
  const lock = useRef(false)
  const [busy, setBusy] = useState<number | null>(null)
  const [pages, setPages] = useState<Record<number, string>>({})
  const [error, setError] = useState<{ photo: number; text: string } | null>(null)
  const results = q.data ?? []

  const evaluate = async (photo: number) => {
    if (lock.current) return
    const page = Number(pages[photo] || 1)
    lock.current = true
    setBusy(photo); setError(null)
    try {
      await evaluatePhoto(jobId, photo, page)
    } catch (e) {
      setError({ photo, text: flowError(e, t) })
    } finally {
      await q.reload()
      lock.current = false
      setBusy(null)
    }
  }

  const when = (iso: string) => new Date(iso).toLocaleString(locale, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Ho_Chi_Minh' })
  const kind = (photoId: number) => {
    const p = photos.find((x) => x.id === photoId)
    return p ? t(`td.flow.photo.${p.kind}`) : t('tq.photoN', { id: photoId })
  }

  return <div className="tq" aria-busy={busy !== null}>
    <div className="ph"><h3>{t('tq.title')}</h3><span className="sub">{t('tq.count', { n: results.length })}</span></div>
    <p className="sub">{t('tq.help')}</p>
    {photos.length > 0 && <ul className="tq-photos">
      {photos.map((p) => {
        const latest = results.find((r) => r.photo_id === p.id)
        const page = Number(pages[p.id] || 1)
        const pageOk = Number.isInteger(page)
          && page >= 1
          && page <= 10
        return <li key={p.id}>
          <div className="tq-photo-h"><b>{t(`td.flow.photo.${p.kind}`)}</b>{latest ? <Verdict r={latest} /> : <span className="sub">{t('tq.notYet')}</span>}</div>
          <div className="tq-act">
            <label className="vh-label">{t('tq.page')}<input className="vh-input" type="number" inputMode="numeric" min={1} max={10} value={pages[p.id] ?? '1'} disabled={disabled || busy !== null}
              onChange={(e) => setPages({ ...pages, [p.id]: e.target.value.replace(/\D/g, '').slice(0, 2) })} /></label>
            <button type="button" className="sd-btn" disabled={disabled || busy !== null || !pageOk} onClick={() => void evaluate(p.id)}>
              {t(busy === p.id ? 'tq.running' : latest ? 'tq.again' : 'tq.run')}
            </button>
          </div>
          {busy === p.id && <p className="sub" role="status">{t('tq.running')}</p>}
          {error?.photo === p.id && <p className="lg-error tech-error" role="alert">{error.text}</p>}
        </li>
      })}
    </ul>}
    <JobFeedback loading={q.loading && !q.data} error={q.error} retry={q.reload} />
    {q.data && !q.error && !results.length && <p className="sub">{t('tq.none')}</p>}
    {results.length > 0 && <details className="tq-history">
      <summary>{t('tq.history', { n: results.length })}</summary>
      <ol className="tech-event-list">{results.map((r) => <li key={r.id}>
        <div className="ph"><b>{kind(r.photo_id)} · {t('tq.pageN', { n: r.page })}</b><time dateTime={r.created_at}>{when(r.created_at)}</time></div>
        <Verdict r={r} />
        <Metrics r={r} />
        <p className="wk-text">{r.advisory}</p>
        {r.overlay_url && <a className="vh-link" href={r.overlay_url} target="_blank" rel="noreferrer">{t('tq.overlay')}</a>}
      </li>)}</ol>
    </details>}
    {results.length > 0 && <p className="sub">{t('tq.unvalidated')}</p>}
  </div>
}

function Verdict({ r }: { r: QualityEvaluation }) {
  const t = useT()
  const I = ICON[r.verdict] ?? Question
  const key = `tq.v.${r.verdict}`
  return <span className={`chip ${TONE[r.verdict] ?? 'mute'}`}><I size={14} aria-hidden /> {t(key) === key ? r.verdict : t(key)}</span>
}

function Metrics({ r }: { r: QualityEvaluation }) {
  const t = useT()
  const rows = METRICS.filter(([k]) => typeof r.metrics[k] === 'number')
  const warnings = Array.isArray(r.metrics.warnings) ? r.metrics.warnings.filter((w): w is string => typeof w === 'string') : []
  if (!rows.length && !warnings.length) return null
  return <>
    {rows.length > 0 && <dl className="wk-rows tq-metrics">{rows.map(([k, unit]) => <div key={k}><dt>{t(`tq.m.${k}`)}</dt><dd className="mono">{String(r.metrics[k])} {unit}</dd></div>)}</dl>}
    {warnings.length > 0 && <ul className="tq-warn">{warnings.map((w) => <li key={w} className="wk-warn">{w}</li>)}</ul>}
  </>
}
