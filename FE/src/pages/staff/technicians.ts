import type { Order } from '../../types'
import { hashOf } from './evaluate'
import { FINISHED } from './telemetry'

/**
 * Stand-in for the workshop roster. Each technician owns several FR3 robots at
 * once. Robot state is deterministic per day so the page looks the same on reload.
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

const ROSTER: { id: string; name: string; shift: string; skills: string[]; robots: string[] }[] = [
  { id: 'T-01', name: 'Hà Trần', shift: 'Morning, 07:00 to 15:00', skills: ['Fountain pens', 'Brush pens'], robots: ['FR3-01', 'FR3-02', 'FR3-03'] },
  { id: 'T-02', name: 'Phúc Lê', shift: 'Morning, 07:00 to 15:00', skills: ['Ballpoint', 'Fine liner'], robots: ['FR3-04', 'FR3-05'] },
  { id: 'T-03', name: 'Anh Vũ', shift: 'Afternoon, 13:00 to 21:00', skills: ['Fountain pens', 'Gel pens'], robots: ['FR3-06', 'FR3-07', 'FR3-08', 'FR3-09'] },
  { id: 'T-04', name: 'Thảo Đinh', shift: 'Afternoon, 13:00 to 21:00', skills: ['Brush pens', 'Large format'], robots: ['FR3-10', 'FR3-11'] },
]

const day = () => new Date().toISOString().slice(0, 10)

function robotState(id: string): Robot {
  const h = hashOf(day() + id)
  const state: RobotState = h % 11 === 0 ? 'offline' : h % 5 === 0 ? 'calibrating' : h % 2 === 0 ? 'writing' : 'idle'
  return { id, state, ink: 25 + (h % 70) }
}

export function roster(): Technician[] {
  return ROSTER.map((t) => ({
    id: t.id,
    name: t.name,
    initials: t.name.split(' ').map((w) => w[0]).join(''),
    shift: t.shift,
    skills: t.skills,
    robots: t.robots.map(robotState),
  }))
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
