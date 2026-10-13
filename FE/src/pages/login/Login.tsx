import { useState, type FormEvent } from 'react'
import { useT } from '../../i18n'
import SkipLink from '../../components/ui/SkipLink'
import ThemeToggle from '../../components/ui/ThemeToggle'
import LanguageToggle from '../../components/ui/LanguageToggle'
import { Link, navigate } from '../../router/router'
import { STAFF_ACCOUNTS, TECH_ACCOUNTS, login, useUser } from '../../store/store'
import type { Role } from '../../types'
import './login.css'
import '../staff/polish.css'

const STAFF_EMAIL = Object.keys(STAFF_ACCOUNTS)[0]
const TECH_EMAIL = Object.keys(TECH_ACCOUNTS)[0]

const HOME: Record<Role, string> = { customer: '/', staff: '/staff', technician: '/tech' }

/** Where to go after signing in: the page that sent the visitor here, else by role. */
function destination(role: Role): string {
  const next = new URLSearchParams(window.location.search).get('next')
  if (next && next.startsWith('/') && !next.startsWith('//')) {
    // Each role only follows `next` into its own area.
    const own = role === 'staff' ? '/staff' : role === 'technician' ? '/tech' : null
    const area = next.startsWith('/staff') ? '/staff' : next.startsWith('/tech') ? '/tech' : null
    if (!area || area === own) return next
  }
  return HOME[role]
}

export default function Login() {
  const t = useT()
  const user = useUser()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) {
      setError(t('login.errEmail'))
      return
    }
    if (!password) {
      setError(t('login.errPassword'))
      return
    }
    setError('')
    const u = login(email)
    navigate(destination(u.role))
  }

  return (
    <div className="lg">
      <SkipLink />
      <header className="lg-top">
        <Link to="/" className="vh-logo">AI-VHRS</Link>
        <ThemeToggle className="vh-icon-btn" />
        <LanguageToggle className="vh-icon-btn" />
      </header>

      <main className="lg-main" id="main">
        <form className="lg-card" onSubmit={submit} noValidate>
          <div className="lg-head">
            <h1>{t('login.title')}</h1>
            <p>{t('login.lede')}</p>
          </div>

          {user && (
            <p className="lg-already">
              {t('login.signedInAs', { name: user.name, role: t(`role.${user.role}`) })}{' '}
              <Link to={HOME[user.role]} className="vh-link">{t('login.continue')}</Link>
            </p>
          )}

          <label className="vh-label" htmlFor="lg-email">
            {t('login.email')}
            <input
              id="lg-email"
              className="vh-input"
              type="email"
              autoComplete="username"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          <label className="vh-label" htmlFor="lg-pass">
            {t('login.password')}
            <input
              id="lg-pass"
              className="vh-input"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>

          {error && <p className="lg-error" role="alert">{error}</p>}

          <button type="submit" className="vh-btn vh-btn--primary">{t('login.title')}</button>

          <div className="lg-demo">
            <span>{t('login.demo')}</span>
            <div>
              <button
                type="button"
                className="vh-btn vh-btn--ghost vh-btn--sm"
                onClick={() => {
                  setEmail(STAFF_EMAIL)
                  setPassword('prototype')
                  setError('')
                }}
              >
                {t('login.fillStaff')}
              </button>
              <button
                type="button"
                className="vh-btn vh-btn--ghost vh-btn--sm"
                onClick={() => {
                  setEmail(TECH_EMAIL)
                  setPassword('prototype')
                  setError('')
                }}
              >
                {t('login.fillTech')}
              </button>
              <button
                type="button"
                className="vh-btn vh-btn--ghost vh-btn--sm"
                onClick={() => {
                  setEmail('khang@example.com')
                  setPassword('prototype')
                  setError('')
                }}
              >
                {t('login.fillCustomer')}
              </button>
            </div>
          </div>
        </form>
      </main>
    </div>
  )
}
