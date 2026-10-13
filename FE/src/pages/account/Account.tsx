import { ClockCounterClockwise, CreditCard, NotePencil, SignOut, SlidersHorizontal, User as UserIcon } from '@phosphor-icons/react'
import { useEffect, useRef, useState } from 'react'
import Page from '../../components/layout/Page'
import { MethodLogos } from '../../components/ui/PaymentLogos'
import PaymentLogos from '../../components/ui/PaymentLogos'
import { PAYMENT_BADGES, PAY_METHODS, STATUS_COLORS } from '../../constants/catalog'
import { LANGS, setLang, useLang, useT, useTn } from '../../i18n'
import { Link, navigate, orderPath } from '../../router/router'
import { setTheme, useTheme } from '../../store/theme'
import {
  signIn, signOut, updateProfile, useDrafts, useOrders, useProfile, useUser,
} from '../../store/store'
import type { Order } from '../../types'
import { fmt } from '../../utils/format'
import { shrinkImage } from '../tech/phase'
import DraftsSection from './DraftsSection'
import './account.css'

export type Section = 'profile' | 'preferences' | 'orders' | 'drafts' | 'payment'
const CUSTOMER_ONLY: Section[] = ['orders', 'drafts', 'payment']

/** Where an order opens from the history list, by status. */
function orderHref(o: Order) {
  if (o.status === 'Accepted') return orderPath(o.id, 'deposit')
  if (['Shipped', 'Delivered'].includes(o.status)) return orderPath(o.id, 'tracking')
  if (['Written', 'Rewriting'].includes(o.status)) return orderPath(o.id, 'result')
  return orderPath(o.id, 'review')
}

export default function Account({ section }: { section: Section }) {
  const t = useT()
  const user = useUser()
  const profile = useProfile()
  const orders = useOrders()
  const drafts = useDrafts()

  if (!user) {
    return (
      <Page label="Account" width={720}>
        <div className="vh-panel" style={{ alignItems: 'flex-start' }}>
          <h1 className="vh-h1">{t('acct.guestTitle')}</h1>
          <p className="vh-lede">{t('acct.guestBody')}</p>
          <button className="vh-btn vh-btn--primary" onClick={() => { signIn(); navigate('/account') }}>{t('nav.signIn')}</button>
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
                {item('orders', '/account/orders', t('acct.nav.orders'), <ClockCounterClockwise size={20} aria-hidden />, orders.length)}
                {item('drafts', '/account/drafts', t('acct.nav.drafts'), <NotePencil size={20} aria-hidden />, drafts.length)}
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
  const save = (e: React.FormEvent) => {
    e.preventDefault()
    updateProfile({ ...form, fullName: form.fullName.trim() || user?.name || '' })
    setSaved(true)
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setSaved(false), 3000)
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
            <input className="vh-input" type="email" autoComplete="email" value={form.email} onChange={(e) => set({ email: e.target.value })} />
            <small>{t('acct.p.emailHelp')}</small>
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
            <button type="submit" className="vh-btn vh-btn--primary vh-btn--md">{t('acct.p.save')}</button>
            {saved && <span className="ac-saved" role="status">{t('acct.p.saved')}</span>}
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
  const tn = useTn()
  const orders = useOrders()
  return (
    <>
      <div className="ac-h2-row">
        <h2 className="ac-h2">{t('acct.o.title')}</h2>
        {orders.length > 0 && <span className="vh-mono ac-count">{t('acct.o.count', { n: orders.length })}</span>}
      </div>
      {orders.length ? (
        <ul className="ac-orders">
          {orders.map((o) => {
            const [color] = STATUS_COLORS[o.status]
            return (
              <li key={o.id}>
                <Link to={orderHref(o)} className="ac-order">
                  <span className="ac-order-main">
                    <span className="ac-order-title">{tn(o.title)}</span>
                    <span className="vh-mono ac-order-meta">{o.id} · {o.date}</span>
                  </span>
                  <span className="vh-chip" style={{ color }}>{t(`status.${o.status}`)}</span>
                  <span className="vh-mono ac-order-total">{fmt(o.total)}</span>
                </Link>
              </li>
            )
          })}
        </ul>
      ) : (
        <div className="ac-empty">
          <b>{t('acct.o.emptyTitle')}</b>
          <span>{t('acct.o.emptyBody')}</span>
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
        {PAY_METHODS.map((m) => (
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
