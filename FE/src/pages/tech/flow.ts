import { ApiError } from '../../services/api'
import type { TFn } from '../../i18n'
import type { ProbePoint } from '../../services/technician'
import { errText, orderErrorKey } from '../../services/orders'

export type TechRun = (action: () => Promise<unknown>, confirmation?: string) => Promise<boolean>

export function optionalJson(text: string, arrayAllowed = false): Record<string, unknown> | unknown[] | undefined {
  if (!text.trim()) return undefined
  try {
    const value: unknown = JSON.parse(text)
    if (!value || typeof value !== 'object' || (!arrayAllowed && Array.isArray(value))) throw new Error()
    return value as Record<string, unknown> | unknown[]
  } catch { throw new Error('td.flow.invalidJson') }
}

export function probePlaneValid(points: ProbePoint[]) {
  if (points.length < 3 || points.length > 400 || points.some((p) => ![p.x, p.y, p.z].every(Number.isFinite))) return false
  const [p0, p1, p2] = points
  const a = [p1.x - p0.x, p1.y - p0.y, p1.z - p0.z]
  const b = [p2.x - p0.x, p2.y - p0.y, p2.z - p0.z]
  return Math.hypot(a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]) >= 1e-6
}

export function flowError(error: unknown, t: TFn): string {
  if (error instanceof Error && error.message.startsWith('td.flow.')) return t(error.message)
  if (error instanceof ApiError) {
    const key = `td.flow.error.${error.code}`
    const translated = t(key)
    let message = translated === key ? errText(t, orderErrorKey(error)) : translated
    if (error.details) message += ` (${JSON.stringify(error.details)})`
    return message
  }
  return errText(t, orderErrorKey(error))
}
