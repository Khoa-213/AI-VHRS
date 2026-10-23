import { ApiError, api } from './api'
import { num, type Page } from './orders'
import type { JobStatus } from './workshop'

/**
 * Technician side (`/technician/*`, role TECHNICAL_STAFF, contract in BE/docs/FE_API_GUIDE.md sections 7b and 7c).
 * Only the jobs assigned to the signed-in technician are visible. The backend does not drive the robot: this app
 * reports calibration, simulation, progress and the finish, and the backend guards the order of the steps.
 */

export type { JobStatus }
export type PhotoKind = 'OVERALL' | 'CLOSE_UP' | 'OTHER'
export type QcResult = 'PASS' | 'FAIL'
export type IncidentType = 'ROBOT' | 'MATERIAL' | 'FORCE_MODULE' | 'OTHER'
export const INCIDENT_TYPES: IncidentType[] = ['ROBOT', 'MATERIAL', 'FORCE_MODULE', 'OTHER']

/** Job statuses the technician still has work on, in the order they happen. */
export const OPEN_STATUSES: JobStatus[] = ['SCHEDULED', 'PREPARING', 'WRITING', 'PAUSED', 'WRITTEN']

// ---------- jobs ----------

export interface TechJob {
  id: number
  orderId: number
  orderCode: string
  robotId: number
  robotCode: string
  status: JobStatus
  isRewrite: boolean
  slotStart: string
  slotEnd: string
  durationMin: number
  packageHash: string | null
  progressPct: number | null
  downloadedAt: string | null
  startedAt: string | null
  finishedAt: string | null
  simulationPassed: boolean | null
}

export interface Incident {
  id: number
  type: IncidentType
  description: string
  createdAt: string
  resolvedAt: string | null
}

export interface Calibration {
  id: number
  isValid: boolean
  forceZeroOffset: number | null
  createdAt: string
}

export interface TechJobDetail extends TechJob {
  orderType: string
  quantity: number
  eta: string | null
  paperName: string | null
  penName: string | null
  inkName: string | null
  approachNote: string | null
  calibration: Calibration | null
  canStart: boolean
  incidents: Incident[]
}

interface RawJob {
  id: number; order_id: number; order_code?: string; robot_id: number; robot_code?: string; status: JobStatus; is_rewrite: boolean
  slot_start: string; slot_end: string; estimated_duration_min: number; package_hash: string | null; progress_pct?: number | null
  downloaded_at?: string | null; started_at?: string | null; finished_at?: string | null; simulation_passed?: boolean | null
}

interface RawDetail extends RawJob {
  order_type?: string; quantity?: number; eta?: string | null; paper_name?: string | null; pen_name?: string | null
  ink_name?: string | null; approach_note?: string | null; can_start?: boolean
  calibration?: { id: number; is_valid: boolean; force_zero_offset: number | null; created_at: string } | null
  incidents?: { id: number; type: IncidentType; description: string; created_at: string; resolved_at: string | null }[]
}

const toJob = (j: RawJob): TechJob => ({
  id: j.id, orderId: j.order_id, orderCode: j.order_code ?? '', robotId: j.robot_id, robotCode: j.robot_code ?? '', status: j.status,
  isRewrite: j.is_rewrite, slotStart: j.slot_start, slotEnd: j.slot_end, durationMin: j.estimated_duration_min,
  packageHash: j.package_hash, progressPct: num(j.progress_pct ?? null), downloadedAt: j.downloaded_at ?? null,
  startedAt: j.started_at ?? null, finishedAt: j.finished_at ?? null, simulationPassed: j.simulation_passed ?? null,
})

const toDetail = (j: RawDetail): TechJobDetail => ({
  ...toJob(j),
  orderType: j.order_type ?? '', quantity: j.quantity ?? 1, eta: j.eta ?? null, paperName: j.paper_name ?? null, penName: j.pen_name ?? null,
  inkName: j.ink_name ?? null, approachNote: j.approach_note ?? null, canStart: !!j.can_start,
  calibration: j.calibration ? { id: j.calibration.id, isValid: j.calibration.is_valid, forceZeroOffset: j.calibration.force_zero_offset, createdAt: j.calibration.created_at } : null,
  incidents: (j.incidents ?? []).map((i) => ({ id: i.id, type: i.type, description: i.description, createdAt: i.created_at, resolvedAt: i.resolved_at })),
})

