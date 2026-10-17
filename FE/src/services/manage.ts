import { api } from './api'
import { num } from './orders'

/** Manager only: materials, stock, compatibility, writing templates, handwriting styles, robots and the versioned price list (`/manager/*`). */

export type PenCategory = 'BALLPOINT' | 'GEL' | 'FINELINER' | 'FOUNTAIN' | 'BRUSH' | 'MARKER'
export const PEN_CATEGORIES: PenCategory[] = ['BALLPOINT', 'GEL', 'FINELINER', 'FOUNTAIN', 'BRUSH', 'MARKER']
export const SURFACES = ['PLAIN', 'ART', 'GLOSSY', 'COATED', 'CARD', 'OTHER'] as const
export const PAPER_SIZES = ['A6', 'A5', 'A4'] as const
export const TEMPLATE_KINDS = ['TYPOGRAPHY', 'CALLIGRAPHY', 'SINGLE_LINE_FONT'] as const

export interface StockChange {
  mode: 'ADD' | 'SET'
  quantity: number
  reason: string
}

// ---------- papers ----------

export interface AdminPaper {
  id: number
  code: string
  name: string
  gsm: number
  surface: string
  size: string
  unitPrice: number
  stock: number
  active: boolean
}

interface RawPaper { id: number; code: string; name: string; gsm: number; surface: string; size: string; unit_price: string; stock_qty: number; is_active: boolean }
const toPaper = (p: RawPaper): AdminPaper => ({
  id: p.id, code: p.code, name: p.name, gsm: p.gsm, surface: p.surface, size: p.size, unitPrice: num(p.unit_price) ?? 0, stock: p.stock_qty, active: p.is_active,
})

export const adminPapers = async () => (await api<RawPaper[]>('/manager/papers')).map(toPaper)
export const createPaper = async (b: { code: string; name: string; gsm: number; surface: string; size: string; unit_price: number; stock_qty?: number }) =>
  toPaper(await api<RawPaper>('/manager/papers', { method: 'POST', body: b }))
export const patchPaper = async (id: number, b: Partial<{ name: string; gsm: number; surface: string; size: string; unit_price: number; is_active: boolean }>) =>
  toPaper(await api<RawPaper>(`/manager/papers/${id}`, { method: 'PATCH', body: b }))
export const stockPaper = async (id: number, b: StockChange) => toPaper(await api<RawPaper>(`/manager/papers/${id}/stock`, { method: 'POST', body: b }))

// ---------- pens ----------

export interface AdminPen {
  id: number
  code: string
  name: string
  category: PenCategory
  widthMm: number
  surcharge: number
  stock: number
  active: boolean
  fTarget: number
  fMin: number
  fMax: number
  fHard: number
  vMax: number
}

interface RawPen {
  id: number; code: string; name: string; category: PenCategory; stroke_width_mm: string; surcharge: string; stock_qty: number; is_active: boolean
  f_target_n: string; f_min_n: string; f_max_n: string; f_hard_n: string; v_max_mm_s: string
}
const toPen = (p: RawPen): AdminPen => ({
  id: p.id, code: p.code, name: p.name, category: p.category, widthMm: num(p.stroke_width_mm) ?? 0, surcharge: num(p.surcharge) ?? 0, stock: p.stock_qty,
  active: p.is_active, fTarget: num(p.f_target_n) ?? 0, fMin: num(p.f_min_n) ?? 0, fMax: num(p.f_max_n) ?? 0, fHard: num(p.f_hard_n) ?? 0, vMax: num(p.v_max_mm_s) ?? 0,
})

export const adminPens = async () => (await api<RawPen[]>('/manager/pens')).map(toPen)
export const createPen = async (b: {
  code: string; name: string; category: PenCategory; stroke_width_mm: number; f_target_n: number; f_min_n: number; f_max_n: number; f_hard_n: number
  v_max_mm_s: number; surcharge: number; stock_qty?: number
}) => toPen(await api<RawPen>('/manager/pens', { method: 'POST', body: b }))
export const patchPen = async (id: number, b: Partial<{ name: string; category: PenCategory; stroke_width_mm: number; surcharge: number; is_active: boolean }>) =>
  toPen(await api<RawPen>(`/manager/pens/${id}`, { method: 'PATCH', body: b }))
