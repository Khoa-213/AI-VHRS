import { openAuth } from '../../store/authDialog'
import { ClockCounterClockwise, CreditCard, NotePencil, SignOut, SlidersHorizontal, User as UserIcon } from '@phosphor-icons/react'
import { useEffect, useRef, useState } from 'react'
import Page from '../../components/layout/Page'
import { MethodLogos } from '../../components/ui/PaymentLogos'
import PaymentLogos from '../../components/ui/PaymentLogos'
import { PAYMENT_BADGES, PAY_METHODS } from '../../constants/catalog'
import { STATUS_COLOR, orderLink } from '../../constants/orderStatus'
import { useAsync } from '../../hooks/useAsync'
import { LANGS, setLang, useLang, useLocale, useT, useTn } from '../../i18n'
import { Link, navigate } from '../../router/router'
import { SENT, listOrders, orderErrorKey, type Order, errText } from '../../services/orders'
import { setTheme, useTheme } from '../../store/theme'
import { authErrorKey } from '../../services/api'
import { PHONE_RULE, cleanPhone } from '../../services/auth'
import {
  saveAccount, signOut, updateProfile, useProfile, useUser,
} from '../../store/store'
import { fmt } from '../../utils/format'
import { shrinkImage } from '../tech/phase'
import DraftsSection from './DraftsSection'
import './account.css'

export type Section = 'profile' | 'preferences' | 'orders' | 'drafts' | 'payment'
const CUSTOMER_ONLY: Section[] = ['orders', 'drafts', 'payment']

export default function Account({ section }: { section: Section }) {
  const t = useT()
  const user = useUser()
  const profile = useProfile()
  const customerUser = user?.role === 'customer'
  const counts = useAsync(
    async () => (customerUser
      ? { orders: (await listOrders({ status: SENT, pageSize: 1 })).total, drafts: (await listOrders({ status: 'DRAFT', pageSize: 1 })).total }
      : null),
    [user?.id, customerUser, section],
  )

  if (!user) {
    return (
      <Page label="Account" width={720}>
        <div className="vh-panel" style={{ alignItems: 'flex-start' }}>
          <h1 className="vh-h1">{t('acct.guestTitle')}</h1>
          <p className="vh-lede">{t('acct.guestBody')}</p>
          <button className="vh-btn vh-btn--primary" onClick={() => openAuth('login', '/account')}>{t('nav.signIn')}</button>
        </div>
      </Page>
    )
  }

  const customer = user.role === 'customer'
  const current: Section = !customer && CUSTOMER_ONLY.includes(section) ? 'profile' : section
  const shownName = profile.fullName || user.name
  const initial = shownName.trim().charAt(0).toUpperCase()

  const item = (id: Section, to: string, label: string, icon: React.ReactNode, count?: number) => (
    <Link key={id} to={to} className={`ac-nav-item${current === id ? ' on' : ''}`} aria-current={current === id ? 'page' : undefined}>
      {icon}
      <span>{label}</span>
      {!!count && <b className="vh-mono">{count}</b>}
    </Link>
  )

  return (
    <Page label="Account" width={1200}>
      <div className="ac">
        <header className="ac-head">
          {profile.avatar
            ? <img src={profile.avatar} alt="" className="ac-avatar" />
            : <span className="ac-avatar ac-avatar--initial">{initial}</span>}
          <div>
            <h1>
              {shownName}
              {shownName !== user.name && <span className="ac-handle"> ({user.name})</span>}
            </h1>
            <p>{t('acct.sub')}</p>
          </div>
        </header>

        <div className="ac-grid">
          <nav className="ac-nav" aria-label={t('acct.navAria')}>
            {item('profile', '/account', t('acct.nav.profile'), <UserIcon size={20} aria-hidden />)}
            {item('preferences', '/account/preferences', t('acct.nav.preferences'), <SlidersHorizontal size={20} aria-hidden />)}
            {customer && (
              <>
                <span className="ac-nav-group">{t('acct.group.activity')}</span>
                {item('orders', '/account/orders', t('acct.nav.orders'), <ClockCounterClockwise size={20} aria-hidden />, counts.data?.orders)}
                {item('drafts', '/account/drafts', t('acct.nav.drafts'), <NotePencil size={20} aria-hidden />, counts.data?.drafts)}
                {item('payment', '/account/payment', t('acct.nav.payment'), <CreditCard size={20} aria-hidden />)}
              </>
            )}
            <button type="button" className="ac-nav-item ac-nav-out" onClick={() => { signOut(); navigate('/') }}>
              <SignOut size={20} aria-hidden />
              <span>{t('acct.signOut')}</span>
            </button>
          </nav>

          <main className="ac-body" id="main">
            {current === 'profile' && <ProfileSection />}
            {current === 'preferences' && <PreferencesSection />}
            {current === 'orders' && <OrdersSection />}
            {current === 'drafts' && (
              <>
                <h2 className="ac-h2">{t('acct.d.title')}</h2>
                <DraftsSection />
              </>
            )}
            {current === 'payment' && <PaymentSection />}
          </main>
        </div>
      </div>
    </Page>
  )
}

