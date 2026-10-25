import { useEffect, useState, type FormEvent } from 'react'
import { Eye, EyeSlash, LockKey } from '@phosphor-icons/react'
import Page from '../../components/layout/Page'
import { useT } from '../../i18n'
import { navigate } from '../../router/router'
import { authErrorKey } from '../../services/api'
import { PASSWORD_RULE, apiConfirmReset, apiRequestReset } from '../../services/auth'
import { openAuth } from '../../store/authDialog'
import '../create-order/sign-in-dialog.css'

type Field = 'code' | 'password' | 'confirm'
type Secret = 'password' | 'confirm'

/**
 * Second step of "Forgot password": the email holds a reset code (a long token), entered here with the new password.
 * Reached from the sign-in dialog with `?email=`; a `?token=` in the address fills the code in.
 */
export default function ResetPassword() {
  const t = useT()
  const [params] = useState(() => new URLSearchParams(window.location.search))
  const email = params.get('email') ?? ''
  const [form, setForm] = useState({ code: params.get('token') ?? '', password: '', confirm: '' })
  const [visible, setVisible] = useState({ password: false, confirm: false })
  const [errors, setErrors] = useState<Partial<Record<Field, string>>>({})
  const [error, setError] = useState('')
  const [notice, setNotice] = useState(email ? t('reset.sent', { email }) : '')
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)

  // Keep the email and any token out of the address bar and history once read.
  useEffect(() => {
    if (window.location.search) window.history.replaceState(null, '', window.location.pathname)
  }, [])

  const signIn = () => {
    navigate('/', { replace: true })
    openAuth('login')
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (busy) return
    // Mail clients can wrap a long code over lines: whitespace is never part of it.
    const code = form.code.replace(/\s+/g, '')
    const next: Partial<Record<Field, string>> = {}
    if (!code) next.code = t('reset.errCode')
    if (!PASSWORD_RULE.test(form.password)) next.password = t('reg.errPassword')
    else if (form.confirm !== form.password) next.confirm = t('reg.errConfirm')
    setErrors(next)
    setError('')
    setNotice('')
    if (Object.keys(next).length) return
    setBusy(true)
    try {
      await apiConfirmReset(code, form.password)
      setDone(true)
    } catch (err) {
      const key = authErrorKey(err)
      setError(t(key === 'auth.err.link' ? 'reset.errCodeBad' : key))
    } finally {
      setBusy(false)
    }
  }

  const resend = async () => {
    if (busy) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await apiRequestReset(email)
      setNotice(t('reset.resent', { email }))
    } catch (err) {
      setError(t(authErrorKey(err)))
    } finally {
      setBusy(false)
    }
  }

  const edit = (key: Field, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }))
    setErrors((prev) => ({ ...prev, [key]: undefined }))
  }
  const help = (key: Field, text?: string) => (errors[key] || text) &&
    <span id={`reset-${key}-help`} className={errors[key] ? 'entry-login-error' : 'entry-register-help'}>{errors[key] ?? text}</span>
  const described = (key: Field, text?: string) => (errors[key] || text ? `reset-${key}-help` : undefined)

  const secret = (key: Secret, label: string, text?: string) => {
    const id = `reset-${key}`
    return <div className="entry-register-field">
      <label htmlFor={id}>{label}</label>
      <div className="entry-login-password">
        <LockKey size={19} aria-hidden="true" />
        <input id={id} type={visible[key] ? 'text' : 'password'} autoComplete="new-password" value={form[key]} disabled={busy}
          aria-invalid={!!errors[key]} aria-describedby={described(key, text)} onChange={(event) => edit(key, event.target.value)} />
        <button type="button" onClick={() => setVisible((prev) => ({ ...prev, [key]: !prev[key] }))} aria-pressed={visible[key]} aria-label={t(visible[key] ? 'login.hidePassword' : 'login.showPassword')}>
          {visible[key] ? <EyeSlash size={21} /> : <Eye size={21} />}
        </button>
      </div>
      {help(key, text)}
    </div>
  }

  let body
  if (done) body = <>
    <p className="entry-login-notice" role="status">{t('reset.done')}</p>
    <form onSubmit={(event) => { event.preventDefault(); signIn() }}>
      <button type="submit" className="entry-login-submit" autoFocus>{t('reset.signIn')}</button>
    </form>
  </>
  else body = <>
    <p className="entry-login-description">{t('reset.newLede')}</p>
    <form onSubmit={submit} noValidate aria-busy={busy}>
      {notice && <p className="entry-login-notice" role="status">{notice}</p>}
      <div className="entry-register-field">
        <label htmlFor="reset-code">{t('reset.code')}</label>
        <input id="reset-code" type="text" autoComplete="one-time-code" autoCapitalize="off" autoCorrect="off" spellCheck={false} autoFocus
          value={form.code} disabled={busy} aria-invalid={!!errors.code} aria-describedby={described('code', t('reset.codeHelp'))}
          onChange={(event) => edit('code', event.target.value)} />
        {help('code', t('reset.codeHelp'))}
      </div>
      {secret('password', t('reset.newPassword'), t('reg.passwordHelp'))}
      {secret('confirm', t('reg.confirm'))}
      {error && <p className="entry-login-error" role="alert">{error}</p>}
      <button type="submit" className="entry-login-submit" disabled={busy}>{t(busy ? 'reset.saving' : 'reset.save')}</button>
      {busy && <p className="entry-login-notice" role="status">{t('login.waking')}</p>}
      {email && <button type="button" className="entry-login-link" disabled={busy} onClick={() => void resend()}>{t('reset.resend')}</button>}
      <button type="button" className="entry-login-link" disabled={busy} onClick={signIn}>{t('reset.back')}</button>
    </form>
  </>

  return (
    <Page label="Reset password" width={560}>
      <div className="entry-reset">
        <div className="entry-login entry-register-card">
          <div className="entry-login-panel">
            <span className="entry-login-brand">AI-VHRS</span>
            <h1>{t('reset.newTitle')}</h1>
            {body}
          </div>
        </div>
      </div>
    </Page>
  )
}
