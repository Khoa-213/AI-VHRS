/**
 * Pick-up appointments the customer can choose. The opening hours come with the delivery quote (`pickup_hours`, the
 * backend's `system_settings.working_hours`); `DEFAULT_HOURS` (the setting's seed: Monday to Saturday, 08:00 to 17:00,
 * UTC+7) is used only until the quote is in or when the setting is broken. A slot outside the hours fails on the server
 * (`OUTSIDE_WORKING_HOURS`).
 */
export interface PickupHours {
  /** ISO weekdays, Monday = 1. */
  days: number[]
  /** HH:MM on the workshop's clock. */
  start: string
  end: string
  utcOffsetMin: number
}
export const DEFAULT_HOURS: PickupHours = { days: [1, 2, 3, 4, 5, 6], start: '08:00', end: '17:00', utcOffsetMin: 420 }
const SLOT_MIN = 60
const HORIZON_DAYS = 30
const OFFSET = '+07:00'
const OFFSET_MS = 7 * 3600_000
const DAY_MS = 86_400_000

/** For `toLocale*String({ timeZone })`, so times read as the workshop's clock wherever the customer is. */
export const WORKSHOP_TZ = 'Asia/Ho_Chi_Minh'

export interface Slot {
  start: string
  end: string
}

const pad = (n: number) => String(n).padStart(2, '0')
const minuteOf = (hm: string) => { const [h, m] = hm.split(':').map(Number); return h * 60 + (m || 0) }
const offsetText = (min: number) => `${min < 0 ? '-' : '+'}${pad(Math.floor(Math.abs(min) / 60))}:${pad(Math.abs(min) % 60)}`
const at = (day: string, minute: number, hours: PickupHours) =>
  `${day}T${pad(Math.floor(minute / 60))}:${pad(minute % 60)}:00${offsetText(hours.utcOffsetMin)}`

/** The workshop's calendar day (YYYY-MM-DD) of a moment. */
export const dayOf = (iso: string | number) => new Date(new Date(iso).getTime() + OFFSET_MS).toISOString().slice(0, 10)

/** Noon of a workshop day, for showing the day in the customer's language. */
export const noonOf = (day: string) => new Date(`${day}T12:00:00${OFFSET}`)

/** Slots of one day that are still ahead and within the booking horizon. */
export function slotsOn(day: string, hours: PickupHours = DEFAULT_HOURS, now = Date.now()): Slot[] {
  const out: Slot[] = []
  const close = minuteOf(hours.end)
  for (let m = minuteOf(hours.start); m + SLOT_MIN <= close; m += SLOT_MIN) {
    const start = at(day, m, hours)
    const ms = Date.parse(start)
    if (ms > now && ms <= now + HORIZON_DAYS * DAY_MS) out.push({ start, end: at(day, m + SLOT_MIN, hours) })
  }
  return out
}

/** Open days, from today, that still have a free slot. */
export function pickupDays(hours: PickupHours = DEFAULT_HOURS, now = Date.now()): string[] {
  const out: string[] = []
  for (let i = 0; i <= HORIZON_DAYS; i++) {
    const day = dayOf(now + i * DAY_MS)
    const weekday = noonOf(day).getUTCDay() || 7 // ISO: Sunday is 7
    if (hours.days.includes(weekday) && slotsOn(day, hours, now).length) out.push(day)
  }
  return out
}
