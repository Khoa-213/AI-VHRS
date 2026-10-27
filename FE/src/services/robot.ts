import { API_BASE, ApiError, api } from './api'

/**
 * Robot control for the Technical Staff (`BE/docs/FE_API_GUIDE.md` sections 7f and 7g). The app never talks to the
 * workstation: it creates commands on the backend, the Robot Agent pulls them, runs them (MOCK, SIM or REAL) and reports
 * back; the live frames, the robot status and the alerts come from the backend too.
 */

export type RobotMode = 'MOCK' | 'SIM' | 'REAL'
export type CommandKind = 'LOAD' | 'PREFLIGHT' | 'DRY_RUN' | 'RUN' | 'PAUSE' | 'RESUME' | 'STOP' | 'PAPER_CHANGED' | 'IDENTIFY' | 'ALIGN_START'
export type CommandStatus = 'PENDING' | 'DELIVERED' | 'DONE' | 'FAILED' | 'EXPIRED' | 'CANCELLED'
export const COMMAND_FINAL: CommandStatus[] = ['DONE', 'FAILED', 'EXPIRED', 'CANCELLED']

export interface RobotCommand {
  id: string
  robotId: number
  jobId: number | null
  kind: CommandKind
  params: Record<string, unknown>
  status: CommandStatus
  result: Record<string, unknown> | null
  errorCode: string | null
  errorMessage: string | null
  createdAt: string
  expiresAt: string
  finishedAt: string | null
}

interface RawCommand {
  id: string; robot_id: number; job_id: number | null; kind: CommandKind; params: Record<string, unknown>; status: CommandStatus
  result: Record<string, unknown> | null; error_code: string | null; error_message: string | null
  created_at: string; expires_at: string; delivered_at: string | null; finished_at: string | null
}

const toCommand = (c: RawCommand): RobotCommand => ({
  id: c.id, robotId: c.robot_id, jobId: c.job_id, kind: c.kind, params: c.params ?? {}, status: c.status, result: c.result,
  errorCode: c.error_code, errorMessage: c.error_message, createdAt: c.created_at, expiresAt: c.expires_at, finishedAt: c.finished_at,
})

