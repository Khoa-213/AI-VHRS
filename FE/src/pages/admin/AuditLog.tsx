import AdminSelect from '../../components/admin/AdminSelect'
import {
  CreditCard, FileText, Gear, Package, Robot, Scroll, Users, Wrench,
} from '@phosphor-icons/react'
import { useState, type ReactNode } from 'react'
import AdminFrame from '../../components/admin/AdminFrame'
import { Card } from '../../components/admin/AdminViz'
import { useAsync } from '../../hooks/useAsync'
import { useLocale, useT } from '../../i18n'
import { listAudit, type AuditEntry } from '../../services/admin'
import { errText, orderErrorKey } from '../../services/orders'
import { AUDIT_KINDS, auditKind, auditLabel } from '../../utils/audit'

const PAGE_SIZE = 20

const KIND_ICON: Record<string, ReactNode> = {
  account: <Users size={18} aria-hidden />,
  order: <Package size={18} aria-hidden />,
  payment: <CreditCard size={18} aria-hidden />,
  quotation: <FileText size={18} aria-hidden />,
  production_job: <Wrench size={18} aria-hidden />,
  robot: <Robot size={18} aria-hidden />,
  system_setting: <Gear size={18} aria-hidden />,
}

/** "5 minutes ago" in the language of the page; older than a week falls back to the date. */
function ago(iso: string, locale: string): string {
  const diff = (new Date(iso).getTime() - Date.now()) / 1000
  const abs = Math.abs(diff)
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' })
  if (abs < 60) return rtf.format(Math.round(diff), 'second')
  if (abs < 3600) return rtf.format(Math.round(diff / 60), 'minute')
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), 'hour')
  if (abs < 7 * 86400) return rtf.format(Math.round(diff / 86400), 'day')
  return new Date(iso).toLocaleDateString(locale, { dateStyle: 'medium' })
}

/**
 * Admin only: the activity log (UC-51) as one list. Narrow it by kind of record, or by the number of a record (an order, a
 * payment). Each line says what happened, to what and who did it, and opens to the reason and the before and after values.
 */
export default function AuditLog() {
  const t = useT()
  const locale = useLocale()
  const [kind, setKind] = useState('')
  const [entityId, setEntityId] = useState('')
  const [page, setPage] = useState(1)
  const [open, setOpen] = useState<number | null>(null)

  const list = useAsync(
    () => listAudit({ entityType: kind, entityId: entityId ? Number(entityId) : undefined, page, pageSize: PAGE_SIZE }),
    [kind, entityId, page],
  )
  const pages = Math.max(1, Math.ceil((list.data?.total ?? 0) / PAGE_SIZE))

  return (
    <AdminFrame active="audit" title={t('ad.au.title')}>
      <Card title={t('adm.au.feed')} sub={t('ad.au.count', { n: list.data?.total ?? 0 })}>
        <div className="adm-toolbar">
          <AdminSelect label={t('adm.au.kind')} value={kind} onChange={(value) => { setKind(value); setPage(1); setOpen(null) }} options={[{ value: '', label: t('adm.au.allKinds') }, ...AUDIT_KINDS.map((k) => ({ value: k, label: auditKind(t, k) }))]} />
          <input
            className="adm-input"
            inputMode="numeric"
            aria-label={t('ad.au.entityId')}
            placeholder={t('adm.au.idPh')}
            value={entityId}
            onChange={(e) => { setEntityId(e.target.value.replace(/\D/g, '').slice(0, 10)); setPage(1); setOpen(null) }}
          />
        </div>

        {!!list.error && <p className="adm-error" role="alert">{errText(t, orderErrorKey(list.error))}</p>}
        {list.loading && !list.data && <p className="adm-fine" role="status">{t('co.loading')}</p>}
        <div className="adm-feed">
          {(list.data?.items ?? []).map((e) => <Event key={e.id} e={e} locale={locale} open={open === e.id} onToggle={() => setOpen(open === e.id ? null : e.id)} />)}
        </div>
        {list.data && !list.data.items.length && <p className="adm-fine">{t(kind || entityId ? 'adm.au.emptyFiltered' : 'ad.au.empty')}</p>}
        {list.data && list.data.total > PAGE_SIZE && (
          <div className="adm-pager">
            <span />
            <div>
              <button type="button" className="adm-btn adm-btn--line adm-btn--sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>{t('ad.prev')}</button>
              <span>{t('ad.page', { page, pages })}</span>
              <button type="button" className="adm-btn adm-btn--line adm-btn--sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>{t('ad.next')}</button>
            </div>
          </div>
        )}
      </Card>
    </AdminFrame>
  )
}

function Event({ e, locale, open, onToggle }: { e: AuditEntry; locale: string; open: boolean; onToggle: () => void }) {
  const t = useT()
  const has = e.oldValue || e.newValue || e.reason
  return (
    <div className="adm-event">
      <div className="adm-event-main">
        <span className="adm-event-ico">{KIND_ICON[e.entityType ?? ''] ?? <Scroll size={18} aria-hidden />}</span>
        <div className="adm-event-text">
          <b>{auditLabel(t, e.action)}</b>
          <span>
            {auditKind(t, e.entityType)}{e.entityId !== null ? ` #${e.entityId}` : ''} · {e.actorId !== null ? t('adm.au.byUser', { id: e.actorId }) : t('ad.au.system')}
          </span>
        </div>
        <div className="adm-event-side">
          <time className="adm-event-when" dateTime={e.createdAt} title={new Date(e.createdAt).toLocaleString(locale, { dateStyle: 'medium', timeStyle: 'medium' })}>{ago(e.createdAt, locale)}</time>
          {has && <button type="button" className="adm-link" aria-expanded={open} onClick={onToggle}>{open ? t('ov.back') : t('ad.au.details')}</button>}
        </div>
      </div>
      {open && (
        <>
          {e.reason && <p className="adm-reason"><b>{t('ad.au.reason')}:</b> {e.reason}</p>}
          <div className="adm-diff">
            {e.oldValue && <div><h4>{t('ad.au.before')}</h4><pre className="adm-json">{JSON.stringify(e.oldValue, null, 2)}</pre></div>}
            {e.newValue && <div><h4>{t('ad.au.after')}</h4><pre className="adm-json">{JSON.stringify(e.newValue, null, 2)}</pre></div>}
          </div>
        </>
      )}
    </div>
  )
}