function ProfileSection() {
  const t = useT()
  const user = useUser()
  const profile = useProfile()
  const [form, setForm] = useState({ fullName: profile.fullName, email: profile.email, phone: profile.phone, address: profile.address, bio: profile.bio })
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')
  const file = useRef<HTMLInputElement>(null)
  const timer = useRef<number | undefined>(undefined)
  useEffect(() => () => window.clearTimeout(timer.current), [])

  const set = (patch: Partial<typeof form>) => {
    setForm((f) => ({ ...f, ...patch }))
    setSaved(false)
  }
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState('')
  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    if (saving) return
    const phone = cleanPhone(form.phone)
    if (phone && !PHONE_RULE.test(phone)) {
      setFormError(t('reg.errPhone'))
      return
    }
    setFormError('')
    setSaving(true)
    try {
      // Name and phone live on the backend account; address and bio stay on this device.
      const fullName = form.fullName.trim() || user?.name || ''
      if (fullName !== user?.name || phone !== (user?.phone ?? '')) await saveAccount({ fullName, phone: phone || null })
      updateProfile({ address: form.address, bio: form.bio })
      setSaved(true)
      window.clearTimeout(timer.current)
      timer.current = window.setTimeout(() => setSaved(false), 3000)
    } catch (err) {
      setFormError(t(authErrorKey(err)))
    } finally {
      setSaving(false)
    }
  }
  const pick = async (f: File | undefined) => {
    if (!f) return
    setError('')
    try {
      updateProfile({ avatar: await shrinkImage(f, 360, 0.82) })
    } catch {
      setError(t('acct.p.photoErr'))
    }
  }

  return (
    <>
      <h2 className="ac-h2">{t('acct.p.title')}</h2>
      <div className="ac-split">
        <form className="ac-form" onSubmit={save}>
          <label className="ac-field">
            <span>{t('acct.p.name')}</span>
            <input className="vh-input" autoComplete="name" value={form.fullName} onChange={(e) => set({ fullName: e.target.value })} />
            <small>{t('acct.p.nameHelp')}</small>
          </label>
          <label className="ac-field">
            <span>{t('acct.p.email')}</span>
            <input className="vh-input" type="email" autoComplete="email" value={form.email} readOnly aria-readonly="true" />
            <small>{t('acct.p.emailLocked')}</small>
          </label>
          <label className="ac-field">
            <span>{t('acct.p.phone')}</span>
            <input className="vh-input" inputMode="tel" autoComplete="tel" value={form.phone} onChange={(e) => set({ phone: e.target.value })} />
            <small>{t('acct.p.phoneHelp')}</small>
          </label>
          <label className="ac-field">
            <span>{t('acct.p.address')}</span>
            <input className="vh-input" autoComplete="street-address" value={form.address} onChange={(e) => set({ address: e.target.value })} />
            <small>{t('acct.p.addressHelp')}</small>
          </label>
          <label className="ac-field">
            <span>{t('acct.p.bio')}</span>
            <textarea className="vh-textarea" rows={4} placeholder={t('acct.p.bioPh')} value={form.bio} onChange={(e) => set({ bio: e.target.value })} />
          </label>
          <div className="ac-actions">
            <button type="submit" className="vh-btn vh-btn--primary vh-btn--md" disabled={saving}>{t(saving ? 'acct.p.saving' : 'acct.p.save')}</button>
            {saved && <span className="ac-saved" role="status">{t('acct.p.saved')}</span>}
            {formError && <span className="ac-error" role="alert">{formError}</span>}
          </div>
        </form>

        <aside className="ac-picture">
          <span className="ac-label">{t('acct.p.picture')}</span>
          <div className="ac-picture-frame">
            {profile.avatar
              ? <img src={profile.avatar} alt="" />
              : <span className="ac-picture-initial">{(profile.fullName || user?.name || '').trim().charAt(0).toUpperCase()}</span>}
            <button type="button" className="ac-edit" onClick={() => file.current?.click()}>{t('acct.p.edit')}</button>
          </div>
          <input
            ref={file}
            type="file"
            accept="image/*"
            hidden
            onChange={(e) => {
              void pick(e.target.files?.[0])
              e.target.value = ''
            }}
          />
          {profile.avatar && (
            <button type="button" className="vh-link" onClick={() => updateProfile({ avatar: null })}>{t('acct.p.remove')}</button>
          )}
          {error && <span className="ac-error" role="alert">{error}</span>}
        </aside>
      </div>
    </>
  )
}

