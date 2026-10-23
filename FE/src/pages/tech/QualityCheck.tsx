import { useMemo, useRef, useState } from 'react'
import { ArrowLeft, ArrowsClockwise, Camera, Check, PaperPlaneTilt, Warning, X } from '@phosphor-icons/react'
import { useT, useTn } from '../../i18n'
import Shell from '../../components/ws/Shell'
import { ApiError } from '../../services/api'
import type { Job } from '../../services/async'
import { useAsync } from '../../hooks/useAsync'
import { Link } from '../../router/router'
import { MAX_UPLOAD_MB, errText, orderErrorKey } from '../../services/orders'
import {
  MAX_PHOTOS, MIN_LONG_SIDE_PX, failQc, getMyJob, listPhotos, removePhoto, setPhotoQc, submitPhotos, uploadPhoto,
  type Photo, type PhotoKind,
} from '../../services/technician'
import { PHOTO_SLOTS, QC_FAIL_REASONS, qcGroups } from './qcItems'
import '../staff/dashboard.css'
import '../staff/staff.css'
import '../staff/polish.css'
import './tech.css'
import './qc.css'

/** Phone photos are often HEIC or tiny; the backend refuses both, so say so before uploading. */
async function checkFile(file: File): Promise<void> {
  if (file.type !== 'image/jpeg' && file.type !== 'image/png') throw new Error('qc.err.type')
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) throw new Error('err.fileTooLarge')
  let side = 0
  try {
    const bmp = await createImageBitmap(file)
    side = Math.max(bmp.width, bmp.height)
    bmp.close()
  } catch {
    throw new Error('qc.err.format')
  }
  if (side < MIN_LONG_SIDE_PX) throw new Error('qc.err.small')
}

