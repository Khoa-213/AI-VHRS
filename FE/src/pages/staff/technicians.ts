import type { Order } from '../../types'
import { FINISHED } from './telemetry'

/**
 */

export type RobotState = 'idle' | 'writing' | 'calibrating' | 'offline'

export interface Robot {
  id: string
  state: RobotState
  ink: number
}

export interface Technician {
  id: string
  name: string
  initials: string
  shift: string
  skills: string[]
  robots: Robot[]
}

export const STATE_LABEL: Record<RobotState, string> = {
  idle: 'Idle',
  writing: 'Writing',
  calibrating: 'Calibrating',
  offline: 'Offline',
}

/**
 * Technicians and their robots. The backend has no endpoint in this shape yet
 * (`/manager/technicians` and `/manager/robots` are job-based), so the list is empty
 * until it is wired in.
 */
export function roster(): Technician[] {
  return []
}

/** Orders a technician is carrying: assigned and not yet written. */
export function loadOf(techId: string, orders: Order[]): number {
  return orders.filter((o) => o.assignment?.techId === techId && !FINISHED.includes(o.status)).length
}

export const freeRobots = (t: Technician) => t.robots.filter((r) => r.state === 'idle')

/** Least loaded technician that has an idle robot, ties broken by more idle robots. */
export function recommend(techs: Technician[], orders: Order[]): Technician | undefined {
  return techs
    .filter((t) => freeRobots(t).length)
    .sort((a, b) => loadOf(a.id, orders) - loadOf(b.id, orders) || freeRobots(b).length - freeRobots(a).length)[0]
}