function PreferencesSection() {
  const t = useT()
  const theme = useTheme()
  const lang = useLang()
  return (
    <>
      <h2 className="ac-h2">{t('acct.pf.title')}</h2>
      <div className="ac-pref">
        <div className="ac-pref-text">
          <b>{t('acct.pf.theme')}</b>
          <span>{t('acct.pf.themeHelp')}</span>
        </div>
        <div className="ac-seg" role="radiogroup" aria-label={t('acct.pf.theme')}>
          {(['light', 'dark'] as const).map((m) => (
            <button key={m} role="radio" aria-checked={theme === m} className={theme === m ? 'on' : ''} onClick={() => setTheme(m)}>
              {t(m === 'light' ? 'acct.pf.light' : 'acct.pf.dark')}
            </button>
          ))}
        </div>
      </div>
      <div className="ac-pref">
        <div className="ac-pref-text">
          <b>{t('acct.pf.language')}</b>
          <span>{t('acct.pf.languageHelp')}</span>
        </div>
        <div className="ac-seg" role="radiogroup" aria-label={t('acct.pf.language')}>
          {LANGS.map((l) => (
            <button key={l.id} role="radio" aria-checked={lang === l.id} lang={l.id} className={lang === l.id ? 'on' : ''} onClick={() => setLang(l.id)}>
              {l.name}
            </button>
          ))}
        </div>
      </div>
    </>
  )
}

function OrdersSection() {
  const t = useT()
  const locale = useLocale()
  const [page, setPage] = useState(1)
  const list = useAsync(() => listOrders({ status: SENT, page, pageSize: 10 }), [page])
  const orders: Order[] = list.data?.items ?? []
  const total = list.data?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / 10))
  return (
    <>
      <div className="ac-h2-row">
        <h2 className="ac-h2">{t('acct.o.title')}</h2>
        {total > 0 && <span className="vh-mono ac-count">{t('acct.o.count', { n: total })}</span>}
      </div>
      {list.loading && !list.data && <p className="vh-lede" role="status">{t('co.loading')}</p>}
      {!!list.error && <p className="lg-error" role="alert">{errText(t, orderErrorKey(list.error))}</p>}
      {orders.length ? (
        <ul className="ac-orders">
          {orders.map((o) => (
            <li key={o.id}>
              <Link to={orderLink(o.id, o.status)} className="ac-order">
                <span className="ac-order-main">
                  <span className="ac-order-title">{t(`ot.${o.type}`)} × {o.quantity}</span>
                  <span className="vh-mono ac-order-meta">{o.code} · {new Date(o.submittedAt ?? o.createdAt).toLocaleDateString(locale)}</span>
                </span>
                <span className="vh-chip" style={{ color: STATUS_COLOR[o.status] }}>{t(`os.${o.status}`)}</span>
                <span className="vh-mono ac-order-total">
                  {o.total !== null ? fmt(o.total) : o.estMax !== null ? (o.estMin === o.estMax ? fmt(o.estMax) : `${fmt(o.estMin ?? 0)} – ${fmt(o.estMax)}`) : ''}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        !list.loading && (
          <div className="ac-empty">
            <b>{t('acct.o.emptyTitle')}</b>
            <span>{t('acct.o.emptyBody')}</span>
          </div>
        )
      )}
      {pages > 1 && (
        <div className="ac-pager">
          <button className="vh-btn vh-btn--ghost vh-btn--sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>{t('acct.o.prev')}</button>
          <span className="vh-mono">{page} / {pages}</span>
          <button className="vh-btn vh-btn--ghost vh-btn--sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>{t('acct.o.next')}</button>
        </div>
      )}
    </>
  )
}

function PaymentSection() {
  const t = useT()
  const tn = useTn()
  const profile = useProfile()
  return (
    <>
      <h2 className="ac-h2">{t('acct.pay.title')}</h2>
      <p className="vh-lede ac-lede">{t('acct.pay.lede')}</p>
      <div className="vh-choice-grid vh-choice-grid--170">
        <button className={`vh-choice${profile.payMethod === null ? ' on' : ''}`} onClick={() => updateProfile({ payMethod: null })}>
          <span className="vh-choice-name">{t('acct.pay.none')}</span>
        </button>
        {PAY_METHODS.filter((m) => m.id === 'vnpay' || m.id === 'momo').map((m) => (
          <button key={m.id} className={`vh-choice${profile.payMethod === m.id ? ' on' : ''}`} onClick={() => updateProfile({ payMethod: m.id })}>
            <MethodLogos id={m.id} />
            <span className="vh-choice-name">{tn(m.name)}</span>
            <span className="vh-choice-sub">{tn(m.spec)}</span>
          </button>
        ))}
      </div>
      <section className="ct-pay ac-supported">
        <h3>{t('acct.pay.supported')}</h3>
        <PaymentLogos names={PAYMENT_BADGES.map((p) => p.name)} />
      </section>
    </>
  )
}