/** Photo and QC of a written job: tick the checklist, take the photos, mark each one, then send them to the customer. */
export default function QualityCheck({ id }: { id: number }) {
  const t = useT()
  const tn = useTn()
  const jobQ = useAsync(() => getMyJob(id), [id])
  // Signed photo links last 10 minutes, so the list is asked again before they run out.
  const photoQ = useAsync(() => listPhotos(id), [id], 8 * 60_000)
  const job = jobQ.data
  const photos = photoQ.data ?? []

  const [ticked, setTicked] = useState<Record<string, boolean>>({})
  const [confirm, setConfirm] = useState(false)
  const [tab, setTab] = useState<'qc' | 'photos'>('qc')
  const [failing, setFailing] = useState(false)
  const [reasons, setReasons] = useState<string[]>([])
  const [failNote, setFailNote] = useState('')
  const [markFail, setMarkFail] = useState<{ id: number; note: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [sent, setSent] = useState<'ok' | 'failed' | null>(null)
  const inputs = useRef<Record<string, HTMLInputElement | null>>({})
  const lastRefresh = useRef(0)

  const groups = useMemo(() => (job ? qcGroups(job, t) : []), [job, t])
  const all = groups.flatMap((g) => g.items)
  const done = all.filter((i) => ticked[i.id]).length

  const shell = (body: React.ReactNode) => (
    <Shell
      area="tech"
      active="qc"
      title={job ? t('qc.title', { id: job.orderCode }) : t('qc.titleShort')}
      lede={job ? t('qc.subtitleJob', { robot: job.robotCode }) : undefined}
      tools={<Link to="/tech/qc" className="sd-btn">{t('qc.another')}</Link>}
    >
      {body}
    </Shell>
  )

  if (!job) {
    const missing = jobQ.error instanceof ApiError && jobQ.error.status === 404
    return shell(
      jobQ.loading
        ? <p className="sd-sub" role="status">{t('co.loading')}</p>
        : <section className="sd-card"><div className="sd-empty"><b>{t('jr.notFound')}</b><span>{missing ? t('jr.notFoundBody') : errText(t, orderErrorKey(jobQ.error))}</span></div></section>,
    )
  }
  if (!sent && job.status !== 'WRITTEN') {
    const early = ['SCHEDULED', 'PREPARING', 'WRITING', 'PAUSED'].includes(job.status)
    return shell(
      <section className="sd-card">
        <div className="sd-empty">
          <b>{t(early ? 'qc.stillWriting' : 'qc.notOpen')}</b>
          <span>{t(early ? 'qc.opensAfter' : 'qc.notOpenBody', { status: t(`js.${job.status}`) })}</span>
          {early && <Link to={`/tech/preview/${job.id}`} className="vh-link">{t('qc.openRun')}</Link>}
        </div>
      </section>,
    )
  }

  const kindPhotos = (k: PhotoKind) => photos.filter((p) => p.kind === k)
  const passes = (k: PhotoKind) => kindPhotos(k).some((p) => p.qc === 'PASS')
  const missing = PHOTO_SLOTS.filter((s) => s.required && !passes(s.kind))
  const blocked = photos.some((p) => p.qc !== 'PASS')
  const ready = done === all.length && !missing.length && !blocked
  const requiredTotal = PHOTO_SLOTS.filter((s) => s.required).length
  const requiredDone = requiredTotal - missing.length
  const qcDone = done === all.length

  /** Runs one request with the page's busy and error handling; true when it worked. */
  const run = async (work: Job) => {
    if (busy) return false
    setBusy(true)
    setError('')
    try {
      await work()
      return true
    } catch (e) {
      setError(e instanceof Error && !(e instanceof ApiError) && /^(qc|err)\./.test(e.message) ? e.message : orderErrorKey(e))
      return false
    } finally {
      setBusy(false)
    }
  }

  const addPhoto = (kind: PhotoKind, file: File | undefined) => {
    if (!file) return
    void run(async () => {
      await checkFile(file)
      // The checklist is ticked before this step, so a new photo starts as PASS; "Mark failed" changes it.
      await uploadPhoto(job.id, file, kind, { result: 'PASS' })
      await photoQ.reload()
    })
  }
  const drop = (p: Photo) => void run(async () => { await removePhoto(job.id, p.id); await photoQ.reload() })
  const setQc = (p: Photo, result: 'PASS' | 'FAIL', note?: string) => void run(async () => {
    await setPhotoQc(job.id, p.id, result, note)
    setMarkFail(null)
    await photoQ.reload()
  })
  const brokenLink = () => {
    if (Date.now() - lastRefresh.current < 30_000) return
    lastRefresh.current = Date.now()
    void photoQ.reload()
  }

  const send = () => void run(async () => {
    await submitPhotos(job.id)
    setSent('ok')
  }).then(() => setConfirm(false))

  if (sent) {
    return shell(
      <section className="qc-sent" role="status">
        <b>{sent === 'ok' ? t('qc.sentOk', { name: t('qc.theCustomer') }) : t('qc.sentFail')}</b>
        <span>
          {sent === 'ok'
            ? t('qc.sentOkBody', { id: job.orderCode, photos: t(photos.length === 1 ? 'qc.photoOne' : 'qc.photoMany', { n: photos.length }) })
            : t('qc.sentFailBody', { id: job.orderCode })}
        </span>
        <div className="qc-sent-actions">
          <Link to="/tech" className="vh-btn vh-btn--primary vh-btn--md">{t('qc.toDash')}</Link>
          <Link to="/tech/qc" className="vh-btn vh-btn--ghost vh-btn--md">{t('qc.nextOrder')}</Link>
        </div>
      </section>,
    )
  }

  const tick = (itemId: string, on: boolean) => {
    const next = { ...ticked, [itemId]: on }
    setTicked(next)
    // The last box moves the technician straight on to the photos.
    if (on && all.every((i) => next[i.id])) setTab('photos')
  }

  const tabs = (
    <div className="sc-tabs qc-tabs" role="tablist" aria-label={t('qc.stepsAria')}>
      <button role="tab" aria-selected={tab === 'qc'} className={tab === 'qc' ? 'on' : ''} onClick={() => setTab('qc')}>
        {t('qc.tabChecklist')} <span className="vh-mono">{done}/{all.length}</span>
      </button>
      <button
        role="tab"
        aria-selected={tab === 'photos'}
        className={tab === 'photos' ? 'on' : ''}
        disabled={!qcDone}
        title={qcDone ? undefined : t('qc.finishFirst')}
        onClick={() => setTab('photos')}
      >
        {t('qc.tabPhotos')} <span className="vh-mono">{requiredDone}/{requiredTotal}</span>
      </button>
    </div>
  )

  const reference = (
    <section className="qc-ref">
      <h2 className="tp-h">{t('qc.compare')}</h2>
      <dl className="tp-opts">
        <div><dt>{t('qc.paperRow')}</dt><dd>{job.paperName ?? '-'}</dd></div>
        <div><dt>{t('po.pen')}</dt><dd>{job.penName ?? '-'}</dd></div>
        <div><dt>{t('qc.inkRow')}</dt><dd>{job.inkName ?? '-'}</dd></div>
        <div><dt>{t('qc.piecesRow')}</dt><dd>{job.quantity}</dd></div>
        <div><dt>{t('qc.robotRow')}</dt><dd>{job.robotCode}</dd></div>
      </dl>
      {job.approachNote && <p className="qc-text-ref">{job.approachNote}</p>}
    </section>
  )

  return shell(
    <>
      {confirm && (
        <div className="sc-modal" onClick={() => setConfirm(false)}>
          <div className="sc-modal-card" role="dialog" aria-modal="true" aria-labelledby="qc-confirm-h" onClick={(e) => e.stopPropagation()}>
            <span className="sc-modal-mark sc-modal-mark--accent" aria-hidden="true" />
            <div className="sc-modal-head">
              <h2 id="qc-confirm-h">{t('qc.confirmTitle', { name: t('qc.theCustomer') })}</h2>
              <p>{t('qc.confirmBodyJob', { photos: t(photos.length === 1 ? 'qc.photoOne' : 'qc.photoMany', { n: photos.length }) })}</p>
            </div>
            <div className="sc-modal-actions">
              <button className="vh-btn vh-btn--primary" disabled={busy} onClick={send}>{t('qc.sendCustomer')}</button>
              <button className="vh-btn vh-btn--ghost vh-btn--sm" onClick={() => setConfirm(false)}>{t('qc.notYet')}</button>
            </div>
          </div>
        </div>
      )}

      <div className="qc-tabbar">{tabs}</div>

      {tab === 'qc' ? (
        <div className="tp-grid">
          <div className="tp-main qc-main">
            <div className="qc-progress" role="progressbar" aria-valuemin={0} aria-valuemax={all.length} aria-valuenow={done} aria-label={t('qc.checked')}>
              <p>{t('qc.progress', { done, total: all.length })}</p>
              <div className="qc-segs" aria-hidden="true">
                {all.map((i) => <i key={i.id} className={ticked[i.id] ? 'on' : ''} />)}
              </div>
            </div>

            {groups.map((g) => {
              const n = g.items.filter((i) => ticked[i.id]).length
              return (
                <fieldset key={g.id} className="qc-group">
                  <legend>
                    <span>{g.title}</span>
                    <span className="vh-mono qc-count">{n}/{g.items.length}</span>
                  </legend>
                  <div className="qc-items">
                    {g.items.map((i) => (
                      <label key={i.id} className={`qc-item${ticked[i.id] ? ' on' : ''}`}>
                        <input type="checkbox" checked={!!ticked[i.id]} onChange={(e) => tick(i.id, e.target.checked)} />
                        <span className="qc-box" aria-hidden="true">{ticked[i.id] && <Check size={14} weight="bold" />}</span>
                        <span className="qc-text">
                          <b>{i.title}</b>
                          <span>{i.detail}</span>
                        </span>
                      </label>
                    ))}
                  </div>
                </fieldset>
              )
            })}

            <section className="qc-fail" aria-label={t('qc.ifWrong')}>
              {!failing ? (
                <button className="qc-link" onClick={() => setFailing(true)}>
                  <Warning size={18} /> {t('qc.reschedule')}
                </button>
              ) : (
                <div className="qc-fail-body">
                  <b>{t('qc.whatWrong')}</b>
                  <div className="sc-reasons">
                    {QC_FAIL_REASONS.map((r) => (
                      <button
                        key={r}
                        type="button"
                        className={`sc-reason${reasons.includes(r) ? ' on' : ''}`}
                        aria-pressed={reasons.includes(r)}
                        onClick={() => setReasons((rs) => (rs.includes(r) ? rs.filter((x) => x !== r) : [...rs, r]))}
                      >
                        {tn(r)}
                      </button>
                    ))}
                  </div>
                  <label className="qc-label">
                    {t('qc.scheduleNote')}
                    <textarea className="vh-textarea" rows={2} value={failNote} onChange={(e) => setFailNote(e.target.value)} />
                  </label>
                  {error && <p className="lg-error" role="alert">{errText(t, error)}</p>}
                  <div className="sc-row">
                    <button
                      className="vh-btn vh-btn--md qc-danger"
                      disabled={busy || !reasons.length}
                      onClick={() => void run(async () => {
                        // The backend keeps one note; the reasons are catalog names, stored in English like the rest.
                        const note = [reasons.join(', '), failNote.trim()].filter(Boolean).join(': ').slice(0, 500)
                        await failQc(job.id, note)
                        setSent('failed')
                      })}
                    >
                      <ArrowsClockwise size={18} /> {t('qc.rescheduleBtn')}
                    </button>
                    <button className="vh-btn vh-btn--ghost vh-btn--md" onClick={() => setFailing(false)}>{t('qc.cancel')}</button>
                  </div>
                </div>
              )}
            </section>
          </div>

          <aside className="tp-side" aria-label={t('qc.reference')}>
            {reference}
          </aside>
        </div>
      ) : (
        <div className="tp-grid">
          <div className="tp-main qc-main">
            <div className="qc-lede">
              <h2 className="tp-h">{t('qc.photosFor')}</h2>
              <p>{t('qc.photosBodyJob', { n: MIN_LONG_SIDE_PX })}</p>
            </div>

            <ul className="qc-slots qc-slots--big">
              {PHOTO_SLOTS.map((s) => {
                const list = kindPhotos(s.kind)
                return (
                  <li key={s.kind} className={s.required ? 'req' : ''}>
                    <input
                      ref={(el) => { inputs.current[s.kind] = el }}
                      type="file"
                      accept="image/jpeg,image/png"
                      capture="environment"
                      hidden
                      aria-label={t('qc.photoLabel', { label: tn(s.label) })}
                      onChange={(e) => {
                        addPhoto(s.kind, e.target.files?.[0])
                        e.target.value = ''
                      }}
                    />
                    <div className="qc-slot-head">
                      <b>{tn(s.label)}</b>
                      <span className={`qc-tag${s.required ? ' req' : ''}${passes(s.kind) ? ' ok' : ''}`}>
                        {passes(s.kind) ? t('qc.added') : s.required ? t('qc.required') : t('qc.optional')}
                      </span>
                    </div>
                    {list.map((p) => (
                      <div key={p.id} className="qc-photo">
                        <div className="qc-shot">
                          {p.url && <img src={p.url} alt={t('rs.photoAlt', { slot: tn(s.label), id: job.orderCode })} onError={brokenLink} />}
                          <div className="qc-shot-bar">
                            <span>{p.qc === 'FAIL' ? t('qc.markedFail') : p.qc === 'PASS' ? t('qc.markedPass') : tn(s.hint)}</span>
                            <button type="button" disabled={busy} aria-label={t('qc.removePhoto', { label: tn(s.label) })} onClick={() => drop(p)}>
                              <X size={16} />
                            </button>
                          </div>
                        </div>
                        {markFail?.id === p.id ? (
                          <div className="qc-fail-body">
                            <label className="qc-label">
                              {t('qc.failWhy')}
                              <textarea className="vh-textarea" rows={2} value={markFail.note} onChange={(e) => setMarkFail({ id: p.id, note: e.target.value })} />
                            </label>
                            <div className="sc-row">
                              <button className="vh-btn vh-btn--md qc-danger" disabled={busy || markFail.note.trim().length < 3} onClick={() => setQc(p, 'FAIL', markFail.note.trim())}>{t('qc.markFail')}</button>
                              <button className="vh-btn vh-btn--ghost vh-btn--md" onClick={() => setMarkFail(null)}>{t('qc.cancel')}</button>
                            </div>
                          </div>
                        ) : p.qc === 'PASS' ? (
                          <button type="button" className="qc-link" disabled={busy} onClick={() => setMarkFail({ id: p.id, note: '' })}>{t('qc.markFail')}</button>
                        ) : (
                          <div className="qc-fail-body">
                            {p.note && <span>{p.note}</span>}
                            <button type="button" className="vh-btn vh-btn--ghost vh-btn--sm" disabled={busy} onClick={() => setQc(p, 'PASS')}>{t('qc.markPass')}</button>
                          </div>
                        )}
                      </div>
                    ))}
                    {!list.length && (
                      <button type="button" className={`qc-empty${s.required ? ' req' : ''}`} disabled={busy || photos.length >= MAX_PHOTOS} onClick={() => inputs.current[s.kind]?.click()}>
                        <Camera size={28} />
                        <span className="qc-empty-text">
                          <b>{busy ? t('qc.uploading') : t('qc.takePhoto')}</b>
                          <span>{tn(s.hint)}</span>
                        </span>
                      </button>
                    )}
                  </li>
                )
              })}
            </ul>
            {error && <p className="lg-error" role="alert">{errText(t, error)}</p>}
          </div>

          <aside className="tp-side" aria-label={t('qc.send')}>
            <section>
              <h2 className="tp-h">{t('qc.checklist')}</h2>
              <p className="qc-done-line"><Check size={18} weight="bold" /> {t('qc.passed', { n: all.length })}</p>
              <button className="qc-link qc-back" onClick={() => setTab('qc')}>
                <ArrowLeft size={16} /> {t('qc.backList')}
              </button>
            </section>
            {reference}
            <section aria-label={t('qc.send')}>
              <p className="qc-need" aria-live="polite">
                {ready
                  ? t('qc.allIn')
                  : blocked
                    ? t('qc.fixPhotos')
                    : t('qc.addPhotos', { list: missing.map((s) => tn(s.label).toLowerCase()).join(t('qc.and')), s: missing.length > 1 ? 's' : '' })}
              </p>
              <button className="vh-btn vh-btn--primary vh-btn--md qc-send" disabled={!ready || busy} onClick={() => setConfirm(true)}>
                <PaperPlaneTilt size={18} weight="bold" /> {t('qc.sendCustomer')}
              </button>
            </section>
          </aside>
        </div>
      )}
    </>,
  )
}
