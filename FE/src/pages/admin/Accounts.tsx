import AdminSelect from '../../components/admin/AdminSelect'
import { UserCirclePlus } from '@phosphor-icons/react'
import { useMemo, useState } from 'react'
import AdminFrame from '../../components/admin/AdminFrame'
import { Card, Chip, type Tone } from '../../components/admin/AdminViz'
import { useAsync } from '../../hooks/useAsync'
import { useDebounced } from '../../hooks/useDebounced'
import { useT } from '../../i18n'
import {
  INTERNAL_ROLES, ROLES, STATUSES, allAccounts, createAccount, updateAccount, type AccountStatus, type AdminAccount,
} from '../../services/admin'
import { PASSWORD_RULE, PHONE_RULE, cleanPhone } from '../../services/auth'
import { errDetails, errText, orderErrorKey } from '../../services/orders'
import { useUser } from '../../store/store'

const PAGE_SIZE = 12
const EMAIL = /^\S+@\S+\.\S+$/
const STATUS_TONE: Record<AccountStatus, Tone> = { ACTIVE: 'good', LOCKED: 'warn', DISABLED: 'mute' }

const initialParams = () => {
  const p = new URLSearchParams(window.location.search)
  const s = p.get('status')
  return { creating: p.get('new') === '1', status: STATUSES.find((x) => x === s) ?? '', q: p.get('q') ?? '' }
}

/**
 * Admin only. One list, one search box and two filters. Each person has a single "Manage" button that opens what can be changed
 * (status, role). New internal accounts are added from the button at the top (customers register themselves, BR-01).
 */
