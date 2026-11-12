import { api, apiFile } from './api'
import type { Page } from './orders'
import type { RobotAlert, RobotStatus } from './robot'

/**
 * Manager only (`RequireStaff manager`):
 * - production dashboard and reports (`BE/app/api/v1/reports.py`; the backend types them `dict[str, Any]`, the shapes below are
 *   read from the SQL in `BE/app/services/reports.py` and checked against the deployed API on 2026-11-12);
 * - robot operations (`robot_ops.py`): status, health, runs, process compliance, alerts and the alert catalogue;
 * - job detail, events, incidents (`scheduling.py`) and quality results (`quality.py`);
 * - review moderation (`reviews.py`).
 */

// ---------- dashboard (UC-45) ----------

export interface DashboardJob { jobId: number; orderId: number; orderCode: string; robotCode: string; status: string; slotStart: string; slotEnd: string; isRewrite: boolean }
export interface DashboardOrder { orderId: number; code: string; status: string; eta: string; daysLate?: number }
export interface LowStock { kind: 'PAPER' | 'PEN' | 'INK'; id: number; name: string; stock: number }

export interface ManagerDashboard {
  date: string
  ordersByStatus: Record<string, number>
  jobsToday: DashboardJob[]
  jobsNext7Days: number
  lateOrders: DashboardOrder[]
  dueIn2Days: DashboardOrder[]
  lowStock: LowStock[]
  pending: { unclaimedOrders: number; priceAdjustments: number; ordersToSchedule: number; openIncidents: number; refundsToConfirm: number }
}

interface RawDashboard {
  date: string
  orders_by_status: Record<string, number>
  jobs_today: { job_id: number; order_id: number; order_code: string; robot_code: string; status: string; slot_start: string; slot_end: string; is_rewrite: boolean }[]
  jobs_next_7_days: number
  late_orders: { order_id: number; code: string; status: string; eta: string; days_late: number }[]
  due_in_2_days: { order_id: number; code: string; status: string; eta: string }[]
  low_stock: { kind: LowStock['kind']; id: number; name: string; stock_qty: number }[]
  pending: { unclaimed_orders: number; price_adjustments: number; orders_to_schedule: number; open_incidents: number; refunds_to_confirm: number }
}

export async function managerDashboard(): Promise<ManagerDashboard> {
  const r = await api<RawDashboard>('/manager/dashboard')
  return {
    date: r.date,
    ordersByStatus: r.orders_by_status,
    jobsToday: r.jobs_today.map((j) => ({
      jobId: j.job_id, orderId: j.order_id, orderCode: j.order_code, robotCode: j.robot_code, status: j.status,
      slotStart: j.slot_start, slotEnd: j.slot_end, isRewrite: j.is_rewrite,
    })),
    jobsNext7Days: r.jobs_next_7_days,
    lateOrders: r.late_orders.map((o) => ({ orderId: o.order_id, code: o.code, status: o.status, eta: o.eta, daysLate: Number(o.days_late) })),
    dueIn2Days: r.due_in_2_days.map((o) => ({ orderId: o.order_id, code: o.code, status: o.status, eta: o.eta })),
    lowStock: r.low_stock.map((s) => ({ kind: s.kind, id: s.id, name: s.name, stock: Number(s.stock_qty) })),
    pending: {
      unclaimedOrders: r.pending.unclaimed_orders, priceAdjustments: r.pending.price_adjustments,
      ordersToSchedule: r.pending.orders_to_schedule, openIncidents: r.pending.open_incidents, refundsToConfirm: r.pending.refunds_to_confirm,
    },
  }
}

// ---------- reports (UC-46, FR-50) ----------

/** `Group` in `reports.py`. */
export type ReportGroup = 'day' | 'week' | 'month'
export const REPORT_GROUPS: ReportGroup[] = ['day', 'week', 'month']