const newKey = () => (globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`)

/** One press of a button: a fresh idempotency key, so a double click or a retried request makes one command only. */
export async function sendCommand(body: { kind: CommandKind; job_id?: number; robot_id?: number; params?: Record<string, unknown> }): Promise<RobotCommand> {
  return toCommand(await api<RawCommand>('/technician/robot-commands', {
    method: 'POST', body: { ...body, params: body.params ?? {}, idempotency_key: newKey() },
  }))
}

export const getCommand = async (id: string): Promise<RobotCommand> =>
  toCommand(await api<RawCommand>(`/technician/robot-commands/${encodeURIComponent(id)}`))

export const jobCommands = async (jobId: number, limit = 20): Promise<RobotCommand[]> =>
  (await api<RawCommand[]>(`/technician/jobs/${jobId}/robot-commands?limit=${limit}`)).map(toCommand)

/** Follows a command until the agent answers (DONE / FAILED) or it lapses (EXPIRED). PENDING never runs late. */
export async function waitCommand(cmd: RobotCommand, onUpdate: (c: RobotCommand) => void, signal: AbortSignal): Promise<RobotCommand> {
  let current = cmd
  while (!COMMAND_FINAL.includes(current.status)) {
    await new Promise((r) => setTimeout(r, 700))
    if (signal.aborted) return current
    try {
      current = await getCommand(cmd.id)
      onUpdate(current)
    } catch (e) {
      if (!(e instanceof ApiError) || e.status >= 500 || e.status === 0) continue // a hiccup: keep asking
      throw e
    }
  }
  return current
}

// ---------- live view ----------

/** One frame of the agent's live state (joints in degrees, tool position in mm). */
export interface LiveFrame {
  seq: number
  state: string
  mode: string
  job_id: number | null
  tcp: number[] | null
  move_kind: string
  stroke: number
  total_strokes: number
  progress_pct: number
  force_n: number | null
  touching: boolean
  fault: string | null
  message: string
  joints_deg: number[] | null
  level: number
  alerts: { code: string; level: number; title_vi: string; action_vi: string; estop_advised: boolean }[]
}

/** The agent's own status line: what it runs now, the last outcome, which modes the workstation allows. */
export interface AgentStatus {
  mode?: string
  busy?: boolean
  state?: string
  level?: number
  current?: { job_id?: number; mode?: string; dry_run?: boolean; align_start?: boolean } | null
  last?: { result?: Record<string, unknown>; refused?: { code: string; message: string }; error?: string; job_id?: number; dry_run?: boolean } | null
  enabled_modes?: string[]
  agent_version?: string
}

export interface Live {
  robotId: number
  robotCode: string
  online: boolean
  ageS: number | null
  mode: string | null
  status: AgentStatus
  lastSeq: number
  frames: LiveFrame[]
}

export async function getLive(robotId: number, after: number): Promise<Live> {
  const r = await api<{ robot_id: number; robot_code: string; agent_online: boolean; age_s: number | null; mode: string | null
    status: AgentStatus; last_seq: number; frames: LiveFrame[] }>(`/technician/robots/${robotId}/live?after=${after}`)
  return { robotId: r.robot_id, robotCode: r.robot_code, online: r.agent_online, ageS: r.age_s, mode: r.mode,
    status: r.status ?? {}, lastSeq: r.last_seq, frames: r.frames ?? [] }
}

/** Read-only 3D page served by the backend, embedded in an iframe. The ticket lasts `expiresIn` seconds. */
export async function viewTicket(robotId: number): Promise<{ url: string; expiresIn: number }> {
  const r = await api<{ ticket: string; expires_in: number; viewer_path: string }>(`/technician/robots/${robotId}/view-ticket`, { method: 'POST' })
  return { url: `${API_BASE.replace(/\/api\/v1$/, '')}${r.viewer_path}`, expiresIn: r.expires_in }
}

// ---------- status and alerts ----------

export interface RobotAlert {
  id: number
  robotId: number
  jobId: number | null
  code: string
  level: number
  title: string
  action: string
  estopAdvised: boolean
  occurrences: number
  raisedAt: string
  acknowledgedAt: string | null
}

export interface RobotStatus {
  robotId: number
  robotCode: string
  state: 'OFFLINE' | 'IDLE' | 'PREPARING' | 'WRITING' | 'PAUSED_SAFE' | 'DANGER'
  /** Plain Vietnamese sentence from the backend. */
  headline: string
  level: number
  mode: string | null
  connection: string
  lastSeenAt: string | null
  jobId: number | null
  jobStatus: string | null
  openRun: { runId: string; mode: string; dryRun: boolean; completedStrokes: number; totalStrokes: number } | null
  alerts: RobotAlert[]
  calibrationAgeMin: number | null
}

interface RawAlert {
  id: number; robot_id: number; job_id: number | null; code: string; level: number; title_vi: string; action_vi: string
  estop_advised: boolean; occurrences: number; raised_at: string; acknowledged_at: string | null
}

const toAlert = (a: RawAlert): RobotAlert => ({
  id: a.id, robotId: a.robot_id, jobId: a.job_id, code: a.code, level: a.level, title: a.title_vi, action: a.action_vi,
  estopAdvised: a.estop_advised, occurrences: a.occurrences, raisedAt: a.raised_at, acknowledgedAt: a.acknowledged_at,
})

export async function robotStatus(): Promise<RobotStatus[]> {
  const rows = await api<{
    robot_id: number; robot_code: string; state: RobotStatus['state']; headline_vi: string; level: number; mode: string | null
    connection_state: string; last_seen_at: string | null; job_id: number | null; job_status: string | null
    open_run: { run_id: string; mode: string; dry_run: boolean; completed_strokes: number; total_strokes: number } | null
    open_alerts: RawAlert[]; calibration_age_minutes: number | null
  }[]>('/technician/robot-status')
  return rows.map((r) => ({
    robotId: r.robot_id, robotCode: r.robot_code, state: r.state, headline: r.headline_vi, level: r.level, mode: r.mode,
    connection: r.connection_state, lastSeenAt: r.last_seen_at, jobId: r.job_id, jobStatus: r.job_status,
    openRun: r.open_run && { runId: r.open_run.run_id, mode: r.open_run.mode, dryRun: r.open_run.dry_run,
      completedStrokes: r.open_run.completed_strokes, totalStrokes: r.open_run.total_strokes },
    alerts: r.open_alerts.map(toAlert), calibrationAgeMin: r.calibration_age_minutes,
  }))
}

export const ackAlert = async (id: number) => toAlert(await api<RawAlert>(`/technician/alerts/${id}/ack`, { method: 'POST' }))

/** Levels 1 to 3 only; a red (level 4) alert is closed by a Manager. */
export const resolveAlert = async (id: number, note: string) =>
  toAlert(await api<RawAlert>(`/technician/alerts/${id}/resolve`, { method: 'POST', body: { note } }))
