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

interface TokenOut {
  access_token: string
  refresh_token: string
  account: Account
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
    apiRole: a.role,
    role,
  }
}

/** `POST /auth/login`: stores the tokens and returns the user. */
export async function apiLogin(email: string, password: string): Promise<User> {
  const r = await api<TokenOut>('/auth/login', { method: 'POST', body: { email, password }, auth: false })
  setTokens({ access: r.access_token, refresh: r.refresh_token })
  return toUser(r.account)
}

/** `POST /auth/google`: customers only. The backend verifies the Google ID token; a first sign-in creates the account. */
export async function apiGoogleLogin(idToken: string): Promise<User> {
  const r = await api<TokenOut>('/auth/google', { method: 'POST', body: { id_token: idToken }, auth: false })
  setTokens({ access: r.access_token, refresh: r.refresh_token })
  return toUser(r.account)
}

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

/** `POST /me/change-password`: signs out the other devices. */
export const apiChangePassword = (current_password: string, new_password: string) =>
  api('/me/change-password', { method: 'POST', body: { current_password, new_password } })

/** `POST /auth/password-reset/request`: always answers 202, whether or not the email exists. */
export const apiRequestReset = (email: string) =>
  api('/auth/password-reset/request', { method: 'POST', body: { email }, auth: false })

/** Same rules as the backend. */
export const PASSWORD_RULE = /^(?=.*[A-Za-z])(?=.*\d).{8,72}$/
export const PHONE_RULE = /^(0|\+84)\d{9}$/
export const cleanPhone = (s: string) => s.replace(/[\s\-().]/g, '')