export async function listMyJobs(opts: { status?: JobStatus[]; page?: number; pageSize?: number } = {}): Promise<Page<TechJob>> {
  const q = new URLSearchParams()
  for (const st of opts.status ?? []) q.append('status', st)
  q.set('page', String(opts.page ?? 1))
  q.set('page_size', String(opts.pageSize ?? 100))
  const r = await api<{ items: RawJob[]; total: number; page: number; page_size: number }>(`/technician/jobs?${q}`)
  return { items: r.items.map(toJob), total: r.total, page: r.page, pageSize: r.page_size }
}

export const getMyJob = async (id: number) => toDetail(await api<RawDetail>(`/technician/jobs/${id}`))

export interface JobPackage {
  jobId: number
  orderCode: string
  quantity: number
  isRewrite: boolean
  durationMin: number
  /** SHA-256 (hex) of the trajectory file. The workstation must check it before it runs anything (MSG14). */
  hash: string
  trajectoryUrl: string
  trajectoryFormat: string
  pages: number
  paper: { name: string; gsm: number; surface: string; size: string } | null
  pen: { name: string; category: string; strokeWidthMm: number; fTargetN: number; fMinN: number; fMaxN: number; fHardN: number; vMaxMmS: number } | null
  inkName: string | null
  inkHex: string | null
  approachNote: string | null
  previewUrl: string | null
}

interface RawPackage {
  job_id: number; order_code: string; quantity: number; is_rewrite: boolean; estimated_duration_min: number; package_hash: string
  trajectory_url: string; trajectory_format: string; pages: number; ink_name: string | null; ink_hex: string | null
  approach_note: string | null; preview_url: string | null
  paper: JobPackage['paper']
  pen: { name: string; category: string; stroke_width_mm: number; f_target_n: number; f_min_n: number; f_max_n: number; f_hard_n: number; v_max_mm_s: number } | null
}

/** Fetching the package also records the download on the job, which `prepare` requires. */
export async function getPackage(id: number): Promise<JobPackage> {
  const p = await api<RawPackage>(`/technician/jobs/${id}/package`)
  return {
    jobId: p.job_id, orderCode: p.order_code, quantity: p.quantity, isRewrite: p.is_rewrite, durationMin: p.estimated_duration_min,
    hash: p.package_hash, trajectoryUrl: p.trajectory_url, trajectoryFormat: p.trajectory_format, pages: p.pages, paper: p.paper,
    pen: p.pen && {
      name: p.pen.name, category: p.pen.category, strokeWidthMm: p.pen.stroke_width_mm, fTargetN: p.pen.f_target_n,
      fMinN: p.pen.f_min_n, fMaxN: p.pen.f_max_n, fHardN: p.pen.f_hard_n, vMaxMmS: p.pen.v_max_mm_s,
    },
    inkName: p.ink_name, inkHex: p.ink_hex, approachNote: p.approach_note, previewUrl: p.preview_url,
  }
}

const hex = (buf: ArrayBuffer) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('')

/** Downloads the trajectory file and compares its SHA-256 with the package hash. Returns the parsed file when they match. */
export async function fetchVerifiedTrajectory(pkg: JobPackage): Promise<{ ok: boolean; hash: string; data: unknown }> {
  let res: Response
  try {
    res = await fetch(pkg.trajectoryUrl)
  } catch (e) {
    throw new ApiError(0, 'NETWORK', e instanceof Error ? e.message : 'Network error')
  }
  if (!res.ok) throw new ApiError(res.status, 'DOWNLOAD_FAILED', `Download failed (${res.status})`)
  const bytes = await res.arrayBuffer()
  const hash = hex(await crypto.subtle.digest('SHA-256', bytes))
  return { ok: hash === pkg.hash.toLowerCase(), hash, data: JSON.parse(new TextDecoder().decode(bytes)) as unknown }
}

const post = async (id: number, step: string, body?: unknown) => toJob(await api<RawJob>(`/technician/jobs/${id}/${step}`, { method: 'POST', body }))

export const prepareJob = (id: number) => post(id, 'prepare')
export const startJob = (id: number) => post(id, 'start')
export const finishJob = (id: number) => post(id, 'finish')

