import { useId, useState, type FormEvent, type InputHTMLAttributes } from 'react'
import { Eye, EyeSlash, LockKey } from '@phosphor-icons/react'
import { useT } from '../../i18n'
import { authErrorKey } from '../../services/api'
import { PASSWORD_RULE, PHONE_RULE, apiRegister, cleanPhone } from '../../services/auth'
import { signInWithGoogle, signInWithPassword } from '../../store/store'
import { GOOGLE_CLIENT_ID } from '../../services/google'
import GoogleButton from '../../components/ui/GoogleButton'
import type { User } from '../../types'

type Field = 'name' | 'email' | 'phone' | 'password' | 'confirm'

/** Shared by the registration page and the order-entry dialog. */
export default function RegisterForm({ onSuccess, onSignIn }: { onSuccess: (user: User) => void; onSignIn: () => void }) {
  const t = useT()
  const prefix = useId()
  const [form, setForm] = useState({ name: '', email: '', phone: '', password: '', confirm: '' })
  const [visible, setVisible] = useState({ password: false, confirm: false })
  const [errors, setErrors] = useState<Partial<Record<Field, string>>>({})
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [created, setCreated] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (busy) return
    const phone = cleanPhone(form.phone)
    const next: Partial<Record<Field, string>> = {}
    if (!form.name.trim()) next.name = t('reg.errName')
    if (!/^\S+@\S+\.\S+$/.test(form.email.trim())) next.email = t('login.errEmail')
    if (phone && !PHONE_RULE.test(phone)) next.phone = t('reg.errPhone')
    if (!PASSWORD_RULE.test(form.password)) next.password = t('reg.errPassword')
    else if (form.confirm !== form.password) next.confirm = t('reg.errConfirm')
    setErrors(next)
    setError('')
    if (Object.keys(next).length) return
    setBusy(true)
    try {
      await apiRegister({ email: form.email.trim(), password: form.password, full_name: form.name.trim(), ...(phone ? { phone } : {}) })
      setCreated(true)
      onSuccess(await signInWithPassword(form.email, form.password))
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
    try { onSuccess(await signInWithGoogle(token)) }
    catch (err) { setError(t(authErrorKey(err))) }
    finally { setBusy(false) }
  }

  const field = (key: Field, label: string, attrs: InputHTMLAttributes<HTMLInputElement>, help?: string) => {
    const id = `${prefix}-${key}`
    const secret = key === 'password' || key === 'confirm'
    const input = <input {...attrs} id={id} value={form[key]} disabled={busy || created} type={secret ? (visible[key] ? 'text' : 'password') : attrs.type}
      aria-invalid={!!errors[key]} aria-describedby={errors[key] || help ? `${id}-help` : undefined}
      onChange={(event) => { setForm((prev) => ({ ...prev, [key]: event.target.value })); setErrors((prev) => ({ ...prev, [key]: undefined })) }} />
    return <div className="entry-register-field">
      <label htmlFor={id}>{label}</label>
      {secret ? <div className="entry-login-password">
        <LockKey size={19} aria-hidden="true" />{input}
        <button type="button" onClick={() => setVisible((prev) => ({ ...prev, [key]: !prev[key] }))} aria-pressed={visible[key]} aria-label={t(visible[key] ? 'login.hidePassword' : 'login.showPassword')}>
          {visible[key] ? <EyeSlash size={21} /> : <Eye size={21} />}
        </button>
      </div> : input}
      {(errors[key] || help) && <span id={`${id}-help`} className={errors[key] ? 'entry-login-error' : 'entry-register-help'}>{errors[key] ?? help}</span>}
    </div>
  }

  return <form onSubmit={submit} noValidate aria-busy={busy}>
    {field('name', t('reg.name'), { autoComplete: 'name', autoFocus: true })}
    {field('email', t('login.email'), { type: 'email', autoComplete: 'email' })}
    {field('phone', t('reg.phone'), { type: 'tel', inputMode: 'tel', autoComplete: 'tel' })}
    {field('password', t('login.password'), { autoComplete: 'new-password' }, t('reg.passwordHelp'))}
    {field('confirm', t('reg.confirm'), { autoComplete: 'new-password' })}
    {error && <p className="entry-login-error" role="alert">{error}</p>}
    {created && <p className="entry-login-notice" role="status">{t('reg.created')}</p>}
    {!created && <button type="submit" className="entry-login-submit" disabled={busy}>{t(busy ? 'reg.creating' : 'reg.submit')}</button>}
    {busy && <p className="entry-login-notice" role="status">{t('login.waking')}</p>}
    {GOOGLE_CLIENT_ID && !created && <>
      <div className="entry-login-divider">{t('login.or')}</div>
      <GoogleButton disabled={busy} onToken={(token) => void google(token)} onError={() => setError(t('auth.err.googleDown'))} />
    </>}
    <p className="entry-login-register">{t('reg.haveAccount')}{' '}<button type="button" className="entry-register-switch" onClick={onSignIn} disabled={busy}>{t('login.title')}</button></p>
  </form>
}
