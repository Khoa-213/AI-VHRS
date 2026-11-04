import { ApiError } from '../../services/api'
import type { TFn } from '../../i18n'
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
