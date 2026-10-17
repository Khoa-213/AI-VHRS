import { useState, type FormEvent } from 'react'
import { useT } from '../../i18n'
import SkipLink from '../../components/ui/SkipLink'
import ThemeToggle from '../../components/ui/ThemeToggle'
import LanguageToggle from '../../components/ui/LanguageToggle'
import { Link, navigate } from '../../router/router'
import { authErrorKey } from '../../services/api'
import { PASSWORD_RULE, PHONE_RULE, apiRegister, cleanPhone } from '../../services/auth'
import { signInWithPassword } from '../../store/store'
import './login.css'
import '../staff/polish.css'

const EMAIL = /^\S+@\S+\.\S+$/

type Field = 'name' | 'email' | 'phone' | 'password' | 'confirm'

/** Customer sign-up (`POST /auth/register`), then signs in with the new account. */
export default function Register() {
  const t = useT()
  const [form, setForm] = useState({ name: '', email: '', phone: '', password: '', confirm: '' })
  const [errors, setErrors] = useState<Partial<Record<Field, string>>>({})
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const set = (k: Field, v: string) => {
    setForm((f) => ({ ...f, [k]: v }))
    setErrors((e) => ({ ...e, [k]: undefined }))
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (busy) return
    const phone = cleanPhone(form.phone)
    const next: Partial<Record<Field, string>> = {}
    if (!form.name.trim()) next.name = t('reg.errName')
    if (!EMAIL.test(form.email.trim())) next.email = t('login.errEmail')
    if (phone && !PHONE_RULE.test(phone)) next.phone = t('reg.errPhone')
    if (!PASSWORD_RULE.test(form.password)) next.password = t('reg.errPassword')
    else if (form.confirm !== form.password) next.confirm = t('reg.errConfirm')
    setErrors(next)
    setError('')
    if (Object.keys(next).length) return

    setBusy(true)
    try {
      await apiRegister({
        email: form.email.trim(),
        password: form.password,
        full_name: form.name.trim(),
        ...(phone ? { phone } : {}),
      })
      await signInWithPassword(form.email, form.password)
      navigate('/')
    } catch (err) {
      setError(t(authErrorKey(err)))
    } finally {
      setBusy(false)
    }
  }

  const field = (k: Field, label: string, input: React.InputHTMLAttributes<HTMLInputElement>, help?: string) => (
    <label className="vh-label" htmlFor={`rg-${k}`}>
      {label}
      <input
        id={`rg-${k}`}
        className="vh-input"
        value={form[k]}
        disabled={busy}
        aria-invalid={!!errors[k]}
        aria-describedby={errors[k] || help ? `rg-${k}-help` : undefined}
        onChange={(e) => set(k, e.target.value)}
        {...input}
      />
      {(errors[k] || help) && (
        <span id={`rg-${k}-help`} className={errors[k] ? 'lg-error' : 'lg-field-help'}>{errors[k] ?? help}</span>
      )}
    </label>
  )

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
            <h1>{t('reg.title')}</h1>
            <p>{t('reg.lede')}</p>
          </div>

          {field('name', t('reg.name'), { autoComplete: 'name' })}
          {field('email', t('login.email'), { type: 'email', autoComplete: 'email', placeholder: 'you@example.com' })}
          {field('phone', t('reg.phone'), { type: 'tel', inputMode: 'tel', autoComplete: 'tel', placeholder: '0901 234 567' })}
          {field('password', t('login.password'), { type: 'password', autoComplete: 'new-password' }, t('reg.passwordHelp'))}
          {field('confirm', t('reg.confirm'), { type: 'password', autoComplete: 'new-password' })}

          {error && <p className="lg-error" role="alert">{error}</p>}

          <button type="submit" className="vh-btn vh-btn--primary" disabled={busy}>
            {t(busy ? 'reg.creating' : 'reg.submit')}
          </button>
          {busy && <p className="lg-note" role="status">{t('login.waking')}</p>}

          <div className="lg-links">
            <span>
              {t('reg.haveAccount')} <Link to="/login" className="vh-link">{t('login.title')}</Link>
            </span>
          </div>
        </form>
      </main>
    </div>
  )
}
