import { useSyncExternalStore } from 'react'
import { robotStatus, type RobotStatus } from '../services/robot'

/**
 * `GET /technician/robot-status`, shared by every technician view that needs it (the alert bell, Robot control, the
 * dashboard): one request every 2 seconds while at least one of them is on screen, none while the tab is hidden.
 */
interface State {
  data: RobotStatus[] | null
  error: unknown
}

let state: State = { data: null, error: null }
const listeners = new Set<() => void>()
let timer = 0
let inflight: Promise<void> | null = null

function emit(next: State) {
  state = next
  listeners.forEach((l) => l())
}

function tick(): Promise<void> {
  inflight ??= robotStatus()
    .then((data) => emit({ data, error: null }), (error: unknown) => emit({ ...state, error }))
    .finally(() => { inflight = null })
  return inflight
}

function subscribe(cb: () => void) {
  listeners.add(cb)
  if (listeners.size === 1) {
    void tick()
    timer = window.setInterval(() => { if (!document.hidden) void tick() }, 2000)
  }
  return () => {
    listeners.delete(cb)
    if (!listeners.size) {
      window.clearInterval(timer)
      state = { data: null, error: null }
    }
  }
}

export const useRobotStatus = () => useSyncExternalStore(subscribe, () => state)

/** Ask again now, after an alert was acknowledged or closed. */
export const reloadRobotStatus = () => tick()
