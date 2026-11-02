import type { Job, Robot, ScheduleConfig } from '../../services/workshop'

/** Calendar maths for the schedule page, in the workshop's clock from `GET /manager/schedule/config`. Mirrors `BE/app/domain/scheduling_rules.py`; the backend still decides on booking. */

const MINUTE = 60_000
const DAY_MS = 86_400_000

export const hm = (v: string) => {
  const [h, m] = v.split(':').map(Number)
  return h * 60 + m
}

const offsetMs = (c: ScheduleConfig) => c.workingHours.utcOffsetMin * MINUTE
const keyMs = (key: string) => Date.parse(`${key}T00:00:00Z`)

export const dateKey = (c: ScheduleConfig, ms: number) => new Date(ms + offsetMs(c)).toISOString().slice(0, 10)
export const clockOf = (c: ScheduleConfig, ms: number) => new Date(ms + offsetMs(c)).toISOString().slice(11, 16)
export const addDays = (key: string, n: number) => new Date(keyMs(key) + n * DAY_MS).toISOString().slice(0, 10)
export const daysBetween = (a: string, b: string) => Math.round((keyMs(b) - keyMs(a)) / DAY_MS)
export const at = (c: ScheduleConfig, key: string, minutes: number) => keyMs(key) + minutes * MINUTE - offsetMs(c)

const weekday = (key: string) => new Date(keyMs(key)).getUTCDay() || 7
export const isWorkingDay = (c: ScheduleConfig, key: string) => c.workingHours.days.includes(weekday(key))
const openMs = (c: ScheduleConfig, key: string) => at(c, key, hm(c.workingHours.start))
const closeMs = (c: ScheduleConfig, key: string) => at(c, key, hm(c.workingHours.end))

export const dayMinutes = (c: ScheduleConfig) => hm(c.workingHours.end) - hm(c.workingHours.start)
export const isOpen = (c: ScheduleConfig, ms: number) => {
  const key = dateKey(c, ms)
  return isWorkingDay(c, key) && ms >= openMs(c, key) && ms < closeMs(c, key)
}

/** Working days of the week holding `key`, Monday first. */
export const weekDays = (c: ScheduleConfig, key: string) => {
  const monday = addDays(key, 1 - weekday(key))
  return [0, 1, 2, 3, 4, 5, 6].map((i) => addDays(monday, i)).filter((d) => isWorkingDay(c, d))
}

/** The nearest working day from `key`, walking `step` days at a time. */
export const workingDayFrom = (c: ScheduleConfig, key: string, step: 1 | -1) => {
  let d = key
  for (let i = 0; i < 15 && !isWorkingDay(c, d); i++) d = addDays(d, step)
  return d
}

/** End of `minutes` of work begun at `start`, stretched over the following working days (`add_working_minutes`). */
export function addWorkingMinutes(c: ScheduleConfig, start: number, minutes: number) {
  let cur = start
  let left = minutes
  for (let guard = 0; guard < 1000; guard++) {
    const close = closeMs(c, dateKey(c, cur))
    const room = (close - cur) / MINUTE
    if (left <= room) return cur + left * MINUTE
    left -= room
    const next = workingDayFrom(c, addDays(dateKey(c, cur), 1), 1)
    cur = openMs(c, next)
  }
  return cur
}

/** The part of [start, end) inside a day's working hours, in minutes after opening. */
export function inDay(c: ScheduleConfig, start: number, end: number, key: string) {
  const a = Math.max(start, openMs(c, key))
  const b = Math.min(end, closeMs(c, key))
  return a < b ? { from: (a - openMs(c, key)) / MINUTE, minutes: (b - a) / MINUTE } : null
}

export type Verdict =
  | { kind: 'ok' }
  | { kind: 'closed' | 'past' }
  | { kind: 'robot'; status: Robot['status'] }
  | { kind: 'robotBusy' | 'techBusy'; code: string }

/** The checks `SchedulingService.schedule` runs, so a clash shows before the request is sent. */
export function checkSlot(c: ScheduleConfig, robot: Robot, techId: number, start: number, minutes: number, jobs: Job[], now: number): Verdict {
  if (robot.status !== 'AVAILABLE') return { kind: 'robot', status: robot.status }
  if (!isOpen(c, start)) return { kind: 'closed' }
  if (start < now - MINUTE) return { kind: 'past' }
  const end = addWorkingMinutes(c, start, minutes)
  const live = jobs.filter((j) => Date.parse(j.slotEnd) > now && Date.parse(j.slotStart) < end && start < Date.parse(j.slotEnd))
  const robotClash = live.find((j) => j.robotId === robot.id)
  if (robotClash) return { kind: 'robotBusy', code: robotClash.orderCode }
  const techClash = live.find((j) => j.technicianId === techId)
  if (techClash) return { kind: 'techBusy', code: techClash.orderCode }
  return { kind: 'ok' }
}

export type Deadline =
  | { state: 'none' }
  | { state: 'overdue' | 'tight'; eta: string; safe: string }
  | { state: 'normal'; eta: string; safe: string; lastOk: string }

/** `eta` is a date. As in `eta_risk`, a job is late when its finish date plus `eta_buffer_days` passes it. */
export function deadlineOf(c: ScheduleConfig, eta: string | null, now: number): Deadline {
  if (!eta) return { state: 'none' }
  const today = dateKey(c, now)
  const safe = addDays(eta, -c.etaBufferDays)
  if (eta < today) return { state: 'overdue', eta, safe }
  if (safe < today) return { state: 'tight', eta, safe }
  const lastOk = workingDayFrom(c, safe, -1)
  return lastOk < today ? { state: 'tight', eta, safe } : { state: 'normal', eta, safe, lastOk }
}

export const lateDays = (c: ScheduleConfig, d: Deadline, end: number) =>
  d.state === 'none' ? 0 : Math.max(0, daysBetween(d.safe, dateKey(c, end)))
