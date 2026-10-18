import { useState } from 'react'
import Shell from '../../components/ws/Shell'
import { avatarTone, initials } from '../../components/ws/parts'
import { useAsync } from '../../hooks/useAsync'
import { useDebounced } from '../../hooks/useDebounced'
import { useLocale, useT } from '../../i18n'
import {
  INTERNAL_ROLES, ROLES, STATUSES, createAccount, listAccounts, updateAccount, type AccountStatus, type AdminAccount,
} from '../../services/admin'
import { PASSWORD_RULE, PHONE_RULE, cleanPhone } from '../../services/auth'
import { errDetails, errText, orderErrorKey } from '../../services/orders'
import { useUser } from '../../store/store'
import './admin.css'

const PAGE_SIZE = 15
const EMAIL = /^\S+@\S+\.\S+$/
const STATUS_CHIP: Record<AccountStatus, string> = { ACTIVE: 'good', LOCKED: 'warn', DISABLED: 'bad' }

/** Admin only: find accounts, create internal ones (BR-01), lock or unlock them and change a role. Every change carries a reason for the audit log. */
export default function Accounts() {
  const t = useT()
  const locale = useLocale()
  const me = useUser()
  const [q, setQ] = useState('')
  const [role, setRole] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const search = useDebounced(q, 350)
  const [open, setOpen] = useState<number | null>(null)
  const [notice, setNotice] = useState('')

  const list = useAsync(() => listAccounts({ q: search, role, status, page, pageSize: PAGE_SIZE }), [search, role, status, page])
  const pages = Math.max(1, Math.ceil((list.data?.total ?? 0) / PAGE_SIZE))
  const done = (msg: string) => {
    setNotice(msg)
    setOpen(null)
    void list.reload()
  }

  return (
    <Shell area="admin" active="accounts" title={t('ad.acc.title')} lede={t('ad.acc.lede')}>
      <div className="wk-page">
        <section className="wk-block">
          <details className="wk-lines">
            <summary>{t('ad.acc.new')}</summary>
            <CreateForm onDone={() => done(t('ad.acc.created'))} />
          </details>
        </section>

        <section className="wk-block" aria-label={t('ad.acc.title')}>
          <div className="ad-bar">
            <label className="vh-label wk-grow">
              {t('ad.acc.search')}
              <input className="vh-input" type="search" value={q} placeholder={t('ad.acc.searchPh')} onChange={(e) => { setQ(e.target.value); setPage(1) }} />
            </label>
            <label className="vh-label">
              {t('ad.acc.role')}
              <select className="vh-select" value={role} onChange={(e) => { setRole(e.target.value); setPage(1) }}>
                <option value="">{t('ad.acc.allRoles')}</option>
                {ROLES.map((r) => <option key={r} value={r}>{t(`ad.role.${r}`)}</option>)}
              </select>
            </label>
            <label className="vh-label">
              {t('ad.acc.status')}
              <select className="vh-select" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }}>
                <option value="">{t('ad.acc.allStatus')}</option>
                {STATUSES.map((s) => <option key={s} value={s}>{t(`ad.status.${s}`)}</option>)}
              </select>
            </label>
          </div>

          {notice && <p className="ad-note" role="status">{notice}</p>}
          {!!list.error && <p className="lg-error" role="alert">{errText(t, orderErrorKey(list.error))}</p>}
          {list.loading && !list.data && <p className="sub" role="status">{t('co.loading')}</p>}

          {list.data && (
            <div className="ad-scroll">
              <table className="ad-table">
                <thead>
                  <tr>
                    <th scope="col">{t('ad.acc.person')}</th>
                    <th scope="col">{t('ad.acc.role')}</th>
                    <th scope="col">{t('ad.acc.status')}</th>
                    <th scope="col">{t('ad.acc.lastLogin')}</th>
                    <th scope="col"><span className="ad-sr">{t('ad.acc.manage')}</span></th>
                  </tr>
                </thead>
                <tbody>
                  {list.data.items.map((a) => (
                    <AccountRows key={a.id} a={a} self={a.id === me?.id} open={open === a.id} onToggle={() => setOpen(open === a.id ? null : a.id)} onDone={() => done(t('ad.acc.saved'))} locale={locale} />
                  ))}
                </tbody>
              </table>
              {!list.data.items.length && <p className="sub">{t('ad.acc.empty')}</p>}
            </div>
          )}

          {list.data && (
            <div className="ad-pager">
              <span className="sub">{t('ad.acc.count', { n: list.data.total })}</span>
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

function AccountRows({ a, self, open, onToggle, onDone, locale }: { a: AdminAccount; self: boolean; open: boolean; onToggle: () => void; onDone: () => void; locale: string }) {
  const t = useT()
  return (
    <>
      <tr className={a.status === 'ACTIVE' ? '' : 'off'}>
        <td>
          <div className="ad-who">
            <span className={`avatar ${avatarTone(a.name)}`}>{initials(a.name)}</span>
            <div className="t"><b>{a.name}{self ? ` (${t('ad.acc.you')})` : ''}</b><span>{a.email}{a.phone ? ` · ${a.phone}` : ''}</span></div>
          </div>
        </td>
        <td>{t(`ad.role.${a.role}`)}</td>
        <td><span className={`chip ${STATUS_CHIP[a.status] ?? 'mute'}`}>{t(`ad.status.${a.status}`)}</span></td>
        <td className="sub">{a.lastLoginAt ? new Date(a.lastLoginAt).toLocaleString(locale, { dateStyle: 'medium', timeStyle: 'short' }) : t('ad.acc.never')}</td>
        <td><button className="vh-btn vh-btn--ghost vh-btn--sm" aria-expanded={open} onClick={onToggle}>{open ? t('ov.back') : t('ad.acc.manage')}</button></td>
      </tr>
      {open && (
        <tr className="ad-edit">
          <td colSpan={5}><EditForm a={a} self={self} onDone={onDone} /></td>
        </tr>
      )}
    </>
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
    <div className="wk-form">
      <label className="vh-label">
        {t('ad.acc.status')}
        <select className="vh-select" value={status} onChange={(e) => setStatus(e.target.value as AccountStatus)}>
          {STATUSES.map((s) => <option key={s} value={s}>{t(`ad.status.${s}`)}</option>)}
        </select>
      </label>
      <label className="vh-label">
        {t('ad.acc.role')}
        <select className="vh-select" value={role} onChange={(e) => setRole(e.target.value)}>
          {ROLES.map((r) => <option key={r} value={r}>{t(`ad.role.${r}`)}</option>)}
        </select>
      </label>
      <label className="vh-label wk-grow">
        {t('ad.acc.reason')}
        <input className="vh-input" value={reason} maxLength={500} placeholder={t('ad.acc.reasonPh')} onChange={(e) => setReason(e.target.value)} />
      </label>
      <button className="vh-btn vh-btn--primary vh-btn--sm" disabled={busy || !changed} onClick={() => void save()}>{t('ad.acc.save')}</button>
      {self && changed && <p className="wk-warn" style={{ flexBasis: '100%' }}>{t('ad.acc.selfWarn')}</p>}
      {err && <p className="lg-error" role="alert" style={{ flexBasis: '100%' }}>{errText(t, err)}</p>}
    </div>
  )
}

function CreateForm({ onDone }: { onDone: () => void }) {
  const t = useT()
  const [f, setF] = useState({ email: '', name: '', phone: '', password: '', role: INTERNAL_ROLES[0] as string })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [lines, setLines] = useState<string[]>([])
  const phone = cleanPhone(f.phone)
  const ok = EMAIL.test(f.email.trim()) && f.name.trim() && PASSWORD_RULE.test(f.password) && (!phone || PHONE_RULE.test(phone))

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
    <form className="wk-form" onSubmit={(e) => { e.preventDefault(); void submit() }}>
      <label className="vh-label wk-grow">{t('ad.acc.email')}<input className="vh-input" type="email" autoComplete="off" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></label>
      <label className="vh-label wk-grow">{t('ad.acc.name')}<input className="vh-input" maxLength={150} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></label>
      <label className="vh-label">{t('ad.acc.phone')}<input className="vh-input" inputMode="tel" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} /></label>
      <label className="vh-label">
        {t('ad.acc.password')}
        <input className="vh-input" type="password" autoComplete="new-password" maxLength={72} value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
      </label>
      <label className="vh-label">
        {t('ad.acc.role')}
        <select className="vh-select" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>
          {INTERNAL_ROLES.map((r) => <option key={r} value={r}>{t(`ad.role.${r}`)}</option>)}
        </select>
      </label>
      <button className="vh-btn vh-btn--primary vh-btn--md" type="submit" disabled={busy || !ok}>{t('ad.acc.create')}</button>
      <p className="sub" style={{ flexBasis: '100%' }}>{t('reg.passwordHelp')}</p>
      {err && <p className="lg-error" role="alert" style={{ flexBasis: '100%' }}>{errText(t, err)}{lines.length ? `: ${lines.join('; ')}` : ''}</p>}
    </form>
  )
}
