import { useState, type FormEvent } from 'react'
import { useT } from '../../i18n'
import SkipLink from '../../components/ui/SkipLink'
import ThemeToggle from '../../components/ui/ThemeToggle'
import LanguageToggle from '../../components/ui/LanguageToggle'
import { Link, navigate } from '../../router/router'
import { authErrorKey } from '../../services/api'
import { apiRequestReset } from '../../services/auth'
import { signInWithPassword, useSessionExpired, useUser } from '../../store/store'
import type { Role } from '../../types'
import './login.css'
import '../staff/polish.css'

const HOME: Record<Role, string> = { customer: '/', staff: '/staff', technician: '/tech' }
const EMAIL = /^\S+@\S+\.\S+$/

/** Where to go after signing in: the page that sent the visitor here, else by role. */
function destination(role: Role): string {
  const next = new URLSearchParams(window.location.search).get('next')
  if (next && next.startsWith('/') && !next.startsWith('//') && !/^\/(login|register)\b/.test(next)) {
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
  const expired = useSessionExpired()
  const [mode, setMode] = useState<'login' | 'reset'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (busy) return
    if (!EMAIL.test(email.trim())) return setError(t('login.errEmail'))
    if (mode === 'login' && !password) return setError(t('login.errPassword'))
    setError('')
    setNotice('')
    setBusy(true)
    try {
      if (mode === 'reset') {
        await apiRequestReset(email.trim())
        setNotice(t('reset.sent', { email: email.trim() }))
        setMode('login')
      } else {
        const u = await signInWithPassword(email, password)
        navigate(destination(u.role))
      }
    } catch (err) {
      setError(t(authErrorKey(err)))
    } finally {
      setBusy(false)
    }
  }

  const switchMode = (m: 'login' | 'reset') => {
    setMode(m)
    setError('')
    setNotice('')
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
        <form className="lg-card" onSubmit={submit} noValidate aria-busy={busy}>
          <div className="lg-head">
            <h1>{t(mode === 'reset' ? 'reset.title' : 'login.title')}</h1>
            <p>{t(mode === 'reset' ? 'reset.lede' : 'login.lede')}</p>
          </div>

          {mode === 'login' && expired && !user && <p className="lg-already" role="status">{t('login.expired')}</p>}
          {mode === 'login' && user && (
            <p className="lg-already">
              {t('login.signedInAs', { name: user.name, role: t(`role.${user.role}`) })}{' '}
              <Link to={HOME[user.role]} className="vh-link">{t('login.continue')}</Link>
            </p>
          )}
          {notice && <p className="lg-already" role="status">{notice}</p>}

          <label className="vh-label" htmlFor="lg-email">
            {t('login.email')}
            <input
              id="lg-email"
              className="vh-input"
              type="email"
              autoComplete="username"
              placeholder="you@example.com"
              value={email}
              disabled={busy}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          {mode === 'login' && (
            <label className="vh-label" htmlFor="lg-pass">
              {t('login.password')}
              <input
                id="lg-pass"
                className="vh-input"
                type="password"
                autoComplete="current-password"
                value={password}
                disabled={busy}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
          )}

          {error && <p className="lg-error" role="alert">{error}</p>}

          <button type="submit" className="vh-btn vh-btn--primary" disabled={busy}>
            {mode === 'reset'
              ? t(busy ? 'reset.sending' : 'reset.send')
              : t(busy ? 'login.signingIn' : 'login.title')}
          </button>
          {busy && mode === 'login' && <p className="lg-note" role="status">{t('login.waking')}</p>}

          <div className="lg-links">
            {mode === 'login' ? (
              <>
                <button type="button" className="vh-link" onClick={() => switchMode('reset')}>{t('login.forgot')}</button>
                <span>
                  {t('login.noAccount')} <Link to="/register" className="vh-link">{t('login.createAccount')}</Link>
                </span>
              </>
            ) : (
              <button type="button" className="vh-link" onClick={() => switchMode('login')}>{t('reset.back')}</button>
            )}
          </div>

        </form>
      </main>
    </div>
  )
}