export interface ReportQuery { from?: string; to?: string; group: ReportGroup }
export interface RevenuePoint { bucket: string; received: number; refunded: number; net: number; payments: number }
export interface OutputRow { orderType: string; orders: number; quantity: number; totalAmount: number }
export interface RobotRow { robotId: number; robotCode: string; jobsWritten: number; writingMinutes: number; incidents: number }
export interface LateRow { orderId: number; code: string; eta: string; completedOn: string; daysLate: number; postponedDays: number }

export interface Report {
  from: string
  to: string
  group: ReportGroup
  revenue: { series: RevenuePoint[]; received: number; refunded: number; net: number }
  outputByType: OutputRow[]
  rates: { submitted: number; rejected: number; rejectRate: number | null; jobsWritten: number; rewrites: number; rewriteRate: number | null }
  robots: RobotRow[]
  late: { count: number; ofCompleted: number; lateRate: number | null; orders: LateRow[] }
}

interface RawReport {
  from: string
  to: string
  group: ReportGroup
  revenue: { series: RevenuePoint[]; received: number; refunded: number; net: number }
  output_by_type: { order_type: string; orders: number; quantity: number; total_amount: number }[]
  rates: { submitted: number; rejected: number; reject_rate: number | null; jobs_written: number; rewrites: number; rewrite_rate: number | null }
  robots: { robot_id: number; robot_code: string; jobs_written: number; writing_minutes: number; incidents: number }[]
  late_completed: {
    count: number; of_completed: number; late_rate: number | null
    orders: { order_id: number; code: string; eta: string; completed_on: string; days_late: number; eta_postponed_days: number | null }[]
  }
}

const reportQuery = (q: ReportQuery, extra?: Record<string, string>) => {
  const p = new URLSearchParams({ group: q.group, ...extra })
  if (q.from) p.set('from', q.from)
  if (q.to) p.set('to', q.to)
  return p.toString()
}

export async function managerReport(q: ReportQuery): Promise<Report> {
  const r = await api<RawReport>(`/manager/reports?${reportQuery(q)}`)
  return {
    from: r.from,
    to: r.to,
    group: r.group,
    revenue: {
      series: r.revenue.series.map((x) => ({ bucket: x.bucket, received: Number(x.received), refunded: Number(x.refunded), net: Number(x.net), payments: Number(x.payments) })),
      received: Number(r.revenue.received), refunded: Number(r.revenue.refunded), net: Number(r.revenue.net),
    },
    outputByType: r.output_by_type.map((x) => ({ orderType: x.order_type, orders: Number(x.orders), quantity: Number(x.quantity), totalAmount: Number(x.total_amount) })),
    rates: {
      submitted: r.rates.submitted, rejected: r.rates.rejected, rejectRate: r.rates.reject_rate,
      jobsWritten: r.rates.jobs_written, rewrites: r.rates.rewrites, rewriteRate: r.rates.rewrite_rate,
    },
    robots: r.robots.map((x) => ({ robotId: x.robot_id, robotCode: x.robot_code, jobsWritten: Number(x.jobs_written), writingMinutes: Number(x.writing_minutes), incidents: Number(x.incidents) })),
    late: {
      count: r.late_completed.count, ofCompleted: r.late_completed.of_completed, lateRate: r.late_completed.late_rate,
      orders: r.late_completed.orders.map((o) => ({
        orderId: o.order_id, code: o.code, eta: o.eta, completedOn: o.completed_on, daysLate: Number(o.days_late), postponedDays: Number(o.eta_postponed_days ?? 0),
      })),
    },
  }
}

