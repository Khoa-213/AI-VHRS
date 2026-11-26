import type { Role, User } from '../types'
import { api, setTokens } from './api'

/** Account as the backend returns it (`AccountOut`). */
export interface Account {
  id: number
  email: string
  full_name: string
  phone: string | null
  phone_verified: boolean
  role: string
  status: string
  addresses: unknown[]
  created_at: string
  last_login_at: string | null
}

/** What a sign-in may ask the person to do next (`TokenOut.reminders`, 2026-11-26); usually nothing. */
export type PhoneReminder = 'ADD_PHONE' | 'VERIFY_PHONE'

interface TokenOut {
  access_token: string
  refresh_token: string
  account: Account
  /** Reminders created by this sign-in; missing on older backends. */
  reminders?: string[]
}

export interface SignedIn { user: User; reminder: PhoneReminder | null }

const signedIn = (r: TokenOut): SignedIn => {
  setTokens({ access: r.access_token, refresh: r.refresh_token })
  const reminder = (r.reminders ?? []).find((x): x is PhoneReminder => x === 'ADD_PHONE' || x === 'VERIFY_PHONE') ?? null
  return { user: toUser(r.account), reminder }
}

/** Backend roles mapped onto the four areas of the site. */
const AREA: Record<string, Role> = {
  CUSTOMER: 'customer',
  TECHNICAL_STAFF: 'technician',
  STAFF: 'staff',
  MANAGER: 'staff',
  ADMIN: 'admin',
}

export function toUser(a: Account): User {
  const role = AREA[a.role] ?? 'customer'
  return {
    id: a.id,
    name: a.full_name,
    email: a.email,
    phone: a.phone,
    phoneVerified: a.phone_verified,
    apiRole: a.role,
    role,
  }
}

/** `POST /auth/login`: stores the tokens and returns the user, with the phone reminder of this sign-in if any. */
export const apiLogin = async (email: string, password: string): Promise<SignedIn> =>
  signedIn(await api<TokenOut>('/auth/login', { method: 'POST', body: { email, password }, auth: false }))

/** `POST /auth/google`: customers only. The backend verifies the Google ID token; a first sign-in creates the account. */
export const apiGoogleLogin = async (idToken: string): Promise<SignedIn> =>
  signedIn(await api<TokenOut>('/auth/google', { method: 'POST', body: { id_token: idToken }, auth: false }))

/** `POST /auth/register`: creates a customer account (no tokens; sign in afterwards). */
export const apiRegister = (body: { email: string; password: string; full_name: string; phone?: string }) =>
  api<Account>('/auth/register', { method: 'POST', body, auth: false })

/** `POST /auth/logout`: revokes this session. Local tokens are cleared even if the call fails. */
export async function apiLogout() {
  try {
    await api('/auth/logout', { method: 'POST' })
  } catch {
    // Offline or already revoked.
  }
  setTokens(null)
}

/** `GET /me` */
export const apiMe = async () => toUser(await api<Account>('/me'))

/** `PATCH /me`: only the fields given change. */
export const apiUpdateMe = async (patch: { full_name?: string; phone?: string | null }) =>
  toUser(await api<Account>('/me', { method: 'PATCH', body: patch }))

/**
 * `POST /me/phone/otp`: texts a 6-digit code to the account's unverified number (5 minutes, 60 s between two codes, 5 a
 * day). `mode` is `MOCK` when the server sends no real SMS. Errors: `PHONE_MISSING`, `PHONE_ALREADY_VERIFIED`,
 * `PHONE_TAKEN`, `OTP_RESEND_TOO_SOON` (`details.retry_after`), `OTP_DAILY_LIMIT`, `SMS_*`.
 */
export async function apiSendPhoneOtp(): Promise<{ phoneMasked: string; expiresIn: number; resendAfter: number; mode: string }> {
  const r = await api<{ phone_masked: string; expires_in: number; resend_after: number; mode: string }>('/me/phone/otp', { method: 'POST' })
  return { phoneMasked: r.phone_masked, expiresIn: r.expires_in, resendAfter: r.resend_after, mode: r.mode }
}

/** `POST /me/phone/verify`: the code marks the number verified and the account comes back. Errors: `OTP_*`, `PHONE_TAKEN`. */
export const apiVerifyPhone = async (code: string) =>
  toUser(await api<Account>('/me/phone/verify', { method: 'POST', body: { code } }))

/** `POST /me/change-password`: signs out the other devices. */
export const apiChangePassword = (current_password: string, new_password: string) =>
  api('/me/change-password', { method: 'POST', body: { current_password, new_password } })

/** `POST /auth/password-reset/request`: always answers 202, whether or not the email exists. */
export const apiRequestReset = (email: string) =>
  api('/auth/password-reset/request', { method: 'POST', body: { email }, auth: false })

/**
 * `POST /auth/phone-reset/request`: a code by SMS to a number verified on an active account. Always answers 202 (unknown
 * or unverified number, resend wait, daily limit, SMS failure), so nothing tells whether the number has an account.
 */
export const apiRequestPhoneReset = (phone: string) =>
  api('/auth/phone-reset/request', { method: 'POST', body: { phone }, auth: false })

/**
 * `POST /auth/password-reset/confirm` with the 6-digit code that went to the email or to the phone
 * (`BE/docs/FE_API_GUIDE.md`, 2026-11-26): the code is checked and the password set in one call; send the email or the
 * phone, never both. Errors: `OTP_INVALID` (`details.attempts_left`), `OTP_EXPIRED`, `OTP_TOO_MANY_ATTEMPTS`.
 * Signs out every device. There is no reset token any more.
 */
export const apiConfirmResetCode = (to: { email: string } | { phone: string }, code: string, new_password: string) =>
  api('/auth/password-reset/confirm', { method: 'POST', body: { ...to, code, new_password }, auth: false })

/** Same rules as the backend. */
export const PASSWORD_RULE = /^(?=.*[A-Za-z])(?=.*\d).{8,72}$/
export const PHONE_RULE = /^(0|\+84)\d{9}$/
export const cleanPhone = (s: string) => s.replace(/[\s\-().]/g, '')
/** `0901234567` as `090****567`, the way the backend masks it. */
export const maskPhone = (phone: string) => (phone.length > 6 ? `${phone.slice(0, 3)}****${phone.slice(-3)}` : phone)
