/** Date helpers for the Manager screens. */

/** `YYYY-MM-DD` of a date in the browser's own calendar. */
export const isoDay = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

/** A `YYYY-MM-DD` from the API as a local date, so the day never shifts across time zones. */
export const dayOf = (s: string) => {
  const [y, m, d] = s.slice(0, 10).split('-').map(Number)
  return new Date(y, m - 1, d)
}

/** `YYYY-MM-DD` of `n` days before today. */
export const daysAgo = (n: number) => {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return isoDay(d)
}

/** The last `n` days, oldest first, as `YYYY-MM-DD`. */
export const lastDays = (n: number) => Array.from({ length: n }, (_, i) => daysAgo(n - 1 - i))

/** A 0..1 share as a percentage, or null when the backend has nothing to divide by. */
export const pct = (v: number | null, locale: string) =>
  v === null ? null : v.toLocaleString(locale, { style: 'percent', maximumFractionDigits: 1 })