/** Downloads the report as Excel (default) or PDF with the Bearer header and hands it to the browser. */
export async function exportReport(q: ReportQuery, format: 'xlsx' | 'pdf'): Promise<void> {
  const { blob, name } = await apiFile(`/manager/reports/export?${reportQuery(q, { format })}`)
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  // Cross-origin the browser hides Content-Disposition unless the backend exposes it, so fall back to the backend's own pattern.
  a.download = name ?? `bao-cao_${q.from ?? ''}_${q.to ?? ''}.${format}`
  document.body.appendChild(a)
  a.click()
  a.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

// ---------- robot status, health, alerts ----------

export interface ManagerAlert extends RobotAlert {
  robotCode: string
  lastRaisedAt: string
  resolvedAt: string | null
  resolutionNote: string | null
}

interface RawAlert {
  id: number; robot_id: number; robot_code: string; job_id: number | null; code: string; level: number; title_vi: string; action_vi: string
  estop_advised: boolean; occurrences: number; raised_at: string; last_raised_at: string; acknowledged_at: string | null
  resolved_at: string | null; resolution_note: string | null
}

const toAlert = (a: RawAlert): ManagerAlert => ({
  id: a.id, robotId: a.robot_id, robotCode: a.robot_code, jobId: a.job_id, code: a.code, level: a.level, title: a.title_vi,
  action: a.action_vi, estopAdvised: a.estop_advised, occurrences: a.occurrences, raisedAt: a.raised_at,
  lastRaisedAt: a.last_raised_at, acknowledgedAt: a.acknowledged_at, resolvedAt: a.resolved_at, resolutionNote: a.resolution_note,
})

export interface ManagerRobotStatus extends Omit<RobotStatus, 'alerts'> {
  alerts: ManagerAlert[]
  secondsSinceSeen: number | null
  agentVersion: string | null
}

interface RawStatus {
  robot_id: number; robot_code: string; state: RobotStatus['state']; headline_vi: string; level: number; mode: string | null
  connection_state: string; last_seen_at: string | null; seconds_since_seen: number | null; agent_version: string | null
  job_id: number | null; job_status: string | null
  open_run: { run_id: string; mode: string; dry_run: boolean; completed_strokes: number; total_strokes: number } | null
  open_alerts: RawAlert[]; calibration_age_minutes: number | null
}

const toStatus = (r: RawStatus): ManagerRobotStatus => ({
  robotId: r.robot_id, robotCode: r.robot_code, state: r.state, headline: r.headline_vi, level: r.level, mode: r.mode,
  connection: r.connection_state, lastSeenAt: r.last_seen_at, secondsSinceSeen: r.seconds_since_seen, agentVersion: r.agent_version,
  jobId: r.job_id, jobStatus: r.job_status,
  openRun: r.open_run && { runId: r.open_run.run_id, mode: r.open_run.mode, dryRun: r.open_run.dry_run,
    completedStrokes: r.open_run.completed_strokes, totalStrokes: r.open_run.total_strokes },
  alerts: r.open_alerts.map(toAlert), calibrationAgeMin: r.calibration_age_minutes,
})

export const managerRobotStatus = async (): Promise<ManagerRobotStatus[]> => (await api<RawStatus[]>('/manager/robot-status')).map(toStatus)

export interface RobotHealth {
  robot: ManagerRobotStatus
  since: string
  runsByResult: Record<string, number>
  runsByMode: Record<string, number>
  runSeconds: number
  safetyStops: number
  alertsByLevel: Record<string, number>
  inBandPctAvg: number | null
  openIncidents: number
  unresolvedRed: number
}

export async function robotHealth(robotId: number, days: number): Promise<RobotHealth> {
  const r = await api<{
    robot: RawStatus; since: string; runs_by_result: Record<string, number>; runs_by_mode: Record<string, number>; run_seconds: number
    safety_stops: number; alerts_by_level: Record<string, number>; in_band_pct_avg: number | null; open_incidents: number; unresolved_red: number
  }>(`/manager/robots/${robotId}/health?days=${days}`)
  return {
    robot: toStatus(r.robot), since: r.since, runsByResult: r.runs_by_result, runsByMode: r.runs_by_mode, runSeconds: r.run_seconds,
    safetyStops: r.safety_stops, alertsByLevel: r.alerts_by_level, inBandPctAvg: r.in_band_pct_avg, openIncidents: r.open_incidents,
    unresolvedRed: r.unresolved_red,
  }
}

/** Open alerts by default, heaviest first then newest (the backend's order). */
export async function managerAlerts(opts: { open?: boolean; robotId?: number; minLevel?: number; page?: number; pageSize?: number } = {}): Promise<Page<ManagerAlert>> {
  const q = new URLSearchParams({ open: String(opts.open ?? true), page: String(opts.page ?? 1), page_size: String(opts.pageSize ?? 50) })
  if (opts.robotId) q.set('robot_id', String(opts.robotId))
  if (opts.minLevel) q.set('min_level', String(opts.minLevel))
  const r = await api<{ items: RawAlert[]; total: number; page: number; page_size: number }>(`/manager/alerts?${q}`)
  return { items: r.items.map(toAlert), total: r.total, page: r.page, pageSize: r.page_size }
}

export const ackManagerAlert = async (id: number) => toAlert(await api<RawAlert>(`/manager/alerts/${id}/ack`, { method: 'POST' }))

/** The note is 3 to 500 characters. A Manager may close a red (level 4) alert after checking the robot is safe. */
export const resolveManagerAlert = async (id: number, note: string) =>
  toAlert(await api<RawAlert>(`/manager/alerts/${id}/resolve`, { method: 'POST', body: { note } }))

export interface AlertCatalogEntry { code: string; level: number; title: string; action: string; estopAdvised: boolean; notifyRoles: string[]; sendEmail: boolean; isActive: boolean }

export async function alertCatalog(): Promise<AlertCatalogEntry[]> {
  const rows = await api<{ code: string; level: number; title_vi: string; action_vi: string; estop_advised: boolean; notify_roles: string[]; send_email: boolean; is_active: boolean }[]>('/manager/alert-catalog')
  return rows.map((c) => ({
    code: c.code, level: c.level, title: c.title_vi, action: c.action_vi, estopAdvised: c.estop_advised,
    notifyRoles: c.notify_roles, sendEmail: c.send_email, isActive: c.is_active,
  }))
}

/** A red (level 4) entry cannot be turned off, lose its e-mail or drop the technician (`RED_ALERT_PROTECTED`). */
export interface CatalogPatch { sendEmail?: boolean; isActive?: boolean; notifyRoles?: string[] }

export async function patchAlertCatalog(code: string, patch: CatalogPatch): Promise<void> {
  const body: Record<string, unknown> = {}
  if (patch.sendEmail !== undefined) body.send_email = patch.sendEmail
  if (patch.isActive !== undefined) body.is_active = patch.isActive
  if (patch.notifyRoles !== undefined) body.notify_roles = patch.notifyRoles
  await api(`/manager/alert-catalog/${encodeURIComponent(code)}`, { method: 'PATCH', body })
}

// ---------- runs and process compliance ----------

export interface RobotRun {
  id: number; runId: string; jobId: number; robotId: number; mode: string; dryRun: boolean; startedAt: string; endedAt: string | null
  /** DONE, STOPPED, FAULT, UNKNOWN, DRY_RUN_DONE, REFUSED, or null while running. */
  result: string | null
  completedStrokes: number
  totalStrokes: number
}

export async function managerRuns(opts: { robotId?: number; jobId?: number; page?: number; pageSize?: number } = {}): Promise<Page<RobotRun>> {
  const q = new URLSearchParams({ page: String(opts.page ?? 1), page_size: String(opts.pageSize ?? 20) })
  if (opts.robotId) q.set('robot_id', String(opts.robotId))
  if (opts.jobId) q.set('job_id', String(opts.jobId))
  const r = await api<{
    items: { id: number; run_id: string; job_id: number; robot_id: number; mode: string; dry_run: boolean; started_at: string; ended_at: string | null; result: string | null; completed_strokes: number; total_strokes: number }[]
    total: number; page: number; page_size: number
  }>(`/manager/runs?${q}`)
  return {
    items: r.items.map((x) => ({
      id: x.id, runId: x.run_id, jobId: x.job_id, robotId: x.robot_id, mode: x.mode, dryRun: x.dry_run, startedAt: x.started_at,
      endedAt: x.ended_at, result: x.result, completedStrokes: x.completed_strokes, totalStrokes: x.total_strokes,
    })),
    total: r.total, page: r.page, pageSize: r.page_size,
  }
}

export interface ComplianceStep { key: string; label: string; status: 'PASS' | 'FAIL' | 'PENDING' | 'NOT_APPLICABLE'; at: string | null; detail: string | null }
export interface Compliance { jobId: number; orderCode: string; robotCode: string; jobStatus: string; steps: ComplianceStep[]; exceptions: string[]; followedProcess: boolean }

export async function jobCompliance(jobId: number): Promise<Compliance> {
  const r = await api<{
    job_id: number; order_code: string; robot_code: string; job_status: string; exceptions: string[]; followed_process: boolean
    steps: { key: string; label_vi: string; status: ComplianceStep['status']; at: string | null; detail: string | null }[]
  }>(`/manager/jobs/${jobId}/compliance`)
  return {
    jobId: r.job_id, orderCode: r.order_code, robotCode: r.robot_code, jobStatus: r.job_status, exceptions: r.exceptions,
    followedProcess: r.followed_process, steps: r.steps.map((s) => ({ key: s.key, label: s.label_vi, status: s.status, at: s.at, detail: s.detail })),
  }
}

// ---------- job detail, events, incidents (scheduling.py) and quality (quality.py) ----------

export interface ManagerJob {
  id: number; orderId: number; orderCode: string; robotCode: string; technicianName: string; status: string; isRewrite: boolean
  slotStart: string; slotEnd: string; estimatedMin: number; progressPct: number | null; startedAt: string | null; finishedAt: string | null
  simulationPassed: boolean | null
}

export async function managerJob(jobId: number): Promise<ManagerJob> {
  const j = await api<{
    id: number; order_id: number; order_code: string; robot_code: string; technician_name: string; status: string; is_rewrite: boolean
    slot_start: string; slot_end: string; estimated_duration_min: number; progress_pct: number | null; started_at: string | null
    finished_at: string | null; simulation_passed: boolean | null
  }>(`/manager/jobs/${jobId}`)
  return {
    id: j.id, orderId: j.order_id, orderCode: j.order_code, robotCode: j.robot_code, technicianName: j.technician_name, status: j.status,
    isRewrite: j.is_rewrite, slotStart: j.slot_start, slotEnd: j.slot_end, estimatedMin: j.estimated_duration_min, progressPct: j.progress_pct,
    startedAt: j.started_at, finishedAt: j.finished_at, simulationPassed: j.simulation_passed,
  }
}

export interface JobEventRow { id: number; type: string; strokeIndex: number | null; incidentId: number | null; at: string }

export async function managerJobEvents(jobId: number, page = 1, pageSize = 50): Promise<Page<JobEventRow>> {
  const r = await api<{ items: { id: number; event_type: string; stroke_index: number | null; incident_id: number | null; occurred_at: string }[]; total: number; page: number; page_size: number }>(
    `/manager/jobs/${jobId}/events?page=${page}&page_size=${pageSize}`)
  return { items: r.items.map((e) => ({ id: e.id, type: e.event_type, strokeIndex: e.stroke_index, incidentId: e.incident_id, at: e.occurred_at })), total: r.total, page: r.page, pageSize: r.page_size }
}

export interface QualityResult {
  id: number; photoId: number; page: number; method: string
  /** PASS, NEEDS_REVIEW or FAIL, as the backend decided; its default thresholds are not validated yet (`metrics.thresholds.source`). */
  verdict: string
  overlayUrl: string | null
  createdAt: string
  /** Backend advice in Vietnamese, shown as received. */
  advisory: string
}

export async function managerJobQuality(jobId: number): Promise<QualityResult[]> {
  const rows = await api<{ id: number; photo_id: number; page: number; method: string; verdict: string; overlay_url: string | null; created_at: string; advisory: string }[]>(
    `/manager/jobs/${jobId}/quality`)
  return rows.map((q) => ({ id: q.id, photoId: q.photo_id, page: q.page, method: q.method, verdict: q.verdict, overlayUrl: q.overlay_url, createdAt: q.created_at, advisory: q.advisory }))
}

export interface Incident {
  id: number; jobId: number | null; robotId: number | null; type: 'ROBOT' | 'MATERIAL' | 'FORCE_MODULE' | 'OTHER'; description: string
  robotStatusAfter: string | null; resolvedAt: string | null; resolutionNote: string | null; createdAt: string
}

/** Newest first. `resolved=false` lists the open ones. */
export async function managerIncidents(opts: { resolved?: boolean; robotId?: number; page?: number; pageSize?: number } = {}): Promise<Page<Incident>> {
  const q = new URLSearchParams({ page: String(opts.page ?? 1), page_size: String(opts.pageSize ?? 50) })
  if (opts.resolved !== undefined) q.set('resolved', String(opts.resolved))
  if (opts.robotId) q.set('robot_id', String(opts.robotId))
  const r = await api<{
    items: { id: number; job_id: number | null; robot_id: number | null; type: Incident['type']; description: string; robot_status_after: string | null; resolved_at: string | null; resolution_note: string | null; created_at: string }[]
    total: number; page: number; page_size: number
  }>(`/manager/incidents?${q}`)
  return {
    items: r.items.map((x) => ({
      id: x.id, jobId: x.job_id, robotId: x.robot_id, type: x.type, description: x.description, robotStatusAfter: x.robot_status_after,
      resolvedAt: x.resolved_at, resolutionNote: x.resolution_note, createdAt: x.created_at,
    })),
    total: r.total, page: r.page, pageSize: r.page_size,
  }
}

/** The note is 1 to 1000 characters. */
export const resolveIncident = (id: number, note: string) => api(`/manager/incidents/${id}/resolve`, { method: 'POST', body: { note } })

// ---------- review moderation (FR-58) ----------

export interface ManagedReview {
  id: number; orderId: number; orderCode: string; customerName: string; rating: number; comment: string | null
  photos: { id: number; url: string | null }[]; hidden: boolean; hiddenAt: string | null; createdAt: string
}

export async function managerReviews(opts: { hidden?: boolean; rating?: number; page?: number; pageSize?: number } = {}): Promise<Page<ManagedReview>> {
  const q = new URLSearchParams({ page: String(opts.page ?? 1), page_size: String(opts.pageSize ?? 20) })
  if (opts.hidden !== undefined) q.set('hidden', String(opts.hidden))
  if (opts.rating) q.set('rating', String(opts.rating))
  const r = await api<{
    items: { id: number; order_id: number; order_code: string; customer_name: string; rating: number; comment: string | null; photos: { id: number; url: string | null }[]; hidden: boolean; hidden_at: string | null; created_at: string }[]
    total: number; page: number; page_size: number
  }>(`/manager/reviews?${q}`)
  return {
    items: r.items.map((x) => ({
      id: x.id, orderId: x.order_id, orderCode: x.order_code, customerName: x.customer_name, rating: x.rating, comment: x.comment,
      photos: x.photos.map((p) => ({ id: p.id, url: p.url })), hidden: x.hidden, hiddenAt: x.hidden_at, createdAt: x.created_at,
    })),
    total: r.total, page: r.page, pageSize: r.page_size,
  }
}

/** Hide or show a review again. The reason (5 to 300 characters) goes to the audit log; a review is never deleted. */
export const setReviewHidden = (id: number, hidden: boolean, reason: string) =>
  api(`/manager/reviews/${id}/${hidden ? 'hide' : 'unhide'}`, { method: 'POST', body: { reason } })
