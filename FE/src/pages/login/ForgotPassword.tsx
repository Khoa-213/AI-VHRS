import { useEffect, useState, type FormEvent } from 'react'
import { DeviceMobile, EnvelopeSimple, Eye, EyeSlash, LockKey } from '@phosphor-icons/react'
import { useT } from '../../i18n'
import { ApiError, authErrorKey } from '../../services/api'
import { PASSWORD_RULE, PHONE_RULE, apiConfirmResetCode, apiRequestPhoneReset, apiRequestReset, cleanPhone } from '../../services/auth'
import OtpBoxes, { OTP_DIGITS as DIGITS } from './OtpBoxes'

/** Seconds before another code may be asked for (the backend keeps the same wait between two codes). */
const RESEND_S = 60

type Step = 'start' | 'otp' | 'password' | 'done'
/** Where the code goes: the account's email, or the phone number verified on the account (SMS). */
type Via = 'email' | 'phone'
type Job = { (): Promise<void> }
type Secret = 'password' | 'confirm'

/**
 * "Forgot password" inside the sign-in dialog: the email or the verified phone number, then the 6-digit code that was
 * sent there, then the new password (`BE/docs/FE_API_GUIDE.md` 3.1 and 3.2, 2026-11-26). The backend checks the code and
 * sets the password in one call (`POST /auth/password-reset/confirm {email | phone, code, new_password}`), so a wrong or
 * expired code is reported after the password step and brings the six boxes back. Asking for a code always answers 202,
 * whether or not the email or the number is known, so the next screen never says that an account exists.
 */