export const stockPen = async (id: number, b: StockChange) => toPen(await api<RawPen>(`/manager/pens/${id}/stock`, { method: 'POST', body: b }))

// ---------- inks ----------

export interface AdminInk {
  id: number
  penId: number
  name: string
  hex: string | null
  unitPrice: number
  stock: number
  active: boolean
}

interface RawInk { id: number; pen_type_id: number; name: string; hex_code: string | null; unit_price: string; stock_qty: number; is_active: boolean }
const toInk = (i: RawInk): AdminInk => ({ id: i.id, penId: i.pen_type_id, name: i.name, hex: i.hex_code, unitPrice: num(i.unit_price) ?? 0, stock: i.stock_qty, active: i.is_active })

export const adminInks = async (penId?: number) => (await api<RawInk[]>(`/manager/inks${penId ? `?pen_id=${penId}` : ''}`)).map(toInk)
export const createInk = async (penId: number, b: { name: string; hex_code: string | null; unit_price: number; stock_qty?: number }) =>
  toInk(await api<RawInk>(`/manager/pens/${penId}/inks`, { method: 'POST', body: b }))
export const patchInk = async (id: number, b: Partial<{ name: string; hex_code: string | null; unit_price: number; is_active: boolean }>) =>
  toInk(await api<RawInk>(`/manager/inks/${id}`, { method: 'PATCH', body: b }))
export const stockInk = async (id: number, b: StockChange) => toInk(await api<RawInk>(`/manager/inks/${id}/stock`, { method: 'POST', body: b }))

// ---------- compatibility ----------

export interface Compat {
  paperId: number
  penId: number
  compatible: boolean
  note: string | null
}

export const adminCompat = async (): Promise<Compat[]> =>
  (await api<{ paper_type_id: number; pen_type_id: number; is_compatible: boolean; note: string | null }[]>('/manager/compatibility')).map((c) => ({
    paperId: c.paper_type_id, penId: c.pen_type_id, compatible: c.is_compatible, note: c.note,
  }))
export const setCompat = (paperId: number, penId: number, compatible: boolean, note?: string) =>
  api(`/manager/compatibility/${paperId}/${penId}`, { method: 'PUT', body: { is_compatible: compatible, ...(note ? { note } : {}) } })

// ---------- templates and styles ----------

export interface AdminTemplate {
  id: number
  code: string
  name: string
  kind: string
  fontUri: string
  active: boolean
}

interface RawTemplate { id: number; code: string; name: string; kind: string; font_uri: string; is_active: boolean }
const toTemplate = (x: RawTemplate): AdminTemplate => ({ id: x.id, code: x.code, name: x.name, kind: x.kind, fontUri: x.font_uri, active: x.is_active })

export const adminTemplates = async () => (await api<RawTemplate[]>('/manager/templates')).map(toTemplate)
export const createTemplate = async (b: { code: string; name: string; kind: string; font_uri: string }) =>
  toTemplate(await api<RawTemplate>('/manager/templates', { method: 'POST', body: b }))
export const patchTemplate = async (id: number, b: Partial<{ name: string; kind: string; font_uri: string; is_active: boolean }>) =>
  toTemplate(await api<RawTemplate>(`/manager/templates/${id}`, { method: 'PATCH', body: b }))

export interface StyleRow {
  id: number
  ownerId: number
  name: string
  status: string
  coverage: number | null
  rightToUse: boolean
  createdAt: string
}

export const adminStyles = async (status = 'PENDING_REVIEW'): Promise<StyleRow[]> =>
  (await api<{ id: number; owner_id: number; name: string; status: string; coverage_pct: string | null; right_to_use_confirmed: boolean; created_at: string }[]>(
    `/manager/styles?status=${status}`,
  )).map((s) => ({ id: s.id, ownerId: s.owner_id, name: s.name, status: s.status, coverage: num(s.coverage_pct), rightToUse: s.right_to_use_confirmed, createdAt: s.created_at }))
