import { useRef, useState } from 'react'
import { useAsync } from '../../hooks/useAsync'
import { useT } from '../../i18n'
import { failJobQc, jobPhotos, photosReady, registerPhoto, removePhoto, requestPhotoUpload, setPhotoQc, submitPhotos, uploadPhotoBinary, type PhotoKind, type ProductPhoto, type QcResult, type TechJobDetail } from '../../services/technician'
import JobFeedback from './JobFeedback'
import type { TechRun } from './flow'

async function validateImage(file: File) {
  if (!['image/jpeg', 'image/png'].includes(file.type) || file.size <= 0) throw new Error('td.flow.invalidPhoto')
  const url = URL.createObjectURL(file)
  try {
    const image = new Image()
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve()
      image.onerror = () => reject(new Error('td.flow.invalidPhoto'))
      image.src = url
    })
    if (Math.max(image.naturalWidth, image.naturalHeight) < 1280) throw new Error('td.flow.photoTooSmall')
  } finally { URL.revokeObjectURL(url) }
}

export default function JobPhotos({ job, disabled, run, revision }: { job: TechJobDetail; disabled: boolean; run: TechRun; revision: number }) {
  const t = useT()
  const q = useAsync(() => jobPhotos(job.id), [job.id, revision, job.status], 30000)
  const photos = q.data ?? []
  const [file, setFile] = useState<File | null>(null)
  const [kind, setKind] = useState<PhotoKind>('OVERALL')
  const [progress, setProgress] = useState<number | null>(null)
  const [pending, setPending] = useState<{ key: string; kind: PhotoKind } | null>(null)
  const [failNote, setFailNote] = useState('')
  const fileInput = useRef<HTMLInputElement>(null)
  const editable = job.status === 'WRITTEN'
  const blocked = disabled || !!q.error || !q.data || q.loading
  const clear = () => { setFile(null); setPending(null); setProgress(null); if (fileInput.current) fileInput.current.value = '' }
  const upload = () => run(async () => {
    if (!file) return
    await validateImage(file)
    setProgress(0)
    const ticket = await requestPhotoUpload(job.id, file)
    await uploadPhotoBinary(ticket, file, setProgress)
    setPending({ key: ticket.photo_key, kind })
    // Retain this key if registration fails; retry registration without a new upload or duplicate photo.
    await registerPhoto(job.id, ticket.photo_key, kind)
    clear()
  })
  return <section className="panel">
    <div className="ph"><h2>{t('td.flow.photos')}</h2><span className="sub">{photos.length}/10</span></div>
    <p className="sub">{t('td.flow.photoHelp')}</p>
    <JobFeedback loading={q.loading && !q.data} error={q.error} retry={q.reload} />
    {editable && <form className="tech-form" onSubmit={(e) => { e.preventDefault(); if (file && !pending) void upload() }}>
      <fieldset disabled={blocked}>
        <legend>{t('td.flow.upload')}</legend>
        <label className="vh-label">{t('td.flow.photoKind')}<select className="vh-select" value={kind} disabled={!!pending} onChange={(e) => setKind(e.target.value as PhotoKind)}>{(['OVERALL', 'CLOSE_UP', 'OTHER'] as const).map((v) => <option key={v} value={v}>{t(`td.flow.photo.${v}`)}</option>)}</select></label>
        <label className="vh-label">{t('td.flow.file')}<input ref={fileInput} type="file" accept="image/jpeg,image/png" disabled={!!pending || photos.length >= 10} onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></label>
        {progress !== null && <div><progress max={100} value={progress} aria-label={t('td.flow.uploadProgress')} /><span className="sub">{progress}%</span></div>}
        {pending ? <>
          <p className="wk-warn">{t('td.flow.registrationPending')}</p>
          <button type="button" className="sd-btn" onClick={() => void run(async () => { await registerPhoto(job.id, pending.key, pending.kind); clear() })}>{t('td.flow.retryRegister')}</button>
          <button type="button" className="sd-btn" onClick={clear}>{t('td.flow.discardUpload')}</button>
        </> : <button type="submit" className="sd-btn" disabled={!file || photos.length >= 10}>{t('td.flow.upload')}</button>}
      </fieldset>
    </form>}
    <div className="tech-photo-grid">{photos.map((p) => <PhotoEditor key={p.id} photo={p} jobId={job.id} editable={editable} disabled={blocked} run={run} refresh={q.reload} />)}</div>
    {q.data && !q.error && !photos.length && <p className="sub">{t('td.flow.noPhotos')}</p>}
    {editable && <>
      <p className="wk-warn">{t('td.flow.photoGate')}</p>
      <button type="button" className="sd-btn" disabled={blocked || !!pending || !photosReady(photos)} onClick={() => void run(() => submitPhotos(job.id), t('td.flow.confirmSubmitPhotos'))}>{t('td.flow.submitPhotos')}</button>
      <form className="tech-form" onSubmit={(e) => { e.preventDefault(); if (failNote.trim().length >= 3) void run(() => failJobQc(job.id, failNote), t('td.flow.confirmQcFail')) }}>
        <fieldset disabled={blocked}>
          <legend>{t('td.flow.qcFail')}</legend><p className="sub">{t('td.flow.qcFailHelp')}</p>
          <label className="vh-label">{t('td.flow.reason')}<textarea className="vh-textarea" minLength={3} maxLength={500} required value={failNote} onChange={(e) => setFailNote(e.target.value)} /></label>
          <button type="submit" className="sd-btn" disabled={failNote.trim().length < 3}>{t('td.flow.qcFail')}</button>
        </fieldset>
      </form>
    </>}
    {job.status === 'PHOTO_UPLOADED' && <p role="status" className="wk-warn">{t('td.flow.photosSubmitted')}</p>}
  </section>
}