export default function Accounts() {
  const t = useT()
  const me = useUser()
  const start = useMemo(initialParams, [])
  const [q, setQ] = useState(start.q)
  const [role, setRole] = useState('')
  const [status, setStatus] = useState<string>(start.status)
  const [page, setPage] = useState(1)
  const search = useDebounced(q, 350)
  const [open, setOpen] = useState<number | null>(null)
  const [creating, setCreating] = useState(start.creating)
  const [notice, setNotice] = useState('')

  // Every match is loaded and paged here (the backend pages oldest first); the role filter is applied here too.
  const list = useAsync(() => allAccounts({ q: search, status }), [search, status])
  const all = (list.data ?? []).filter((a) => !role || a.role === role)
  const pages = Math.max(1, Math.ceil(all.length / PAGE_SIZE))
  const shown = all.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  const done = (msg: string) => {
    setNotice(msg)
    setOpen(null)
    setCreating(false)
    void list.reload()
  }

  return (
    <AdminFrame
      active="accounts"
      title={t('ad.acc.title')}
      actions={!creating && (
        <button type="button" className="adm-btn adm-btn--solid" onClick={() => { setCreating(true); setNotice('') }}>
          <UserCirclePlus size={20} aria-hidden />{t('adm.acc.add')}
        </button>
      )}
    >
      {creating && (
        <Card title={t('adm.acc.add')} sub={t('adm.acc.addHint')}>
          <CreateForm onDone={() => done(t('adm.acc.createdNext'))} onCancel={() => setCreating(false)} />
        </Card>
      )}

      <Card title={t('ad.acc.title')} sub={t('ad.acc.count', { n: all.length })}>
        <div className="adm-toolbar">
          <input className="adm-input adm-toolbar-search" type="search" aria-label={t('ad.acc.search')} value={q} placeholder={t('ad.acc.searchPh')} onChange={(e) => { setQ(e.target.value); setPage(1) }} />
          <AdminSelect label={t('ad.acc.role')} value={role} onChange={(value) => { setRole(value); setPage(1) }} options={[{ value: '', label: t('ad.acc.allRoles') }, ...ROLES.map((r) => ({ value: r, label: t(`ad.role.${r}`) }))]} />
          <AdminSelect label={t('ad.acc.status')} value={status} onChange={(value) => { setStatus(value); setPage(1) }} options={[{ value: '', label: t('ad.acc.allStatus') }, ...STATUSES.map((r) => ({ value: r, label: t(`ad.status.${r}`) }))]} />
        </div>

        {notice && <p className="adm-note" role="status">{notice}</p>}
        {!!list.error && <p className="adm-error" role="alert">{errText(t, orderErrorKey(list.error))}</p>}
        {list.loading && !list.data && <p className="adm-fine" role="status">{t('co.loading')}</p>}

        <div className="adm-people">
          {shown.map((a) => (
            <Person key={a.id} a={a} self={a.id === me?.id} open={open === a.id} onToggle={() => setOpen(open === a.id ? null : a.id)} onDone={() => done(t('ad.acc.saved'))} />
          ))}
          {list.data && !shown.length && <p className="adm-fine">{t('adm.acc.emptyBody')}</p>}
        </div>

        {list.data && all.length > PAGE_SIZE && (
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

const initial = (name: string) => name.trim().charAt(0).toUpperCase() || '?'

function Person({ a, self, open, onToggle, onDone }: { a: AdminAccount; self: boolean; open: boolean; onToggle: () => void; onDone: () => void }) {
  const t = useT()
  return (
    <div className={`adm-person${a.status === 'ACTIVE' ? '' : ' off'}`}>
      <div className="adm-person-main">
        <div className="adm-who">
          <span className="adm-avatar" aria-hidden>{initial(a.name)}</span>
          <div className="adm-who-text">
            <b>{a.name}{self ? ` (${t('ad.acc.you')})` : ''}</b>
            <span>{a.email}</span>
          </div>
        </div>
        <div className="adm-person-meta">
          <span>{t(`ad.role.${a.role}`)}</span>
          <Chip tone={STATUS_TONE[a.status] ?? 'mute'}>{t(`ad.status.${a.status}`)}</Chip>
        </div>
        <div className="adm-person-act">
          <button type="button" className="adm-btn adm-btn--line adm-btn--sm" aria-expanded={open} onClick={onToggle}>{open ? t('ov.back') : t('adm.acc.edit')}</button>
        </div>
      </div>
      {open && <EditForm a={a} self={self} onDone={onDone} />}
    </div>
  )
}

function EditForm({ a, self, onDone }: { a: AdminAccount; self: boolean; onDone: () => void }) {
  const t = useT()
  const [status, setStatus] = useState<AccountStatus>(a.status)
  const [role, setRole] = useState(a.role)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const changed = status !== a.status || role !== a.role

  const save = async () => {
    if (busy || !changed) return
    setBusy(true)
    setErr('')
    try {
      await updateAccount(a.id, {
        ...(status !== a.status ? { status } : {}),
        ...(role !== a.role ? { role } : {}),
        ...(reason.trim() ? { reason: reason.trim() } : {}),
      })
      onDone()
    } catch (e) {
      setErr(orderErrorKey(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="adm-edit">
      <div className="adm-formgrid">
        <fieldset className="adm-fieldset" disabled={self}>
          <legend>{t('ad.acc.status')}</legend>
          <div className="adm-seg-radio">
            {STATUSES.map((s) => (
              <label key={s}><input type="radio" name={`st-${a.id}`} checked={status === s} onChange={() => setStatus(s)} />{t(`ad.status.${s}`)}</label>
            ))}
          </div>
        </fieldset>
        <label className="adm-field">
          {t('ad.acc.role')}
          <AdminSelect label={t('ad.acc.role')} value={role} disabled={self || busy} onChange={setRole} options={ROLES.map((r) => ({ value: r, label: t(`ad.role.${r}`) }))} />
        </label>
        <label className="adm-field">
          {t('ad.acc.reason')}
          <input value={reason} maxLength={500} placeholder={t('ad.acc.reasonPh')} onChange={(e) => setReason(e.target.value)} />
        </label>
      </div>
      {status !== a.status && <p className="adm-consequence">{t(`adm.acc.hint.${status}`)}</p>}
      {self && <p className="adm-consequence">{t('ad.acc.selfWarn')}</p>}
      {err && <p className="adm-error" role="alert">{errText(t, err)}</p>}
      <div className="adm-actions">
        <button type="button" className="adm-btn adm-btn--solid" disabled={busy || !changed || self} onClick={() => void save()}>{t('ad.acc.save')}</button>
      </div>
    </div>
  )
}

function CreateForm({ onDone, onCancel }: { onDone: () => void; onCancel: () => void }) {
  const t = useT()
  const [f, setF] = useState({ email: '', name: '', phone: '', password: '', role: INTERNAL_ROLES[0] as string })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [lines, setLines] = useState<string[]>([])
  const phone = cleanPhone(f.phone)
  const ok = !!f.name.trim() && EMAIL.test(f.email.trim()) && PASSWORD_RULE.test(f.password) && (!phone || PHONE_RULE.test(phone))

  const submit = async () => {
    if (busy || !ok) return
    setBusy(true)
    setErr('')
    setLines([])
    try {
      await createAccount({ email: f.email.trim(), password: f.password, full_name: f.name.trim(), role: f.role, ...(phone ? { phone } : {}) })
      setF({ email: '', name: '', phone: '', password: '', role: INTERNAL_ROLES[0] })
      onDone()
    } catch (e) {
      setErr(orderErrorKey(e))
      setLines(errDetails(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="adm-edit" style={{ borderTop: 'none', paddingTop: 0 }} onSubmit={(e) => { e.preventDefault(); void submit() }}>
      <div className="adm-formgrid">
        <label className="adm-field">{t('ad.acc.name')}<input maxLength={150} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></label>
        <label className="adm-field">{t('ad.acc.email')}<input type="email" autoComplete="off" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></label>
        <label className="adm-field">
          {t('ad.acc.password')}
          <input type="password" autoComplete="new-password" maxLength={72} value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
          <small>{t('reg.passwordHelp')}</small>
        </label>
        <label className="adm-field">
          {t('ad.acc.role')}
          <AdminSelect label={t('ad.acc.role')} value={f.role} disabled={busy} onChange={(value) => setF({ ...f, role: value })} options={INTERNAL_ROLES.map((r) => ({ value: r, label: t(`ad.role.${r}`) }))} />
          <small>{t(`adm.acc.roleHelp.${f.role}`)}</small>
        </label>
        <label className="adm-field">{t('ad.acc.phone')}<input inputMode="tel" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} /><small>{t('adm.acc.optional')}</small></label>
      </div>
      {err && <p className="adm-error" role="alert">{errText(t, err)}{lines.length ? `: ${lines.join('; ')}` : ''}</p>}
      <div className="adm-actions">
        <button className="adm-btn adm-btn--solid" type="submit" disabled={busy || !ok}>{t('ad.acc.create')}</button>
        <button className="adm-btn adm-btn--line" type="button" disabled={busy} onClick={onCancel}>{t('ov.back')}</button>
      </div>
    </form>
  )
}
