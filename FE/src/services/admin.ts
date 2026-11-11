import { allPages, api, newestFirst } from './api'
import type { Account } from './auth'

/** Admin only: internal accounts and the system audit trail (`/admin/*`). Admin has no access to orders, prices or production. */

export const ROLES = ['CUSTOMER', 'STAFF', 'TECHNICAL_STAFF', 'MANAGER', 'ADMIN'] as const
export type ApiRole = (typeof ROLES)[number]
/** Roles an Admin can create (BR-01: customers register themselves). */
export const INTERNAL_ROLES: ApiRole[] = ['STAFF', 'TECHNICAL_STAFF', 'MANAGER', 'ADMIN']

export const STATUSES = ['ACTIVE', 'LOCKED', 'DISABLED'] as const
export type AccountStatus = (typeof STATUSES)[number]

export interface AdminAccount {
  id: number
  email: string
  name: string
  phone: string | null
  role: string
  status: AccountStatus
  createdAt: string
  lastLoginAt: string | null
}

const toAccount = (a: Account): AdminAccount => ({
  id: a.id, email: a.email, name: a.full_name, phone: a.phone, role: a.role, status: a.status as AccountStatus, createdAt: a.created_at, lastLoginAt: a.last_login_at,
})

export interface Paged<T> {
  items: T[]
  total: number
  page: number
  pageSize: number
}

interface RawPage<T> { items: T[]; total: number; page: number; page_size: number }

const query = (params: Record<string, string | number | undefined>) => {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== '') q.set(k, String(v))
  const s = q.toString()
  return s ? `?${s}` : ''
}

export async function listAccounts(f: { role?: string; status?: string; q?: string; page?: number; pageSize?: number } = {}): Promise<Paged<AdminAccount>> {
  const r = await api<RawPage<Account>>(`/admin/accounts${query({ role: f.role, status: f.status, q: f.q?.trim(), page: f.page, page_size: f.pageSize })}`)
  return { items: r.items.map(toAccount), total: r.total, page: r.page, pageSize: r.page_size }
}

/** Every matching account, newest first (the backend pages them oldest first). */
export const allAccounts = async (f: { role?: string; status?: string; q?: string } = {}): Promise<AdminAccount[]> =>
  newestFirst(await allPages((page) => listAccounts({ ...f, page, pageSize: 100 }), 100), (a) => a.createdAt)

export const createAccount = async (b: { email: string; password: string; full_name: string; phone?: string; role: string }) =>
  toAccount(await api<Account>('/admin/accounts', { method: 'POST', body: b }))

/** Lock, unlock or change the role. The reason (up to 500 characters) goes into the audit log. */
export const updateAccount = async (id: number, b: { status?: AccountStatus; role?: string; reason?: string }) =>
  toAccount(await api<Account>(`/admin/accounts/${id}`, { method: 'PATCH', body: b }))

export interface AuditEntry {
  id: number
  actorId: number | null
  action: string
  entityType: string | null
  entityId: number | null
  oldValue: Record<string, unknown> | null
  newValue: Record<string, unknown> | null
  reason: string | null
  createdAt: string
}

interface RawAudit {
  id: number; actor_id: number | null; action: string; entity_type: string | null; entity_id: number | null
  old_value: Record<string, unknown> | null; new_value: Record<string, unknown> | null; reason: string | null; created_at: string
}

export async function listAudit(f: { actorId?: number; action?: string; entityType?: string; entityId?: number; page?: number; pageSize?: number } = {}): Promise<Paged<AuditEntry>> {
  const r = await api<RawPage<RawAudit>>(
    `/admin/audit-logs${query({ actor_id: f.actorId, action: f.action?.trim(), entity_type: f.entityType?.trim(), entity_id: f.entityId, page: f.page, page_size: f.pageSize })}`,
  )
  return {
    items: r.items.map((x) => ({
      id: x.id, actorId: x.actor_id, action: x.action, entityType: x.entity_type, entityId: x.entity_id,
      oldValue: x.old_value, newValue: x.new_value, reason: x.reason, createdAt: x.created_at,
    })),
    total: r.total, page: r.page, pageSize: r.page_size,
  }
}

// ---------- background jobs (Phase 5a) ----------

export const BACKGROUND_JOBS = ['quotation_expiry', 'deposit_deadline', 'acceptance', 'email_retry', 'photo_purge'] as const
export type BackgroundJob = (typeof BACKGROUND_JOBS)[number]

export interface JobsRun {
  ran: boolean
  reason: string | null
  /** Per job: counters, or `{ error }`. */
  results: Record<string, Record<string, unknown>>
  startedAt: string
  seconds: number
}

interface RawJobsRun { ran: boolean; reason?: string | null; results: Record<string, Record<string, unknown>>; started_at: string; seconds: number }

const toJobsRun = (r: RawJobsRun): JobsRun => ({ ran: r.ran, reason: r.reason ?? null, results: r.results ?? {}, startedAt: r.started_at, seconds: r.seconds })

/** `POST /admin/jobs/run`: runs the background jobs now (all, or only the given ones). */
export const runBackgroundJobs = async (only?: BackgroundJob[]) =>
  toJobsRun(await api<RawJobsRun>('/admin/jobs/run', { method: 'POST', body: { confirm: true, ...(only?.length ? { only } : {}) } }))

