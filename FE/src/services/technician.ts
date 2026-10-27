import { ApiError, allPages, api, newestFirst } from './api'
import type { Page } from './orders'
import type { JobStatus } from './workshop'

// Avoid hammering technician endpoints while the server's Retry-After window is active.
let rateLimitedUntil = 0
let rateLimitError: ApiError | null = null
async function techApi<T = unknown>(path: string, opts?: Parameters<typeof api>[1]): Promise<T> {
  if (rateLimitError && Date.now() < rateLimitedUntil) throw rateLimitError
  try { return await api<T>(path, opts) }
  catch (e) {
    if (e instanceof ApiError && e.status === 429) {
      rateLimitError = e
      rateLimitedUntil = Date.now() + Math.max(e.retryAfterMs ?? 30000, 1000)
    }
    throw e
  }
}

export type { JobStatus } from './workshop'

export interface TechJob {
  id: number
  orderId: number
  orderCode: string
  robotId: number
  robotCode: string
  technicianId: number
  technicianName: string
  status: JobStatus
  isRewrite: boolean
  slotStart: string
  slotEnd: string
  durationMin: number
  progress: number | null
  downloadedAt: string | null
  startedAt: string | null
  finishedAt: string | null
  simulationPassed: boolean | null
  packageHash: string | null
}

interface RawJob {
  id: number; order_id: number; order_code: string; robot_id: number; robot_code: string
  technician_id: number; technician_name: string; status: JobStatus; is_rewrite: boolean
  slot_start: string; slot_end: string; estimated_duration_min: number
  progress_pct: number | null; downloaded_at: string | null; started_at: string | null
  finished_at: string | null; simulation_passed: boolean | null
  package_hash?: string | null
}

interface RawDetail extends RawJob {
  order_type: string; quantity: number; eta: string | null; paper_name: string | null
  pen_name: string | null; ink_name: string | null; approach_note: string | null
  can_start: boolean
  calibration: { id: number; is_valid: boolean; created_at: string; checklist?: Record<string, boolean>; force_zero_offset?: number | null; probe_points?: ProbePoint[] } | null
  incidents: { id: number; type: string; description: string; resolved_at: string | null; created_at: string }[]
}

export interface TechJobDetail extends TechJob {
  orderType: string
  quantity: number
  eta: string | null
  paper: string | null
  pen: string | null
  ink: string | null
  note: string | null
  canStart: boolean
  calibration: RawDetail['calibration']
  incidents: RawDetail['incidents']
}

const toJob = (j: RawJob): TechJob => ({
  id: j.id, orderId: j.order_id, orderCode: j.order_code, robotId: j.robot_id, robotCode: j.robot_code,
  technicianId: j.technician_id, technicianName: j.technician_name, status: j.status, isRewrite: j.is_rewrite,
  slotStart: j.slot_start, slotEnd: j.slot_end, durationMin: j.estimated_duration_min,
  progress: j.progress_pct ?? null, downloadedAt: j.downloaded_at ?? null,
  startedAt: j.started_at ?? null, finishedAt: j.finished_at ?? null, simulationPassed: j.simulation_passed ?? null,
  packageHash: j.package_hash ?? null,
})

export interface TechJobQuery {
  status?: JobStatus[]
  from?: string
  to?: string
  page?: number
  pageSize?: number
}

/** The backend scopes these jobs to the authenticated technician, without a local roster ID. */
export async function listTechJobs(opts: TechJobQuery = {}): Promise<Page<TechJob>> {
  const q = new URLSearchParams()
  for (const status of opts.status ?? []) q.append('status', status)
  if (opts.from) q.set('from', opts.from)
  if (opts.to) q.set('to', opts.to)
  q.set('page', String(opts.page ?? 1))
  q.set('page_size', String(opts.pageSize ?? 50))
  const r = await techApi<{ items: RawJob[]; total: number; page: number; page_size: number }>(`/technician/jobs?${q}`)
  return { items: r.items.map(toJob), total: r.total, page: r.page, pageSize: r.page_size }
}

/** Include every page so the dashboard totals and robot assignments are not truncated at 50 jobs. */
export async function allTechJobs(): Promise<TechJob[]> {
  const jobs = new Map<number, TechJob>()
  let page = 1
  while (true) {
    const r = await listTechJobs({ page, pageSize: 200 })
    for (const job of r.items) jobs.set(job.id, job)
    if (r.items.length === 0 || r.page * r.pageSize >= r.total) break
    page++
  }
  return [...jobs.values()]
}

export async function getTechJob(id: number): Promise<TechJobDetail> {
  if (!Number.isSafeInteger(id) || id <= 0) throw new ApiError(404, 'JOB_NOT_FOUND', 'Job not found')
  const j = await techApi<RawDetail>(`/technician/jobs/${id}`)
  return { ...toJob(j), orderType: j.order_type, quantity: j.quantity, eta: j.eta,
    paper: j.paper_name, pen: j.pen_name, ink: j.ink_name, note: j.approach_note,
    canStart: j.can_start, calibration: j.calibration, incidents: j.incidents }
}

