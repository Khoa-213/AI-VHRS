import { useEffect, useRef, useState, type ClipboardEvent, type FormEvent, type KeyboardEvent } from 'react'
import { Eye, EyeSlash, LockKey } from '@phosphor-icons/react'
import { useT } from '../../i18n'
import { ApiError, authErrorKey } from '../../services/api'
import { PASSWORD_RULE, apiConfirmResetCode, apiRequestReset } from '../../services/auth'

const DIGITS = 6
/** Seconds before another code may be asked for (the backend keeps the same wait between two codes). */
const RESEND_S = 60

/** Six boxes for the emailed code. Typing moves on, Backspace moves back, and a pasted or autofilled code fills them all. */
function OtpBoxes({ value, disabled, invalid, onChange }: {
  value: string
  disabled: boolean
  invalid: boolean
  onChange: (code: string) => void
}) {
  const t = useT()
  const boxes = useRef<(HTMLInputElement | null)[]>([])
  const focus = (i: number) => boxes.current[Math.max(0, Math.min(DIGITS - 1, i))]?.focus()

  useEffect(() => {
    boxes.current[0]?.focus()
  }, [])

  /** Writes `digits` from box `at` on, over what was there. */
  const put = (at: number, digits: string) => {
    const next = (value.slice(0, at) + digits + value.slice(at + digits.length)).slice(0, DIGITS)
    onChange(next)
    focus(Math.min(at + digits.length, DIGITS - 1))
  }

  const key = (i: number, e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Backspace') {
      e.preventDefault()
      if (value[i]) onChange(value.slice(0, i))
      else if (i > 0) {
        onChange(value.slice(0, i - 1))
        focus(i - 1)
      }
    } else if (e.key === 'ArrowLeft') focus(i - 1)
    else if (e.key === 'ArrowRight') focus(i + 1)
  }

  const paste = (e: ClipboardEvent<HTMLInputElement>) => {
    const digits = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, DIGITS)
    if (!digits) return
    e.preventDefault()
    onChange(digits)
    focus(digits.length)
  }

  return (
    <div className="entry-otp" role="group" aria-label={t('reset.otpLabel')}>
      {Array.from({ length: DIGITS }, (_, i) => (
        <input
          key={i}
          ref={(el) => { boxes.current[i] = el }}
          type="text"
          inputMode="numeric"
          pattern="[0-9]*"
          autoComplete={i === 0 ? 'one-time-code' : 'off'}
          maxLength={DIGITS}
          value={value[i] ?? ''}
          disabled={disabled}
          aria-label={t('reset.otpDigit', { n: i + 1 })}
          aria-invalid={invalid}
          onFocus={(e) => e.target.select()}
          onKeyDown={(e) => key(i, e)}
          onPaste={paste}
          onChange={(e) => {
            const digits = e.target.value.replace(/\D/g, '')
            // Boxes fill in order: a digit typed further along goes to the first empty box.
            if (digits) put(Math.min(i, value.length), digits)
          }}
        />
      ))}
    </div>
  )
}

type Step = 'email' | 'otp' | 'password' | 'done'
type Job = { (): Promise<void> }
type Secret = 'password' | 'confirm'

/**
 * "Forgot password" inside the sign-in dialog: the email, then the 6-digit code that was emailed, then the new password.
 * The backend checks the code and sets the password in one call (`POST /auth/password-reset/confirm {email, code,
 * new_password}`), so a wrong or expired code is reported after the password step and brings the six boxes back.
 */
export default function ForgotPassword({ initialEmail, onBack }: {
  initialEmail: string
  /** Back to the sign-in form; after a reset the email is passed on so it is already filled in. */
  onBack: (email?: string) => void
}) {
  const t = useT()
  const [step, setStep] = useState<Step>('email')
  const [email, setEmail] = useState(initialEmail)
  const [code, setCode] = useState('')
  const [form, setForm] = useState({ password: '', confirm: '' })
  const [visible, setVisible] = useState({ password: false, confirm: false })
  const [errors, setErrors] = useState<Partial<Record<Secret, string>>>({})
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [wait, setWait] = useState(0)

  useEffect(() => {
    if (wait <= 0) return
    const id = window.setTimeout(() => setWait((s) => s - 1), 1000)
    return () => window.clearTimeout(id)
  }, [wait])

  const fail = (e: unknown) => setError(t(authErrorKey(e)))

  const run = async (job: Job) => {
    if (busy) return
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await job()
    } catch (e) {
      fail(e)
    } finally {
      setBusy(false)
    }
  }

  const sendCode = (event: FormEvent) => {
    event.preventDefault()
    const address = email.trim()
    if (!/^\S+@\S+\.\S+$/.test(address)) return setError(t('login.errEmail'))
    void run(async () => {
      await apiRequestReset(address)
      setEmail(address)
      setCode('')
      setWait(RESEND_S)
      setStep('otp')
    })
  }

  const resend = () => run(async () => {
    await apiRequestReset(email)
    setCode('')
    setWait(RESEND_S)
    setNotice(t('reset.resent', { email }))
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
        await apiConfirmResetCode(email, code, form.password)
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

  if (step === 'email') return <>
    <h2 id="entry-login-title">{t('reset.title')}</h2>
    <p id="entry-login-description" className="entry-login-description">{t('reset.lede')}</p>
    <form onSubmit={sendCode} noValidate aria-busy={busy}>
      <label htmlFor="forgot-email">{t('login.email')}</label>
      <input id="forgot-email" type="email" autoComplete="username" autoFocus value={email} disabled={busy} onChange={(event) => setEmail(event.target.value)} />
      {status}
      <button type="submit" className="entry-login-submit" disabled={busy}>{t(busy ? 'reset.sending' : 'reset.send')}</button>
      <button type="button" className="entry-login-link" disabled={busy} onClick={() => onBack()}>{t('reset.back')}</button>
    </form>
  </>

  if (step === 'otp') return <>
    <h2 id="entry-login-title">{t('reset.otpTitle')}</h2>
    <p id="entry-login-description" className="entry-login-description">{t('reset.otpLede', { email })}</p>
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
      <button type="button" className="entry-login-link" disabled={busy} onClick={() => { setStep('email'); setError(''); setNotice('') }}>{t('reset.changeEmail')}</button>
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
    <form onSubmit={(event) => { event.preventDefault(); onBack(email) }}>
      <button type="submit" className="entry-login-submit" autoFocus>{t('reset.signIn')}</button>
    </form>
  </>
}
