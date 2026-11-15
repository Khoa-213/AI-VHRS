import { CheckCircle, Image as ImageIcon, WarningCircle } from '@phosphor-icons/react'
import { useState } from 'react'
import { useAsync } from '../../hooks/useAsync'
import { useLocale, useT } from '../../i18n'
import { errText, orderErrorKey } from '../../services/orders'
import { orderProductPhotos, type WorkOrder } from '../../services/workshop'
import './staff-extras.css'

/** Finished-product photos of the order's jobs and their QC verdict (`GET /workshop/orders/{id}/product-photos`), read only. */
export default function ProductPhotosPanel({ order }: { order: WorkOrder }) {
  const t = useT()
  const locale = useLocale()
  const q = useAsync(() => orderProductPhotos(order.id), [order.id, order.status])
  const [broken, setBroken] = useState<Set<number>>(new Set())
  const photos = q.data ?? []
  const reload = () => { setBroken(new Set()); void q.reload() }

  return (
    <section className="wk-block" aria-labelledby={`stp-h-${order.id}`}>
      <div className="stx-head">
        <h3 id={`stp-h-${order.id}`}>{t('stp.title')}</h3>
        {q.data && <span className="sd-sub">{t('stp.count', { n: photos.length })}</span>}
        <button type="button" className="vh-btn vh-btn--ghost vh-btn--sm" disabled={q.loading} onClick={reload}>{t('td.api.reload')}</button>
      </div>
      {q.loading && !q.data && <p className="sd-sub" role="status">{t('co.loading')}</p>}
      {q.error != null && <p className="lg-error" role="alert">{errText(t, orderErrorKey(q.error))}</p>}
      {q.data && !q.error && !photos.length && <p className="sd-sub">{t('stp.empty')}</p>}
      {photos.length > 0 && (
        <ul className="stx-photos">
          {photos.map((p) => (
            <li key={p.id} className="stx-photo">
              {p.url && !broken.has(p.id)
                ? <a href={p.url} target="_blank" rel="noreferrer"><img src={p.url} alt={t('stp.alt', { kind: t(`td.flow.photo.${p.kind}`), job: p.jobId })} loading="lazy" onError={() => setBroken((s) => new Set(s).add(p.id))} /></a>
                : <div className="stx-photo-missing"><ImageIcon size={22} aria-hidden /><span>{t('td.flow.photoLinkExpired')}</span></div>}
              <div className="stx-photo-meta">
                <b>{t(`td.flow.photo.${p.kind}`)}</b>
                <span className={`stx-qc${p.qcResult === 'PASS' ? ' ok' : p.qcResult === 'FAIL' ? ' bad' : ''}`}>
                  {p.qcResult === 'PASS' ? <CheckCircle size={15} aria-hidden /> : <WarningCircle size={15} aria-hidden />}
                  {t(p.qcResult === 'PASS' ? 'td.api.passed' : p.qcResult === 'FAIL' ? 'td.api.notPassed' : 'td.api.notRecorded')}
                </span>
              </div>
              <span className="sd-sub">{t('stp.job', { id: p.jobId, status: t(`js.${p.jobStatus}`) })}</span>
              <span className="sd-sub">{new Date(p.createdAt).toLocaleString(locale, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</span>
              {p.qcNote && <p className="wk-text">{p.qcNote}</p>}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