export interface ProbePoint { x: number; y: number; z: number }
export interface JobPackage {
  job_id: number; order_code: string; package_hash: string; hash_algorithm: 'SHA-256'
  trajectory_url: string; trajectory_url_expires_in: number; trajectory_format: string; pages: number
  paper: { name: string; size: string; gsm: number } | null
  pen: { name: string; f_target_n: number; f_min_n: number; f_max_n: number; f_hard_n: number; v_max_mm_s: number } | null
  preview_url: string | null
}
export interface TrajectoryPage { paper: { width_mm: number; height_mm: number }; strokes: { points: number[][] }[] }
export interface VerifiedPackage { info: JobPackage; bytes: ArrayBuffer; pages: TrajectoryPage[]; hash: string }

export async function verifyPackageBytes(bytes: ArrayBuffer, expected: string): Promise<string> {
  if (!globalThis.crypto?.subtle) throw new Error('td.flow.cryptoUnavailable')
  const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes)
  const hash = Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('')
  if (hash !== expected.toLowerCase()) throw new ApiError(409, 'JOB_HASH_MISMATCH', 'td.flow.hashMismatch')
  return hash
}

/** A signed storage request must not contain the application's bearer token or cookies. */
async function storageBytes(url: string): Promise<ArrayBuffer> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), 75000)
  try {
    const res = await fetch(url, { credentials: 'omit', signal: ctrl.signal })
    if (!res.ok) throw new ApiError(res.status, 'STORAGE_DOWNLOAD_FAILED', 'td.flow.downloadFailed')
    return await res.arrayBuffer()
  } finally { clearTimeout(timer) }
}

export async function downloadJobPackage(id: number): Promise<VerifiedPackage> {
  const info = await techApi<JobPackage>(`/technician/jobs/${id}/package`)
  const bytes = await storageBytes(info.trajectory_url)
  const hash = await verifyPackageBytes(bytes, info.package_hash)
  // Parse only after the exact downloaded bytes have been verified.
  let data: { format?: string; pages?: TrajectoryPage[] }
  try { data = JSON.parse(new TextDecoder().decode(bytes)) } catch { throw new Error('td.flow.invalidPackage') }
  if (!data || data.format !== info.trajectory_format || !Array.isArray(data.pages) || data.pages.length !== info.pages || data.pages.length === 0) throw new Error('td.flow.invalidPackage')
  if (data.pages.some((p) => !Number.isFinite(p.paper?.width_mm) || !Number.isFinite(p.paper?.height_mm) || p.paper.width_mm <= 0 || p.paper.height_mm <= 0 || !Array.isArray(p.strokes) || p.strokes.some((s) => !Array.isArray(s.points) || s.points.some((pt) => !Array.isArray(pt) || pt.length < 2 || !Number.isFinite(pt[0]) || !Number.isFinite(pt[1]))))) throw new Error('td.flow.invalidPackage')
  return { info, bytes, hash, pages: data.pages }
}

const jobAction = async (id: number, action: string, body?: unknown) => toJob(await techApi<RawJob>(`/technician/jobs/${id}/${action}`, { method: 'POST', body }))
export const prepareJob = (id: number) => jobAction(id, 'prepare')
export const simulateJob = (id: number, body: { passed: boolean; errors: string[]; report?: Record<string, unknown> }) => jobAction(id, 'simulation', body)
export const startJob = (id: number) => jobAction(id, 'start')
export const finishJob = (id: number) => jobAction(id, 'finish')
export type ClientEvent = 'PROGRESS' | 'PAUSE' | 'RESUME' | 'ESTOP' | 'OVER_FORCE' | 'STROKE_LOST' | 'SENSOR_LOST' | 'FORCE_SUMMARY'
export const CLIENT_EVENTS: ClientEvent[] = ['PROGRESS', 'PAUSE', 'RESUME', 'ESTOP', 'OVER_FORCE', 'STROKE_LOST', 'SENSOR_LOST', 'FORCE_SUMMARY']
export interface JobEvent {
  id: number; event_type: string; occurred_at: string; stroke_index: number | null
  force_summary: Record<string, unknown> | null; payload: Record<string, unknown> | null
}
export interface EventInput { event_type: ClientEvent; progress_pct?: number; stroke_index?: number; force_summary?: Record<string, number>; payload?: Record<string, unknown> }
export const postJobEvent = (id: number, body: EventInput) => {
  if (!CLIENT_EVENTS.includes(body.event_type)) throw new Error('td.flow.invalidEvent')
  return techApi<JobEvent>(`/technician/jobs/${id}/events`, { method: 'POST', body })
}
export async function jobEvents(id: number, page = 1, pageSize = 50) {
  return techApi<{ items: JobEvent[]; total: number; page: number; page_size: number }>(`/technician/jobs/${id}/events?page=${page}&page_size=${pageSize}`)
}
/** The whole history of a job, latest event first (the backend pages it oldest first). */
export const allJobEvents = async (id: number) =>
  newestFirst(await allPages((page) => jobEvents(id, page, 500), 500), (e) => e.occurred_at)
