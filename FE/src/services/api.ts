/**
 * Thin client for the AI-VHRS backend (https://ai-vhrs.onrender.com/docs).
 *
 * - Base URL from `VITE_API_BASE_URL`; otherwise `/api/v1` through the Vite proxy in dev and
 *   the Render deployment in production builds.
 * - Sends the access token, refreshes it once on a 401 and retries.
 * - Errors come back as `{"error": {"code", "message", "details"}}` and are
 *   thrown as `ApiError`, whose `code` the UI translates (see `authErrorKey`).
 */

export const API_BASE: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ??
  // Dev: same origin, forwarded by the Vite proxy (vite.config.ts). Build: the deployed API,
  // which must list the site's origin in CORS_ORIGINS on Render.
  (import.meta.env.DEV ? '/api/v1' : 'https://ai-vhrs.onrender.com/api/v1')

/** The free Render plan sleeps when idle; waking it can take close to a minute. */
const TIMEOUT_MS = 75_000

const TOKENS_KEY = 'aivhrs-auth'

export interface Tokens {
  access: string
  refresh: string
}

export class ApiError extends Error {
  readonly status: number
  /** Backend code, e.g. `INVALID_CREDENTIALS`; `NETWORK` or `TIMEOUT` when the request never got an answer. */
  readonly code: string
  readonly details: unknown
  readonly retryAfterMs?: number

  constructor(status: number, code: string, message: string, details?: unknown, retryAfterMs?: number) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
    this.retryAfterMs = retryAfterMs
  }
}

export function getTokens(): Tokens | null {
  try {
    const t = JSON.parse(localStorage.getItem(TOKENS_KEY) ?? 'null') as Tokens | null
    return t?.access && t.refresh ? t : null
  } catch {
    return null
  }
}

export function setTokens(t: Tokens | null) {
  try {
    if (t) localStorage.setItem(TOKENS_KEY, JSON.stringify(t))
    else localStorage.removeItem(TOKENS_KEY)
  } catch {
    // Storage blocked: the session lasts until the tab closes.
  }
}

/** Called once when the refresh token is rejected too, so the app can sign out. */
let onExpired: (() => void) | null = null
export const onSessionExpired = (fn: () => void) => {
  onExpired = fn
}

interface Options {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'
  body?: unknown
  /** Send the access token (default true). Public endpoints set false. */
  auth?: boolean
  /** Use this token instead of the stored one. */
  token?: string
}

async function send(path: string, { method = 'GET', body, auth = true, token }: Options): Promise<Response> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const bearer = token ?? (auth ? getTokens()?.access : undefined)
  if (bearer) headers.Authorization = `Bearer ${bearer}`

  const ctrl = new AbortController()
  const timer = window.setTimeout(() => ctrl.abort(), TIMEOUT_MS)
  try {
    return await fetch(API_BASE + path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: ctrl.signal,
    })
  } catch (e) {
    if (ctrl.signal.aborted) throw new ApiError(0, 'TIMEOUT', 'Request timed out')
    throw new ApiError(0, 'NETWORK', e instanceof Error ? e.message : 'Network error')
  } finally {
    window.clearTimeout(timer)
  }
}

async function toError(res: Response): Promise<ApiError> {
  let code = `HTTP_${res.status}`
  let message = res.statusText
  let details: unknown
  try {
    const data = (await res.json()) as { error?: { code?: string; message?: string; details?: unknown } }
    if (data.error) {
      code = data.error.code ?? code
      message = data.error.message ?? message
      details = data.error.details
    }
  } catch {
    // Not JSON: keep the status text.
  }
  const retry = res.headers.get('Retry-After')
  const retryAfterMs = retry === null ? undefined : Math.max(0,
    Number.isFinite(Number(retry)) ? Number(retry) * 1000 : Date.parse(retry) - Date.now())
  return new ApiError(res.status, code, message, details, Number.isFinite(retryAfterMs) ? retryAfterMs : undefined)
}

// One refresh at a time: parallel 401s wait for the same promise.
let refreshing: Promise<boolean> | null = null

function refreshTokens(): Promise<boolean> {
  refreshing ??= (async () => {
    const t = getTokens()
    if (!t) return false
    try {
      const res = await send('/auth/refresh', { method: 'POST', body: { refresh_token: t.refresh }, auth: false })
      if (!res.ok) return false
      const data = (await res.json()) as { access_token: string; refresh_token: string }
      setTokens({ access: data.access_token, refresh: data.refresh_token })
      return true
    } catch {
      return false
    }
  })().finally(() => {
    refreshing = null
  })
  return refreshing
}

/** JSON request. Resolves to `undefined` for empty answers (204). */
export async function api<T = unknown>(path: string, opts: Options = {}): Promise<T> {
  let res = await send(path, opts)
  const canRefresh = (opts.auth ?? true) && !opts.token && getTokens() !== null
  if (res.status === 401 && canRefresh) {
    if (await refreshTokens()) {
      res = await send(path, opts)
    } else {
      setTokens(null)
      onExpired?.()
    }
  }
  if (!res.ok) throw await toError(res)
  if (res.status === 204) return undefined as T
  const text = await res.text()
  return (text ? JSON.parse(text) : undefined) as T
}

/** Translation key for an error from the API (keys live under `auth.err.`). */
export function authErrorKey(e: unknown): string {
  if (!(e instanceof ApiError)) return 'auth.err.unknown'
  switch (e.code) {
    case 'INVALID_CREDENTIALS': return 'auth.err.credentials'
    case 'GOOGLE_TOKEN_INVALID': return 'auth.err.googleInvalid'
    case 'GOOGLE_EMAIL_NOT_VERIFIED': return 'auth.err.googleUnverified'
    case 'GOOGLE_NOT_ALLOWED': return 'auth.err.googleNotAllowed'
    case 'GOOGLE_NOT_CONFIGURED':
    case 'GOOGLE_UNAVAILABLE': return 'auth.err.googleDown'
    case 'ACCOUNT_DISABLED': return 'auth.err.disabled'
    case 'ACCOUNT_TEMP_LOCKED': return 'auth.err.locked'
    case 'RATE_LIMITED': return 'auth.err.rate'
    case 'EMAIL_TAKEN': return 'auth.err.emailTaken'
    case 'WEAK_PASSWORD': return 'auth.err.weak'
    case 'WRONG_PASSWORD': return 'auth.err.wrongPassword'
    case 'VALIDATION_ERROR': return 'auth.err.validation'
    case 'TOKEN_EXPIRED':
    case 'TOKEN_INVALID': return 'auth.err.link'
    case 'TIMEOUT': return 'auth.err.timeout'
    case 'NETWORK': return 'auth.err.network'
  }
  return e.status >= 500 ? 'auth.err.server' : 'auth.err.unknown'
}

/**
 * Loads every page of a paged list. Several backend lists come oldest first, so the newest rows sit on the last page:
 * read them all before sorting, or a new row never shows.
 */
export async function allPages<T>(load: (page: number) => Promise<{ items: T[]; total: number }>, pageSize: number): Promise<T[]> {
  const out: T[] = []
  for (let page = 1; ; page++) {
    const r = await load(page)
    out.push(...r.items)
    if (!r.items.length || page * pageSize >= r.total) return out
  }
}

/** Newest first by the given ISO timestamp (missing ones last), then by id, newest first. */
export const newestFirst = <T extends { id: number }>(items: T[], at: (x: T) => string | null | undefined): T[] =>
  [...items].sort((a, b) => (at(b) ?? '').localeCompare(at(a) ?? '') || b.id - a.id)
