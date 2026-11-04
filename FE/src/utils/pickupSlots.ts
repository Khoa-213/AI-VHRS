/**
 * Pick-up appointments the customer can choose. The backend checks a slot against `system_settings.working_hours` but has
 * no endpoint that reads that setting, so the hours below copy its seed (Monday to Saturday, 08:00 to 17:00, UTC+7).
 * Change them together with the setting. A slot outside the hours still fails on the server (`OUTSIDE_WORKING_HOURS`).
 */
const OPEN_DAYS = [1, 2, 3, 4, 5, 6] // getUTCDay of the workshop's date: 0 is Sunday
const OPEN_HOUR = 8
const CLOSE_HOUR = 17
const SLOT_HOURS = 1
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
const at = (day: string, hour: number) => `${day}T${pad(hour)}:00:00${OFFSET}`

/** The workshop's calendar day (YYYY-MM-DD) of a moment. */
export const dayOf = (iso: string | number) => new Date(new Date(iso).getTime() + OFFSET_MS).toISOString().slice(0, 10)

/** Noon of a workshop day, for showing the day in the customer's language. */
export const noonOf = (day: string) => new Date(`${day}T12:00:00${OFFSET}`)

/** Slots of one day that are still ahead and within the booking horizon. */
export function slotsOn(day: string, now = Date.now()): Slot[] {
  const out: Slot[] = []
  for (let h = OPEN_HOUR; h + SLOT_HOURS <= CLOSE_HOUR; h += SLOT_HOURS) {
    const start = at(day, h)
    const ms = Date.parse(start)
    if (ms > now && ms <= now + HORIZON_DAYS * DAY_MS) out.push({ start, end: at(day, h + SLOT_HOURS) })
  }
  return out
}

/** Open days, from today, that still have a free slot. */
export function pickupDays(now = Date.now()): string[] {
  const out: string[] = []
  for (let i = 0; i <= HORIZON_DAYS; i++) {
    const day = dayOf(now + i * DAY_MS)
    if (OPEN_DAYS.includes(noonOf(day).getUTCDay()) && slotsOn(day, now).length) out.push(day)
  }
  return out
}