export interface ProbePoint { x: number; y: number; z: number }

export const saveCalibration = (id: number, body: {
  checklist: { frame_mounted: true; paper_clamped: true; pen_installed: true; force_zeroed: true }
  force_zero_offset: number
  probe_points: ProbePoint[]
}) => api(`/technician/jobs/${id}/calibration`, { method: 'POST', body })

export const saveSimulation = (id: number, body: { passed: boolean; errors?: string[] }) => post(id, 'simulation', body)

export type ReportedEvent = 'PROGRESS' | 'PAUSE' | 'RESUME' | 'ESTOP' | 'OVER_FORCE' | 'STROKE_LOST' | 'SENSOR_LOST'

export const reportEvent = (id: number, body: { event_type: ReportedEvent; progress_pct?: number; stroke_index?: number }) =>
  api(`/technician/jobs/${id}/events`, { method: 'POST', body })

export const reportIncident = (id: number, body: { type: IncidentType; description: string; robot_status_after?: 'MAINTENANCE' | 'BROKEN' }) =>
  api(`/technician/jobs/${id}/incidents`, { method: 'POST', body })

// ---------- product photos and QC (UC-38) ----------

export interface Photo {
  id: number
  jobId: number
  kind: PhotoKind
  qc: QcResult | null
  note: string | null
  createdAt: string
  /** Signed link, valid for `urlExpiresIn` seconds. */
  url: string | null
  urlExpiresIn: number
}

interface RawPhoto {
  id: number; job_id: number; kind: PhotoKind; qc_result: QcResult | null; qc_note: string | null; created_at: string
  url: string | null; url_expires_in: number
}

const toPhoto = (p: RawPhoto): Photo => ({
  id: p.id, jobId: p.job_id, kind: p.kind, qc: p.qc_result, note: p.qc_note, createdAt: p.created_at, url: p.url, urlExpiresIn: p.url_expires_in,
})

/** BR-21: at least two photos, an OVERALL and a CLOSE_UP among them, every one marked PASS. */
export const MIN_LONG_SIDE_PX = 1280
export const MAX_PHOTOS = 10

export const listPhotos = async (jobId: number) => (await api<RawPhoto[]>(`/technician/jobs/${jobId}/photos`)).map(toPhoto)

/** Three steps: ask for a signed link, PUT the file straight to storage (no token), then register it with its kind. */
export async function uploadPhoto(jobId: number, file: File, kind: PhotoKind, qc?: { result: QcResult; note?: string }): Promise<Photo> {
  const ticket = await api<{ photo_key: string; upload_url: string; method: string }>(`/technician/jobs/${jobId}/photos/upload-url`, {
    method: 'POST',
    body: { mime_type: file.type, size_bytes: file.size },
  })
  let res: Response
  try {
    res = await fetch(ticket.upload_url, { method: ticket.method || 'PUT', headers: { 'Content-Type': file.type }, body: file })
  } catch (e) {
    throw new ApiError(0, 'NETWORK', e instanceof Error ? e.message : 'Network error')
  }
  if (!res.ok) throw new ApiError(res.status, 'UPLOAD_FAILED', `Upload failed (${res.status})`)
  return toPhoto(await api<RawPhoto>(`/technician/jobs/${jobId}/photos`, {
    method: 'POST',
    body: { photo_key: ticket.photo_key, kind, ...(qc ? { qc_result: qc.result, qc_note: qc.note ?? null } : {}) },
  }))
}

export const setPhotoQc = async (jobId: number, photoId: number, result: QcResult, note?: string) =>
  toPhoto(await api<RawPhoto>(`/technician/jobs/${jobId}/photos/${photoId}`, { method: 'PATCH', body: { qc_result: result, qc_note: note?.trim() || null } }))

export const removePhoto = (jobId: number, photoId: number) => api(`/technician/jobs/${jobId}/photos/${photoId}`, { method: 'DELETE' })

/** Hands the photos to the customer: job PHOTO_UPLOADED, order AWAITING_ACCEPTANCE. */
export const submitPhotos = (jobId: number) => post(jobId, 'photos/submit')

/** The product is not good enough: the job goes back to the Manager's queue to be scheduled again. */
export const failQc = (jobId: number, note: string) => post(jobId, 'qc-fail', { note })
