import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useT } from '../../i18n'
import { authErrorKey } from '../../services/api'
import { PHONE_RULE, cleanPhone, maskPhone } from '../../services/auth'
import { dismissPhoneReminder, saveAccount, usePhoneReminder, useUser } from '../../store/store'
import PhoneVerify from './PhoneVerify'
import '../../pages/create-order/sign-in-dialog.css'

type Step = 'add' | 'verify' | 'done'

/**
 * The prompt that opens after a sign-in when the backend lists a reminder (`TokenOut.reminders`, 2026-11-26):
 * `ADD_PHONE` asks for a number (`PATCH /me`) and goes on to verify it; `VERIFY_PHONE` goes straight to the verification.
 * "Later" closes it; the same reminder stays in the bell, which opens Account > Profile.
 */
export default function PhoneReminderDialog() {
  const reminder = usePhoneReminder()
  const user = useUser()
  if (!reminder || !user) return null
  // Nothing to ask when the account already has a verified number, or has no number to verify.
  if (reminder === 'VERIFY_PHONE' && (!user.phone || user.phoneVerified)) return null
  return <Prompt key={reminder} first={reminder === 'ADD_PHONE' ? 'add' : 'verify'} />
}

function Prompt({ first }: { first: Step }) {
  const t = useT()
  const user = useUser()
  const dialog = useRef<HTMLDialogElement>(null)
  const [step, setStep] = useState<Step>(first)
  const [phone, setPhone] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  // After "Continue" on the number the code is sent at once; a plain "verify" reminder waits for the button.
  const [autoSend, setAutoSend] = useState(false)

  useEffect(() => {
    const el = dialog.current!
    const previousOverflow = document.body.style.overflow
    el.showModal()
    document.body.style.overflow = 'hidden'
    return () => {
      el.close()
      document.body.style.overflow = previousOverflow
    }
  }, [])

  const add = async (event: FormEvent) => {
    event.preventDefault()
    if (busy) return
    const number = cleanPhone(phone)
    if (!PHONE_RULE.test(number)) return setError(t('reset.errPhone'))
    setBusy(true)
    setError('')
    try {
      await saveAccount({ phone: number })
      setAutoSend(true)
      setStep('verify')
    } catch (e) {
      setError(t(authErrorKey(e)))
    } finally {
      setBusy(false)
    }
  }

  return (
    <dialog ref={dialog} className="entry-login" aria-labelledby="phone-reminder-title"
      onCancel={dismissPhoneReminder} onClick={(event) => { if (event.target === event.currentTarget) dismissPhoneReminder() }}>
      <div className="entry-login-panel">
        <span className="entry-login-brand">AI-VHRS</span>
        {step === 'add' && <>
          <h2 id="phone-reminder-title">{t('ph.addTitle')}</h2>
          <p className="entry-login-description">{t('ph.addLede')}</p>
          <form onSubmit={add} noValidate aria-busy={busy}>
            <label htmlFor="phone-reminder-number">{t('reset.phone')}</label>
            <input id="phone-reminder-number" type="tel" inputMode="tel" autoComplete="tel" autoFocus value={phone} disabled={busy}
              onChange={(event) => { setPhone(event.target.value); setError('') }} />
            {error && <p className="entry-login-error" role="alert">{error}</p>}
            <button type="submit" className="entry-login-submit" disabled={busy}>{t(busy ? 'acct.p.saving' : 'ph.addNext')}</button>
            <button type="button" className="entry-login-link" disabled={busy} onClick={dismissPhoneReminder}>{t('ph.later')}</button>
          </form>
        </>}
        {step === 'verify' && <>
          <h2 id="phone-reminder-title">{t('ph.verifyTitle')}</h2>
          <p className="entry-login-description">{t('ph.verifyLede', { phone: maskPhone(user?.phone ?? '') })}</p>
          <PhoneVerify look="dialog" autoSend={autoSend} cancelLabel={t('ph.later')} onVerified={() => setStep('done')} onCancel={dismissPhoneReminder} />
        </>}
        {step === 'done' && <>
          <h2 id="phone-reminder-title">{t('ph.verifyTitle')}</h2>
          <p className="entry-login-notice" role="status">{t('ph.done')}</p>
          <form onSubmit={(event) => { event.preventDefault(); dismissPhoneReminder() }}>
            <button type="submit" className="entry-login-submit" autoFocus>{t('common.close')}</button>
          </form>
        </>}
      </div>
    </dialog>
  )
}