export const approveStyle = (id: number) => api(`/manager/styles/${id}/approve`, { method: 'POST' })
export const rejectStyle = (id: number, reason: string) => api(`/manager/styles/${id}/reject`, { method: 'POST', body: { reason } })

// ---------- robots ----------

export interface AdminRobot {
  id: number
  code: string
  type: string
  station: string | null
  status: 'AVAILABLE' | 'BUSY' | 'MAINTENANCE' | 'BROKEN'
  simulated: boolean
  penCategories: PenCategory[]
  note: string | null
  affectedJobs: number[]
}

interface RawRobot {
  id: number; code: string; robot_type: string; station: string | null; status: AdminRobot['status']; is_simulated: boolean
  supported_pen_categories: PenCategory[] | null; note: string | null; affected_job_ids?: number[]
}
const toRobot = (r: RawRobot): AdminRobot => ({
  id: r.id, code: r.code, type: r.robot_type, station: r.station, status: r.status, simulated: r.is_simulated,
  penCategories: r.supported_pen_categories ?? [], note: r.note, affectedJobs: r.affected_job_ids ?? [],
})

export const adminRobots = async () => (await api<RawRobot[]>('/manager/robots')).map(toRobot)
export const createRobot = async (b: { code: string; station?: string | null; status?: AdminRobot['status']; supported_pen_categories?: PenCategory[] | null; note?: string | null }) =>
  toRobot(await api<RawRobot>('/manager/robots', { method: 'POST', body: b }))
export const patchRobot = async (id: number, b: Partial<{ station: string | null; status: AdminRobot['status']; supported_pen_categories: PenCategory[] | null; note: string | null }>) =>
  toRobot(await api<RawRobot>(`/manager/robots/${id}`, { method: 'PATCH', body: b }))

// ---------- price list ----------

export interface PriceList {
  version: number
  active: boolean
  uOt1: number; uOt2: number; uOt3: number
  wMin: number
  sOt1: number; sOt2: number; sOt3: number
  kSimple: number; kMedium: number; kComplex: number
  tiers: { minQty: number; pct: number }[]
  minDepositPct: number
  adjustThresholdPct: number
  canvasMmPerChar: number
  note: string | null
  createdAt: string
}

interface RawPrice {
  version: number; is_active: boolean; u_ot1: string; u_ot2: string; u_ot3: string; w_min: string; s_ot1: string; s_ot2: string; s_ot3: string
  k_simple: string; k_medium: string; k_complex: string; discount_tiers: { min_qty: number; pct: string | number }[]
  p_min_pct: string; adjust_threshold_pct: string; canvas_mm_per_char: string; note: string | null; created_at: string
}
const toPrice = (p: RawPrice): PriceList => ({
  version: p.version, active: p.is_active, uOt1: num(p.u_ot1) ?? 0, uOt2: num(p.u_ot2) ?? 0, uOt3: num(p.u_ot3) ?? 0, wMin: num(p.w_min) ?? 0,
  sOt1: num(p.s_ot1) ?? 0, sOt2: num(p.s_ot2) ?? 0, sOt3: num(p.s_ot3) ?? 0, kSimple: num(p.k_simple) ?? 1, kMedium: num(p.k_medium) ?? 1, kComplex: num(p.k_complex) ?? 1,
  tiers: p.discount_tiers.map((t) => ({ minQty: t.min_qty, pct: Number(t.pct) })), minDepositPct: num(p.p_min_pct) ?? 50,
  adjustThresholdPct: num(p.adjust_threshold_pct) ?? 15, canvasMmPerChar: num(p.canvas_mm_per_char) ?? 0, note: p.note, createdAt: p.created_at,
})

export const priceVersions = async () => (await api<RawPrice[]>('/manager/pricing-config/versions')).map(toPrice)
/** Sends only the fields that changed; the backend copies the rest and makes version N+1 active. */
export const savePrice = async (b: Record<string, unknown>) => toPrice(await api<RawPrice>('/manager/pricing-config', { method: 'POST', body: b }))
