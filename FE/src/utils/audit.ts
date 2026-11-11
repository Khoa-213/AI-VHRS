import type { TFn } from '../i18n'

/** Record kinds the audit log can be narrowed to with one click (the backend's `entity_type`). */
export const AUDIT_KINDS = ['account', 'order', 'payment', 'quotation', 'production_job', 'robot', 'system_setting'] as const

/** A readable name for an audit action code (`REFUND_CONFIRM`). Unknown codes show as plain lower-case words. */
export function auditLabel(t: TFn, action: string): string {
  const key = `au.act.${action}`
  const text = t(key)
  return text === key ? action.toLowerCase().replace(/_/g, ' ') : text
}

/** A readable name for the kind of record an entry is about, or the raw type when it is not one of the known kinds. */
export function auditKind(t: TFn, kind: string | null): string {
  if (!kind) return '–'
  const key = `au.kind.${kind}`
  const text = t(key)
  return text === key ? kind : text
}