export const INCIDENT_TYPES = ['ROBOT', 'MATERIAL', 'FORCE_MODULE', 'OTHER'] as const
export interface IncidentInput { type: typeof INCIDENT_TYPES[number]; description: string; robot_status_after?: 'MAINTENANCE' | 'BROKEN' }
export const reportIncident = (id: number, body: IncidentInput) => techApi(`/technician/jobs/${id}/incidents`, { method: 'POST', body })

export type PhotoKind = 'OVERALL' | 'CLOSE_UP' | 'OTHER'
export type QcResult = 'PASS' | 'FAIL'
export interface ProductPhoto { id: number; kind: PhotoKind; qc_result: QcResult | null; qc_note: string | null; url: string | null; url_expires_in: number; created_at: string }
export interface PhotoTicket { photo_key: string; upload_url: string; method: string; expires_in: number }
export const jobPhotos = (id: number) => techApi<ProductPhoto[]>(`/technician/jobs/${id}/photos`)
export const requestPhotoUpload = (id: number, file: File) => techApi<PhotoTicket>(`/technician/jobs/${id}/photos/upload-url`, { method: 'POST', body: { mime_type: file.type, size_bytes: file.size } })
export function uploadPhotoBinary(ticket: PhotoTicket, file: File, progress: (n: number) => void): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open(ticket.method || 'PUT', ticket.upload_url)
    xhr.timeout = 75000
    xhr.withCredentials = false
    xhr.setRequestHeader('Content-Type', file.type)
    xhr.upload.onprogress = (e) => { if (e.lengthComputable) progress(Math.round(e.loaded / e.total * 100)) }
    xhr.onload = () => xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error('td.flow.uploadFailed'))
    xhr.onerror = () => reject(new Error('td.flow.uploadFailed'))
    xhr.ontimeout = () => reject(new Error('td.flow.uploadFailed'))
    xhr.onabort = () => reject(new Error('td.flow.uploadFailed'))
    xhr.send(file)
  })
}
export const registerPhoto = (id: number, photo_key: string, kind: PhotoKind) => techApi<ProductPhoto>(`/technician/jobs/${id}/photos`, { method: 'POST', body: { photo_key, kind } })
export const setPhotoQc = (id: number, photoId: number, qc_result: QcResult, qc_note?: string) => techApi<ProductPhoto>(`/technician/jobs/${id}/photos/${photoId}`, { method: 'PATCH', body: { qc_result, qc_note: qc_note?.trim() || null } })
export const removePhoto = (id: number, photoId: number) => techApi(`/technician/jobs/${id}/photos/${photoId}`, { method: 'DELETE' })
export const submitPhotos = (id: number) => jobAction(id, 'photos/submit')
export const failJobQc = (id: number, note: string) => jobAction(id, 'qc-fail', { note: note.trim() })
export const photosReady = (photos: ProductPhoto[]) => photos.length >= 2 && photos.length <= 10 && ['OVERALL', 'CLOSE_UP'].every((k) => photos.some((p) => p.kind === k)) && photos.every((p) => p.qc_result === 'PASS')

export function jobPermissions(job: TechJobDetail, hash?: string) {
  const verified = !!hash && !!job.packageHash && hash === job.packageHash
  return {
    download: PREVIEW_JOB_STATUSES.includes(job.status),
    prepare: job.status === 'SCHEDULED' && verified && !!job.downloadedAt,
    simulate: job.status === 'PREPARING' && verified && !!job.calibration?.is_valid,
    start: job.status === 'PREPARING' && verified && !!job.downloadedAt && !!job.calibration?.is_valid && job.simulationPassed === true && job.canStart,
    finish: job.status === 'WRITING',
    incident: ['PREPARING', 'WRITING', 'PAUSED'].includes(job.status),
    photos: job.status === 'WRITTEN',
  }
}
export function eventAllowed(status: JobStatus, event: ClientEvent) {
  if (event === 'PROGRESS' || event === 'PAUSE') return status === 'WRITING'
  if (event === 'RESUME') return status === 'PAUSED'
  if (event === 'FORCE_SUMMARY') return ['WRITING', 'PAUSED', 'WRITTEN'].includes(status)
  return status === 'WRITING' || status === 'PAUSED'
}

export const ACTIVE_JOB_STATUSES: JobStatus[] = ['SCHEDULED', 'PREPARING', 'WRITING', 'PAUSED', 'WRITTEN']
export const PREVIEW_JOB_STATUSES: JobStatus[] = ['SCHEDULED', 'PREPARING', 'WRITING', 'PAUSED']
export const jobPath = (id: number) => `/tech/jobs/${id}`

export function jobTone(status: JobStatus): string {
  if (status === 'FAILED' || status === 'REWRITE_REQUIRED') return 'warn'
  if (status === 'WRITING' || status === 'PAUSED' || status === 'WRITTEN') return 'orange'
  if (status === 'SCHEDULED' || status === 'PREPARING') return 'info'
  return 'mute'
}
