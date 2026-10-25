import { useState, type FormEvent } from 'react'
import { Eye, EyeSlash, LockKey, X } from '@phosphor-icons/react'
import { useT } from '../../i18n'
import { authErrorKey } from '../../services/api'
import { apiRequestReset } from '../../services/auth'
import { navigate } from '../../router/router'
import { closeAuth } from '../../store/authDialog'
import { GOOGLE_CLIENT_ID } from '../../services/google'
import { signInWithGoogle, signInWithPassword, useSessionExpired, useUser } from '../../store/store'
import GoogleButton from '../../components/ui/GoogleButton'
import type { User } from '../../types'
import RegisterForm from './RegisterForm'
import '../create-order/sign-in-dialog.css'

export default function SignInPanel({ onSuccess: finish, onClose, initialMode = 'login' }: {
  onSuccess: (user: User) => void
  onClose?: () => void
  initialMode?: 'login' | 'register'
}) {
  const t = useT()
  const user = useUser()
  const expired = useSessionExpired()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [visible, setVisible] = useState(false)
  const [reset, setReset] = useState(false)
  const [register, setRegister] = useState(initialMode === 'register')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (busy) return
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) return setError(t('login.errEmail'))
    if (!reset && !password) return setError(t('login.errPassword'))
    setBusy(true)
    setError('')
    setNotice('')
    try {
      if (reset) {
        await apiRequestReset(email.trim())
        // The email carries a code: continue on the page where it is entered with the new password.
        closeAuth()
        navigate(`/reset-password?email=${encodeURIComponent(email.trim())}`)
      } else finish(await signInWithPassword(email, password))
    } catch (err) {
      setError(t(authErrorKey(err)))
    } finally {
      setBusy(false)
    }
  }

  const google = async (token: string) => {
    if (busy) return
    setBusy(true)
    setError('')
    try {
      finish(await signInWithGoogle(token))
    } catch (err) {
      setError(t(authErrorKey(err)))
    } finally {
      setBusy(false)
    }
  }

  return (
      <div className="entry-login-panel">
        {onClose && <button type="button" className="entry-login-close" onClick={onClose} aria-label={t(register ? 'reg.close' : 'login.close')}><X size={20} /></button>}
        <span className="entry-login-brand">AI-VHRS</span>
        <h2 id="entry-login-title">{t(register ? 'reg.title' : reset ? 'reset.title' : 'login.title')}</h2>
        <p id="entry-login-description" className="entry-login-description">{t(register ? 'reg.lede' : reset ? 'reset.lede' : 'co.signInBody')}</p>
        {expired && !user && <p className="entry-login-notice" role="status">{t('login.expired')}</p>}
        {register ? <RegisterForm onSuccess={finish} onSignIn={() => setRegister(false)} /> : <form onSubmit={submit} noValidate aria-busy={busy}>
          <label htmlFor="entry-email">{t('login.email')}</label>
          <input id="entry-email" type="email" autoComplete="username" autoFocus value={email} disabled={busy} onChange={(event) => setEmail(event.target.value)} />
          {!reset && <>
            <label htmlFor="entry-password">{t('login.password')}</label>
            <div className="entry-login-password">
              <LockKey size={19} aria-hidden="true" />
              <input id="entry-password" type={visible ? 'text' : 'password'} autoComplete="current-password" value={password} disabled={busy} onChange={(event) => setPassword(event.target.value)} />
              <button type="button" onClick={() => setVisible(!visible)} aria-label={t(visible ? 'login.hidePassword' : 'login.showPassword')} aria-pressed={visible}>
                {visible ? <EyeSlash size={21} /> : <Eye size={21} />}
              </button>
            </div>
          </>}
          {error && <p className="entry-login-error" role="alert">{error}</p>}
          {notice && <p className="entry-login-notice" role="status">{notice}</p>}
          <button type="submit" className="entry-login-submit" disabled={busy}>{t(reset ? (busy ? 'reset.sending' : 'reset.send') : (busy ? 'login.signingIn' : 'login.title'))}</button>
          {busy && <p className="entry-login-notice" role="status">{t('login.waking')}</p>}
          {!reset && GOOGLE_CLIENT_ID && <>
            <div className="entry-login-divider">{t('login.or')}</div>
            <GoogleButton disabled={busy} onToken={(token) => void google(token)} onError={() => setError(t('auth.err.googleDown'))} />
          </>}
          <button type="button" className="entry-login-link" disabled={busy} onClick={() => { setReset(!reset); setError(''); setNotice(''); setVisible(false) }}>{t(reset ? 'reset.back' : 'login.forgot')}</button>
          {!reset && <p className="entry-login-register">{t('login.noAccount')}{' '}<button type="button" className="entry-register-switch" disabled={busy} onClick={() => { setRegister(true); setVisible(false); setError(''); setNotice('') }}>{t('login.createAccount')}</button></p>}
        </form>}
      </div>
  )
}