export default function ForgotPassword({ initialEmail, onBack }: {
  initialEmail: string
  /**
   * Back to the sign-in form. After a reset a string is passed: the email, so it is already filled in, or an empty
   * string when the reset went by phone.
   */
  onBack: (email?: string) => void
}) {
  const t = useT()
  const [step, setStep] = useState<Step>('start')
  const [via, setVia] = useState<Via>('email')
  const [email, setEmail] = useState(initialEmail)
  const [phone, setPhone] = useState('')
  const [code, setCode] = useState('')
  const [form, setForm] = useState({ password: '', confirm: '' })
  const [visible, setVisible] = useState({ password: false, confirm: false })
  const [errors, setErrors] = useState<Partial<Record<Secret, string>>>({})
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [wait, setWait] = useState(0)
  const byPhone = via === 'phone'

  useEffect(() => {
    if (wait <= 0) return
    const id = window.setTimeout(() => setWait((s) => s - 1), 1000)
    return () => window.clearTimeout(id)
  }, [wait])

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

  const sendCode = (event: FormEvent) => {
    event.preventDefault()
    const address = email.trim()
    const number = cleanPhone(phone)
    if (byPhone ? !PHONE_RULE.test(number) : !/^\S+@\S+\.\S+$/.test(address)) return setError(t(byPhone ? 'reset.errPhone' : 'login.errEmail'))
    void run(async () => {
      await (byPhone ? apiRequestPhoneReset(number) : apiRequestReset(address))
      setEmail(address)
      if (byPhone) setPhone(number)
      setCode('')
      setWait(RESEND_S)
      setStep('otp')
    })
  }

  const resend = () => run(async () => {
    await (byPhone ? apiRequestPhoneReset(phone) : apiRequestReset(email))
    setCode('')
    setWait(RESEND_S)
    setNotice(byPhone ? t('reset.resentPhone', { phone }) : t('reset.resent', { email }))
  })

  /** Six digits are enough to go on; the backend checks them together with the new password. */
  const next = (value: string) => {
    if (value.length < DIGITS) return setError(t('reset.otpErr'))
    setError('')
    setNotice('')
    setStep('password')
  }

  const save = (event: FormEvent) => {
    event.preventDefault()
    const next: Partial<Record<Secret, string>> = {}
    if (!PASSWORD_RULE.test(form.password)) next.password = t('reg.errPassword')
    else if (form.confirm !== form.password) next.confirm = t('reg.errConfirm')
    setErrors(next)
    if (Object.keys(next).length) return
    void run(async () => {
      try {
        await apiConfirmResetCode(byPhone ? { phone } : { email }, code, form.password)
        setStep('done')
      } catch (e) {
        // A wrong, expired or used-up code: back to the six boxes, the passwords typed are kept.
        if (e instanceof ApiError && e.code.startsWith('OTP_')) {
          setStep('otp')
          setCode('')
        }
        throw e
      }
    })
  }

  const pick = (to: Via) => {
    setVia(to)
    setError('')
    setNotice('')
  }

  const secret = (key: Secret, label: string, text?: string) => {
    const id = `forgot-${key}`
    const help = errors[key] ?? text
    return <div className="entry-register-field">
      <label htmlFor={id}>{label}</label>
      <div className="entry-login-password">
        <LockKey size={19} aria-hidden="true" />
        <input id={id} type={visible[key] ? 'text' : 'password'} autoComplete="new-password" autoFocus={key === 'password'} value={form[key]} disabled={busy}
          aria-invalid={!!errors[key]} aria-describedby={help ? `${id}-help` : undefined}
          onChange={(event) => {
            setForm((prev) => ({ ...prev, [key]: event.target.value }))
            setErrors((prev) => ({ ...prev, [key]: undefined }))
          }} />
        <button type="button" onClick={() => setVisible((prev) => ({ ...prev, [key]: !prev[key] }))} aria-pressed={visible[key]} aria-label={t(visible[key] ? 'login.hidePassword' : 'login.showPassword')}>
          {visible[key] ? <EyeSlash size={21} /> : <Eye size={21} />}
        </button>
      </div>
      {help && <span id={`${id}-help`} className={errors[key] ? 'entry-login-error' : 'entry-register-help'}>{help}</span>}
    </div>
  }

  const status = <>
    {error && <p className="entry-login-error" role="alert">{error}</p>}
    {notice && <p className="entry-login-notice" role="status">{notice}</p>}
    {busy && <p className="entry-login-notice" role="status">{t('login.waking')}</p>}
  </>

  if (step === 'start') return <>
    <h2 id="entry-login-title">{t('reset.title')}</h2>
    <p id="entry-login-description" className="entry-login-description">{t(byPhone ? 'reset.phoneLede' : 'reset.lede')}</p>
    <form onSubmit={sendCode} noValidate aria-busy={busy}>
      <div className="entry-seg" role="radiogroup" aria-label={t('reset.via')}>
        <button type="button" role="radio" aria-checked={!byPhone} className={byPhone ? '' : 'on'} disabled={busy} onClick={() => pick('email')}>
          <EnvelopeSimple size={17} aria-hidden="true" />{t('login.email')}
        </button>
        <button type="button" role="radio" aria-checked={byPhone} className={byPhone ? 'on' : ''} disabled={busy} onClick={() => pick('phone')}>
          <DeviceMobile size={17} aria-hidden="true" />{t('reset.phone')}
        </button>
      </div>
      {byPhone ? <div className="entry-register-field">
        <label htmlFor="forgot-phone">{t('reset.phone')}</label>
        <input key="phone" id="forgot-phone" type="tel" inputMode="tel" autoComplete="tel" autoFocus value={phone} disabled={busy}
          aria-describedby="forgot-phone-help" onChange={(event) => setPhone(event.target.value)} />
        <span id="forgot-phone-help" className="entry-register-help">{t('reset.phoneHelp')}</span>
      </div> : <>
        <label htmlFor="forgot-email">{t('login.email')}</label>
        <input key="email" id="forgot-email" type="email" autoComplete="username" autoFocus value={email} disabled={busy} onChange={(event) => setEmail(event.target.value)} />
      </>}
      {status}
      <button type="submit" className="entry-login-submit" disabled={busy}>{t(busy ? 'reset.sending' : 'reset.send')}</button>
      <button type="button" className="entry-login-link" disabled={busy} onClick={() => onBack()}>{t('reset.back')}</button>
    </form>
  </>

  if (step === 'otp') return <>
    <h2 id="entry-login-title">{t('reset.otpTitle')}</h2>
    <p id="entry-login-description" className="entry-login-description">{byPhone ? t('reset.otpLedePhone', { phone }) : t('reset.otpLede', { email })}</p>
    <form onSubmit={(event) => { event.preventDefault(); next(code) }} noValidate aria-busy={busy}>
      <OtpBoxes
        value={code}
        disabled={busy}
        invalid={!!error}
        onChange={(value) => {
          setCode(value)
          setError('')
          // The last digit moves on, so there is nothing more to press.
          if (value.length === DIGITS) next(value)
        }}
      />
      {status}
      <button type="submit" className="entry-login-submit" disabled={busy || code.length < DIGITS}>{t('reset.otpVerify')}</button>
      <button type="button" className="entry-login-link" disabled={busy || wait > 0} onClick={() => void resend()}>
        {wait > 0 ? t('reset.resendIn', { s: wait }) : t('reset.resend')}
      </button>
      <button type="button" className="entry-login-link" disabled={busy} onClick={() => { setStep('start'); setError(''); setNotice('') }}>{t(byPhone ? 'reset.changePhone' : 'reset.changeEmail')}</button>
    </form>
  </>

  if (step === 'password') return <>
    <h2 id="entry-login-title">{t('reset.newTitle')}</h2>
    <p id="entry-login-description" className="entry-login-description">{t('reset.pwLede')}</p>
    <form onSubmit={save} noValidate aria-busy={busy}>
      {secret('password', t('reset.newPassword'), t('reg.passwordHelp'))}
      {secret('confirm', t('reg.confirm'))}
      {status}
      <button type="submit" className="entry-login-submit" disabled={busy}>{t(busy ? 'reset.saving' : 'reset.save')}</button>
      <button type="button" className="entry-login-link" disabled={busy} onClick={() => onBack()}>{t('reset.back')}</button>
    </form>
  </>

  return <>
    <h2 id="entry-login-title">{t('reset.newTitle')}</h2>
    <p id="entry-login-description" className="entry-login-notice" role="status">{t('reset.done')}</p>
    <form onSubmit={(event) => { event.preventDefault(); onBack(byPhone ? '' : email) }}>
      <button type="submit" className="entry-login-submit" autoFocus>{t('reset.signIn')}</button>
    </form>
  </>
}
