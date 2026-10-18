import { useState } from 'react'
import Shell from '../../components/ws/Shell'
import { useAsync } from '../../hooks/useAsync'
import { useLocale, useT } from '../../i18n'
import { listAudit, type AuditEntry } from '../../services/admin'
import { errText, orderErrorKey } from '../../services/orders'
import './admin.css'

const PAGE_SIZE = 20
const intOnly = (v: string) => v.replace(/\D/g, '').slice(0, 10)

/** Admin only: the system activity log (UC-51). Entries are read only; filter by who did it, what, and on which record. */
export default function AuditLog() {
  const t = useT()
  const locale = useLocale()
  const blank = { actor: '', action: '', entityType: '', entityId: '' }
  const [draft, setDraft] = useState(blank)
  const [applied, setApplied] = useState(blank)
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState<number | null>(null)

  const list = useAsync(
    () => listAudit({
      actorId: applied.actor ? Number(applied.actor) : undefined,
      action: applied.action,
      entityType: applied.entityType,
      entityId: applied.entityId ? Number(applied.entityId) : undefined,
      page,
      pageSize: PAGE_SIZE,
    }),
    [applied, page],
  )
  const pages = Math.max(1, Math.ceil((list.data?.total ?? 0) / PAGE_SIZE))
  const apply = () => {
    setPage(1)
    setApplied(draft)
  }
  const clear = () => {
    setDraft(blank)
    setApplied(blank)
    setPage(1)
  }

  return (
    <Shell area="admin" active="audit" title={t('ad.au.title')} lede={t('ad.au.lede')}>
      <div className="wk-page">
        <section className="wk-block" aria-label={t('ad.au.title')}>
          <form className="ad-bar" onSubmit={(e) => { e.preventDefault(); apply() }}>
            <label className="vh-label wk-grow">{t('ad.au.action')}<input className="vh-input" value={draft.action} onChange={(e) => setDraft({ ...draft, action: e.target.value })} /></label>
            <label className="vh-label">{t('ad.au.entityType')}<input className="vh-input" value={draft.entityType} onChange={(e) => setDraft({ ...draft, entityType: e.target.value })} /></label>
            <label className="vh-label">{t('ad.au.entityId')}<input className="vh-input" inputMode="numeric" value={draft.entityId} onChange={(e) => setDraft({ ...draft, entityId: intOnly(e.target.value) })} /></label>
            <label className="vh-label">{t('ad.au.actor')}<input className="vh-input" inputMode="numeric" value={draft.actor} onChange={(e) => setDraft({ ...draft, actor: intOnly(e.target.value) })} /></label>
            <button className="vh-btn vh-btn--primary vh-btn--md" type="submit">{t('ad.au.apply')}</button>
            <button className="vh-btn vh-btn--ghost vh-btn--md" type="button" onClick={clear}>{t('ad.au.clear')}</button>
          </form>

          {!!list.error && <p className="lg-error" role="alert">{errText(t, orderErrorKey(list.error))}</p>}
          {list.loading && !list.data && <p className="sub" role="status">{t('co.loading')}</p>}

          {list.data && (
            <div className="ad-scroll">
              <table className="ad-table">
                <thead>
                  <tr>
                    <th scope="col">{t('ad.au.when')}</th>
                    <th scope="col">{t('ad.au.action')}</th>
                    <th scope="col">{t('ad.au.record')}</th>
                    <th scope="col">{t('ad.au.actor')}</th>
                    <th scope="col"><span className="ad-sr">{t('ad.au.details')}</span></th>
                  </tr>
                </thead>
                <tbody>
                  {list.data.items.map((e) => <Row key={e.id} e={e} locale={locale} open={open === e.id} onToggle={() => setOpen(open === e.id ? null : e.id)} />)}
                </tbody>
              </table>
              {!list.data.items.length && <p className="sub">{t('ad.au.empty')}</p>}
            </div>
          )}

          {list.data && (
            <div className="ad-pager">
              <span className="sub">{t('ad.au.count', { n: list.data.total })}</span>
              <div>
                <button className="vh-btn vh-btn--ghost vh-btn--sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>{t('ad.prev')}</button>
                <span className="sub">{t('ad.page', { page, pages })}</span>
                <button className="vh-btn vh-btn--ghost vh-btn--sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>{t('ad.next')}</button>
              </div>
            </div>
          )}
        </section>
      </div>
    </Shell>
  )
}

function Row({ e, locale, open, onToggle }: { e: AuditEntry; locale: string; open: boolean; onToggle: () => void }) {
  const t = useT()
  const has = e.oldValue || e.newValue || e.reason
  return (
    <>
      <tr>
        <td className="sub" style={{ whiteSpace: 'nowrap' }}>{new Date(e.createdAt).toLocaleString(locale, { dateStyle: 'medium', timeStyle: 'medium' })}</td>
        <td><b className="mono">{e.action}</b></td>
        <td>{[e.entityType, e.entityId !== null ? `#${e.entityId}` : null].filter(Boolean).join(' ') || '–'}</td>
        <td>{e.actorId !== null ? `#${e.actorId}` : t('ad.au.system')}</td>
        <td>{has && <button className="vh-btn vh-btn--ghost vh-btn--sm" aria-expanded={open} onClick={onToggle}>{open ? t('ov.back') : t('ad.au.details')}</button>}</td>
      </tr>
      {open && (
        <tr className="ad-edit">
          <td colSpan={5}>
            {e.reason && <p><b>{t('ad.au.reason')}:</b> {e.reason}</p>}
            <div className="ad-diff">
              {e.oldValue && <div><h4>{t('ad.au.before')}</h4><pre className="ad-json">{JSON.stringify(e.oldValue, null, 2)}</pre></div>}
              {e.newValue && <div><h4>{t('ad.au.after')}</h4><pre className="ad-json">{JSON.stringify(e.newValue, null, 2)}</pre></div>}
            </div>
          </td>
        </tr>
      )}
    </>
  )
}