function PhotoEditor({ photo: p, jobId, editable, disabled, run, refresh }: {
  photo: ProductPhoto; jobId: number; editable: boolean; disabled: boolean; run: TechRun; refresh: () => unknown
}) {
  const t = useT()
  const [qc, setQc] = useState<QcResult | ''>(p.qc_result ?? '')
  const [note, setNote] = useState(p.qc_note ?? '')
  const [failedUrl, setFailedUrl] = useState<string | null>(null)
  return <article className="tech-photo">
    {p.url && failedUrl !== p.url ? <a href={p.url} target="_blank" rel="noreferrer"><img src={p.url} alt={t(`td.flow.photo.${p.kind}`)} onError={() => setFailedUrl(p.url)} /></a>
      : <div className="tech-photo-missing"><p>{t('td.flow.photoLinkExpired')}</p><button type="button" className="sd-btn" onClick={() => { setFailedUrl(null); void refresh() }}>{t('td.api.reload')}</button></div>}
    <b>{t(`td.flow.photo.${p.kind}`)}</b>
    <span className={`chip ${p.qc_result === 'PASS' ? 'good' : 'warn'}`}>{t(p.qc_result === 'PASS' ? 'td.api.passed' : p.qc_result === 'FAIL' ? 'td.api.notPassed' : 'td.api.notRecorded')}</span>
    {editable ? <form className="tech-form" onSubmit={(e) => { e.preventDefault(); if (qc) void run(() => setPhotoQc(jobId, p.id, qc, note)) }}>
      <fieldset disabled={disabled}>
        <legend>{t('td.flow.photoQc')}</legend>
        <label className="vh-label">{t('td.flow.result')}<select className="vh-select" required value={qc} onChange={(e) => setQc(e.target.value as QcResult | '')}><option value="">{t('td.flow.choose')}</option><option value="PASS">{t('td.api.passed')}</option><option value="FAIL">{t('td.api.notPassed')}</option></select></label>
        <label className="vh-label">{t('td.flow.note')}<textarea className="vh-textarea" maxLength={500} required={qc === 'FAIL'} minLength={qc === 'FAIL' ? 3 : undefined} value={note} onChange={(e) => setNote(e.target.value)} /></label>
        <button type="submit" className="sd-btn" disabled={!qc || (qc === 'FAIL' && note.trim().length < 3)}>{t('td.flow.saveQc')}</button>
        <button type="button" className="sd-btn" onClick={() => void run(() => removePhoto(jobId, p.id), t('td.flow.confirmDeletePhoto'))}>{t('td.flow.remove')}</button>
      </fieldset>
    </form> : <>{p.qc_note && <p className="wk-text">{p.qc_note}</p>}</>}
  </article>
}
