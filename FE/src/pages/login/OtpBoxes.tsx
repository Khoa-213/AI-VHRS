import { useEffect, useRef, type ClipboardEvent, type KeyboardEvent } from 'react'
import { useT } from '../../i18n'
import './otp-boxes.css'

/** The emailed reset code has this many digits. */
export const OTP_DIGITS = 6

/** Six boxes for the emailed code. Typing moves on, Backspace moves back, and a pasted or autofilled code fills them all. */
export default function OtpBoxes({ value, disabled, invalid, autoFocus = true, onChange }: {
  value: string
  disabled: boolean
  invalid: boolean
  /** Focus the first box when it appears (off when another field comes first). */
  autoFocus?: boolean
  onChange: (code: string) => void
}) {
  const t = useT()
  const boxes = useRef<(HTMLInputElement | null)[]>([])
  const focus = (i: number) => boxes.current[Math.max(0, Math.min(OTP_DIGITS - 1, i))]?.focus()

  const first = useRef(autoFocus)
  useEffect(() => {
    if (first.current) boxes.current[0]?.focus()
  }, [])

  /** Writes `digits` from box `at` on, over what was there. */
  const put = (at: number, digits: string) => {
    const next = (value.slice(0, at) + digits + value.slice(at + digits.length)).slice(0, OTP_DIGITS)
    onChange(next)
    focus(Math.min(at + digits.length, OTP_DIGITS - 1))
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
    const digits = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, OTP_DIGITS)
    if (!digits) return
    e.preventDefault()
    onChange(digits)
    focus(digits.length)
  }

  return (
    <div className="entry-otp" role="group" aria-label={t('reset.otpLabel')}>
      {Array.from({ length: OTP_DIGITS }, (_, i) => (
        <input
          key={i}
          ref={(el) => { boxes.current[i] = el }}
          type="text"
          inputMode="numeric"
          pattern="[0-9]*"
          autoComplete={i === 0 ? 'one-time-code' : 'off'}
          maxLength={OTP_DIGITS}
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
