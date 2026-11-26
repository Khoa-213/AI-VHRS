import { useEffect, useState, type FormEvent } from 'react'
import { Eye, EyeSlash, LockKey } from '@phosphor-icons/react'
import Page from '../../components/layout/Page'
import { useT } from '../../i18n'
import { navigate } from '../../router/router'
import { ApiError, authErrorKey } from '../../services/api'
import { PASSWORD_RULE, apiConfirmResetCode, apiRequestReset } from '../../services/auth'
import { openAuth } from '../../store/authDialog'
import OtpBoxes, { OTP_DIGITS } from './OtpBoxes'
import '../create-order/sign-in-dialog.css'

/** Seconds before another code may be asked for (the backend keeps the same wait between two codes). */
const RESEND_S = 60

type Field = 'email' | 'code' | 'password' | 'confirm'
type Secret = 'password' | 'confirm'
type Job = { (): Promise<void> }

/**
 * The page the reset email links to (`BE/docs/FE_API_GUIDE.md`, 2026-11-26, code only): the email, the 6-digit code of
 * that email and the new password, saved in one call (`{email, code, new_password}`). The link carries no token;
 * `?email=` fills the email in. The sign-in dialog has the same steps in `ForgotPassword.tsx`.
 */
export default function ResetPassword() {
  const t = useT()
  const [params] = useState(() => new URLSearchParams(window.location.search))
  const [form, setForm] = useState({ email: params.get('email') ?? '', code: '', password: '', confirm: '' })
  const [visible, setVisible] = useState({ password: false, confirm: false })
  const [errors, setErrors] = useState<Partial<Record<Field, string>>>({})
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(false)
  const [wait, setWait] = useState(0)

  // Keep the email out of the address bar and history once read.
  useEffect(() => {
    if (window.location.search) window.history.replaceState(null, '', window.location.pathname)
  }, [])

  useEffect(() => {
    if (wait <= 0) return
    const id = window.setTimeout(() => setWait((s) => s - 1), 1000)
    return () => window.clearTimeout(id)
  }, [wait])

  const signIn = () => {
    navigate('/', { replace: true })
    openAuth('login')
  }

  const edit = (key: Field, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }))
    setErrors((prev) => ({ ...prev, [key]: undefined }))
  }

  const run = async (job: Job) => {
    if (busy) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await job()
    } catch (e) {
      setError(t(authErrorKey(e)))
    } finally {
      setBusy(false)
    }
  }

  const emailOk = (value: string) => /^\S+@\S+\.\S+$/.test(value.trim())

  const submit = (event: FormEvent) => {
    event.preventDefault()
    const next: Partial<Record<Field, string>> = {}
    if (!emailOk(form.email)) next.email = t('login.errEmail')
    if (form.code.length < OTP_DIGITS) next.code = t('reset.otpErr')
    if (!PASSWORD_RULE.test(form.password)) next.password = t('reg.errPassword')
    else if (form.confirm !== form.password) next.confirm = t('reg.errConfirm')
    setErrors(next)
    if (Object.keys(next).length) return
    void run(async () => {
      try {
        await apiConfirmResetCode({ email: form.email.trim() }, form.code, form.password)
        setDone(true)
      } catch (e) {
        // A wrong, expired or used-up code: the boxes are cleared, the rest of the form is kept.
        if (e instanceof ApiError && e.code.startsWith('OTP_')) setForm((prev) => ({ ...prev, code: '' }))
        throw e
      }
    })
  }

  const resend = () => {
    if (!emailOk(form.email)) return setErrors((prev) => ({ ...prev, email: t('login.errEmail') }))
    const email = form.email.trim()
    void run(async () => {
      await apiRequestReset(email)
      setForm((prev) => ({ ...prev, code: '' }))
      setWait(RESEND_S)
      setNotice(t('reset.resent', { email }))
    })
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
    <p className="entry-login-description">{t('reset.pageLede')}</p>
    <form onSubmit={submit} noValidate aria-busy={busy}>
      {notice && <p className="entry-login-notice" role="status">{notice}</p>}
      <div className="entry-register-field">
        <label htmlFor="reset-email">{t('login.email')}</label>
        <input id="reset-email" type="email" autoComplete="username" autoFocus={!form.email} value={form.email} disabled={busy}
          aria-invalid={!!errors.email} aria-describedby={described('email')} onChange={(event) => edit('email', event.target.value)} />
        {help('email')}
      </div>
      <div className="entry-register-field">
        <span id="reset-code-label" className="entry-otp-label">{t('reset.otpLabel')}</span>
        <OtpBoxes value={form.code} disabled={busy} invalid={!!errors.code} autoFocus={!!form.email} onChange={(code) => edit('code', code)} />
        {help('code')}
      </div>
      {secret('password', t('reset.newPassword'), t('reg.passwordHelp'))}
      {secret('confirm', t('reg.confirm'))}
      {error && <p className="entry-login-error" role="alert">{error}</p>}
      <button type="submit" className="entry-login-submit" disabled={busy}>{t(busy ? 'reset.saving' : 'reset.save')}</button>
      {busy && <p className="entry-login-notice" role="status">{t('login.waking')}</p>}
      <button type="button" className="entry-login-link" disabled={busy || wait > 0} onClick={resend}>
        {wait > 0 ? t('reset.resendIn', { s: wait }) : t('reset.resend')}
      </button>
      <button type="button" className="entry-login-link" disabled={busy} onClick={signIn}>{t('reset.back')}</button>
    </form>
  </>

  return (
    <Page label="Reset password" width={560} footer>
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
