import { api } from './api'
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
