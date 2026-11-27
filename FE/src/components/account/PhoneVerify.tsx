import { useEffect, useRef, useState } from 'react'
import { useLang, useT } from '../../i18n'
import OtpBoxes, { OTP_DIGITS } from '../../pages/login/OtpBoxes'
import { ApiError, authErrorKey } from '../../services/api'
import { apiSendPhoneOtp, maskPhone } from '../../services/auth'
import { FirebasePhoneError, cancelPhoneCode, firebasePhoneEnabled, sendPhoneCode, type PhoneCode } from '../../services/firebasePhone'
import { useUser, verifyPhone, verifyPhoneFirebase } from '../../store/store'
import './phone-verify.css'

type T = ReturnType<typeof useT>
type Job = { (): Promise<void> }

/** Seconds before another code may be asked for when Firebase sends it (the backend's own flow answers its wait). */
const FIREBASE_RESEND_S = 60

/** The backend's answers about codes and SMS, in the reader's language (`BE/docs/FE_API_GUIDE.md` 3.2). */
function phoneErrorText(t: T, e: unknown): string {
  if (e instanceof FirebasePhoneError) return t(e.key)
  if (!(e instanceof ApiError)) return t(authErrorKey(e))
  const details = (e.details ?? {}) as { attempts_left?: unknown; retry_after?: unknown }
  switch (e.code) {
    case 'OTP_INVALID': return typeof details.attempts_left === 'number' ? t('ph.err.invalidLeft', { n: details.attempts_left }) : t('auth.err.otpInvalid')
    case 'OTP_RESEND_TOO_SOON': return t('ph.err.soon', { s: typeof details.retry_after === 'number' ? details.retry_after : 60 })
    case 'OTP_DAILY_LIMIT': return t('ph.err.daily')
    case 'PHONE_TAKEN': return t('ph.err.taken')
    case 'PHONE_ALREADY_VERIFIED': return t('ph.err.already')
    case 'PHONE_MISSING': return t('ph.err.missing')
    case 'SMS_NOT_CONFIGURED':
    case 'SMS_UNAVAILABLE':
    case 'SMS_REJECTED': return t('ph.err.sms')
  }
  return t(authErrorKey(e))
}

/**
 * Verifies the phone number of the signed-in account: `POST /me/phone/otp` sends a 6-digit code by SMS, the six boxes take
 * it and `POST /me/phone/verify` marks the number verified (the sixth digit sends it). Used in Account > Profile and in the
 * reminder after sign-in. A code is only sent after a click, or at once with `autoSend` when the click already happened.
 * `look` picks the buttons of the place it sits in.
 *
 * With Firebase set up (`services/firebasePhone.ts`, 2026-11-27) Google sends and checks the code instead: the six boxes
 * confirm it with Firebase and the ID token goes to `POST /me/phone/verify-firebase`. The screen is the same.
 */
export default function PhoneVerify({ look, autoSend = false, cancelLabel, onVerified, onCancel }: {
  look: 'page' | 'dialog'
  autoSend?: boolean
  cancelLabel: string
  onVerified: () => void
  onCancel: () => void
}) {
  const t = useT()
  const lang = useLang()
  const user = useUser()
  const phone = user?.phone ?? ''
  /** The code Firebase texted, waiting for the six digits. */
  const pending = useRef<PhoneCode | null>(null)
  const [sent, setSent] = useState<{ masked: string; mock: boolean } | null>(null)
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState<'send' | 'check' | null>(null)
  const [error, setError] = useState('')
  const [wait, setWait] = useState(0)
  const started = useRef(false)

  useEffect(() => {
    if (wait <= 0) return
    const id = window.setTimeout(() => setWait((s) => s - 1), 1000)
    return () => window.clearTimeout(id)
  }, [wait])

  const run = async (kind: 'send' | 'check', job: Job) => {
    if (busy) return
    setBusy(kind)
    setError('')
    try {
      await job()
    } catch (e) {
      setError(phoneErrorText(t, e))
      // A code asked for less than a minute ago is still good: show the boxes and count the wait down.
      if (e instanceof ApiError && e.code === 'OTP_RESEND_TOO_SOON') {
        const s = (e.details as { retry_after?: unknown } | null)?.retry_after
        setWait(typeof s === 'number' ? s : 60)
        setSent((prev) => prev ?? { masked: maskPhone(phone), mock: false })
      }
      if (kind === 'check') setCode('')
    } finally {
      setBusy(null)
    }
  }

  const send = () => run('send', async () => {
    if (firebasePhoneEnabled) {
      pending.current = await sendPhoneCode(phone, lang)
      setSent({ masked: maskPhone(phone), mock: false })
      setCode('')
      setWait(FIREBASE_RESEND_S)
      return
    }
    const r = await apiSendPhoneOtp()
    setSent({ masked: r.phoneMasked, mock: r.mode === 'MOCK' })
    setCode('')
    setWait(r.resendAfter)
  })

  const check = (value: string) => run('check', async () => {
    if (firebasePhoneEnabled) {
      if (!pending.current) throw new FirebasePhoneError('auth.err.otpExpired', 'no-code')
      const token = await pending.current.confirm(value)
      pending.current = null
      await verifyPhoneFirebase(token)
    } else {
      await verifyPhone(value)
    }
    onVerified()
  })

  // The reCAPTCHA widget of a code that was never typed goes with the panel.
  useEffect(() => cancelPhoneCode, [])

  useEffect(() => {
    if (!autoSend || started.current) return
    started.current = true
    void send()
    // Once, when the panel opens after the click that asked for it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoSend])

  const primary = look === 'dialog' ? 'entry-login-submit' : 'co-btn co-btn--solid co-btn--sm'
  const link = look === 'dialog' ? 'entry-login-link' : 'vh-link phv-link'

  return (
    <div className={`phv phv--${look}`} aria-busy={!!busy}>
      {sent ? (
        <>
          <p className="phv-note" role="status">{t(firebasePhoneEnabled ? 'ph.sentFirebase' : 'ph.sent', { phone: sent.masked })}</p>
          {sent.mock && <p className="phv-note phv-note--warn" role="note">{t('ph.mock')}</p>}
          <OtpBoxes
            value={code}
            disabled={busy === 'check'}
            invalid={!!error}
            onChange={(value) => {
              setCode(value)
              setError('')
              // The last digit sends the code, so there is nothing more to press.
              if (value.length === OTP_DIGITS) void check(value)
            }}
          />
          {busy === 'check' && <p className="phv-note" role="status">{t('ph.checking')}</p>}
        </>
      ) : (
        busy === 'send' && <p className="phv-note" role="status">{t('ph.sending')}</p>
      )}
      {error && <p className="phv-error" role="alert">{error}</p>}
      <div className="phv-actions">
        {!sent && <button type="button" className={primary} disabled={!!busy} onClick={() => void send()}>{t(busy === 'send' ? 'ph.sending' : 'ph.send')}</button>}
        {sent && (
          <button type="button" className={link} disabled={!!busy || wait > 0} onClick={() => void send()}>
            {wait > 0 ? t('reset.resendIn', { s: wait }) : t('reset.resend')}
          </button>
        )}
        <button type="button" className={link} disabled={busy === 'check'} onClick={onCancel}>{cancelLabel}</button>
      </div>
    </div>
  )
}