/** `GET /admin/jobs/last`: the latest run, or null when none ran yet. */
export const lastBackgroundRun = async () => {
  const r = await api<RawJobsRun | null>('/admin/jobs/last')
  return r ? toJobsRun(r) : null
}

// ---------- system settings, integrations, system dashboard (Phase 5b: UC-49, UC-50, UC-52) ----------

export type SettingValue = number | boolean | string[] | Record<string, number>

export interface SystemSetting {
  key: string
  /** Vietnamese label from the backend; screens show their own translation of `key` and keep this as a fallback. */
  label: string
  value: SettingValue
  /** True while no row exists yet and the code default applies. */
  isDefault: boolean
  updatedBy: number | null
  updatedAt: string | null
}

interface RawSetting { key: string; label: string; value: SettingValue; is_default: boolean; updated_by: number | null; updated_at: string | null }

const toSetting = (s: RawSetting): SystemSetting => ({
  key: s.key, label: s.label, value: s.value, isDefault: s.is_default, updatedBy: s.updated_by, updatedAt: s.updated_at,
})

export const listSettings = async () => (await api<RawSetting[]>('/admin/settings')).map(toSetting)

/** `PUT /admin/settings/{key}`. A wrong type or range comes back as `422 INVALID_SETTING` with the reason in the message. */
export const saveSetting = async (key: string, value: SettingValue, reason?: string) =>
  toSetting(await api<RawSetting>(`/admin/settings/${encodeURIComponent(key)}`, { method: 'PUT', body: { value, ...(reason?.trim() ? { reason: reason.trim() } : {}) } }))

export interface Integration {
  name: string
  kind: string
  mode: string
  configured: boolean
  /** Only GHN can be switched here; the others are set by the server environment. */
  toggleable: boolean
  enabled: boolean
}

export const listIntegrations = () => api<Integration[]>('/admin/integrations')

export const toggleIntegration = (name: string, enabled: boolean, reason?: string) =>
  api<Integration>(`/admin/integrations/${encodeURIComponent(name)}`, { method: 'PUT', body: { enabled, ...(reason?.trim() ? { reason: reason.trim() } : {}) } })

export interface SystemDashboard {
  generatedAt: string
  databaseMs: number
  accounts: { byRole: Record<string, Record<string, number>>; newLast7Days: number; activeSessions: number }
  robots: { total: number; online: number; byStatus: Record<string, number> }
  integrations: Integration[]
  backgroundJobs: { enabled: boolean; intervalSeconds: number; lastRun: JobsRun | null }
  emailsFailedLast24h: number
}

interface RawDashboard {
  generated_at: string
  database_ms: number
  accounts: { by_role: Record<string, Record<string, number>>; new_last_7_days: number; active_sessions: number }
  robots: { total: number; online: number; by_status: Record<string, number> }
  integrations: Integration[]
  background_jobs: { enabled: boolean; interval_seconds: number; last_run: RawJobsRun | null }
  notifications: { emails_failed_last_24h: number }
}

export async function systemDashboard(): Promise<SystemDashboard> {
  const d = await api<RawDashboard>('/admin/dashboard')
  return {
    generatedAt: d.generated_at,
    databaseMs: d.database_ms,
    accounts: { byRole: d.accounts.by_role, newLast7Days: d.accounts.new_last_7_days, activeSessions: d.accounts.active_sessions },
    robots: { total: d.robots.total, online: d.robots.online, byStatus: d.robots.by_status },
    integrations: d.integrations,
    backgroundJobs: {
      enabled: d.background_jobs.enabled,
      intervalSeconds: d.background_jobs.interval_seconds,
      lastRun: d.background_jobs.last_run ? toJobsRun(d.background_jobs.last_run) : null,
    },
    emailsFailedLast24h: d.notifications.emails_failed_last_24h,
  }
}

// ---------- activity per day, from the audit log ----------

export interface DayCount { date: string; count: number }

const dayKey = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

/**
 * Audit entries per local day for the last `days` days (today last), counted from `GET /admin/audit-logs`, which lists the
 * newest first: pages are read until one reaches back past the first day, up to `maxPages` of 100 entries. `truncated` is
 * true when the page limit stopped the count before the first day was reached.
 */
export async function auditActivity(days = 14, maxPages = 8): Promise<{ days: DayCount[]; truncated: boolean }> {
  const start = new Date()
  start.setHours(0, 0, 0, 0)
  start.setDate(start.getDate() - (days - 1))
  const buckets = new Map<string, number>()
  for (let i = 0; i < days; i++) {
    const d = new Date(start)
    d.setDate(start.getDate() + i)
    buckets.set(dayKey(d), 0)
  }
  let truncated = false
  for (let page = 1; page <= maxPages; page++) {
    const r = await listAudit({ page, pageSize: 100 })
    let reached = false
    for (const e of r.items) {
      const t = new Date(e.createdAt)
      if (t < start) { reached = true; continue }
      const k = dayKey(t)
      if (buckets.has(k)) buckets.set(k, (buckets.get(k) ?? 0) + 1)
    }
    if (reached || page * 100 >= r.total) break
    if (page === maxPages) truncated = true
  }
  return { days: [...buckets].map(([date, count]) => ({ date, count })), truncated }
}
