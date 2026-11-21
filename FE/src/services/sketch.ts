/**
 * The customer's working sketch of a draft order (V2, `BE/docs/FE_API_GUIDE.md` sections 7r, 7u, 7w).
 *
 * The backend keeps a tree of revisions and a cursor (`current`). The create-order editor also keeps an
 * **applied** revision per order: the one the canvas shows and the one that is sent to the workshop. Assistant edits
 * move the backend cursor to a new revision straight away, so they are only *proposals* until the customer presses
 * "Apply" in the chat. Before anything that writes from the canvas (a manual edit, a redraw, submitting) the cursor is
 * moved back to the applied revision with undo / redo (`moveTo`).
 */
import { ApiError, api, apiFile } from './api'

export type SketchOp = 'translate' | 'rotate' | 'scale' | 'slant' | 'curvature' | 'smooth' | 'extend' | 'trim' | 'join' | 'split' | 'delete'

export interface SketchStroke {
  id: string
  kind: string
  points: [number, number][]
  word: string | null
  provenance: string
  edited_by?: string[]
}
export interface SketchWord { id: string; stroke_ids: string[]; bbox: [number, number, number, number]; text?: string | null }
export interface SketchLine { id: string; word_ids: string[]; bbox: [number, number, number, number]; paragraph: string | null }
export interface SketchParagraph { id: string; line_ids: string[]; bbox: [number, number, number, number] }
export interface SketchPage {
  no: number
  width_mm: number
  height_mm: number
  strokes: SketchStroke[]
  words: SketchWord[]
  lines?: SketchLine[]
  paragraphs?: SketchParagraph[]
}

export interface SketchRevision {
  id: number
  seq: number
  parentId: number | null
  author: 'ENGINE' | 'CUSTOMER' | 'AI' | 'STAFF' | string
  note: string | null
  createdAt: string
}

/** How far one edit may go for this order type (sliders). Keys follow the backend's `limits`. */
export interface SketchLimits {
  name?: string
  max_shift_mm?: number
  max_rotate_deg?: number
  scale_range?: [number, number]
  max_slant_deg?: number
  curvature_range?: [number, number]
  max_extend_mm?: number
  max_join_gap_mm?: number
}

export interface WorkingSketch {
  revision: SketchRevision
  isCurrent: boolean
  canUndo: boolean
  canRedo: boolean
  inputsChanged: boolean
  inputsRestored: boolean
  limits: SketchLimits
  pages: SketchPage[]
  redraw: { reapplied: unknown[]; dropped: unknown[] } | null
}

interface RawRevision { id: number; seq: number; parent_id: number | null; author: string; note: string | null; created_at: string }
interface RawSketch {
  revision: RawRevision
  is_current: boolean
  can_undo: boolean
  can_redo: boolean
  inputs_changed: boolean
  inputs_restored?: boolean
  limits: SketchLimits
  document: { pages: SketchPage[] }
  redraw?: { reapplied: unknown[]; dropped: unknown[] } | null
}

const toRev = (r: RawRevision): SketchRevision => ({ id: r.id, seq: r.seq, parentId: r.parent_id, author: r.author, note: r.note, createdAt: r.created_at })
const toSketch = (s: RawSketch): WorkingSketch => ({
  revision: toRev(s.revision),
  isCurrent: s.is_current,
  canUndo: s.can_undo,
  canRedo: s.can_redo,
  inputsChanged: s.inputs_changed,
  inputsRestored: !!s.inputs_restored,
  limits: s.limits ?? {},
  pages: s.document?.pages ?? [],
  redraw: s.redraw ?? null,
})

export interface Selection { stroke_ids?: string[]; word_ids?: string[]; line_ids?: string[]; paragraph_ids?: string[] }

/** The current revision, or one revision by id. `null` when the order has no working sketch yet. */
export async function getSketch(orderId: number, revisionId?: number): Promise<WorkingSketch | null> {
  try {
    return toSketch(await api<RawSketch>(`/orders/${orderId}/sketch${revisionId ? `?revision_id=${revisionId}` : ''}`))
  } catch (e) {
    if (e instanceof ApiError && e.code === 'SKETCH_NOT_GENERATED') return null
    throw e
  }
}

export const generateSketch = async (orderId: number, discardEdits = false): Promise<WorkingSketch> =>
  toSketch(await api<RawSketch>(`/orders/${orderId}/sketch/generate`, { method: 'POST', body: discardEdits ? { discard_edits: true } : {} }))

export const editSketch = async (orderId: number, body: { base_revision_id: number; op: SketchOp; params: Record<string, unknown>; note?: string } & Selection): Promise<WorkingSketch> =>
  toSketch(await api<RawSketch>(`/orders/${orderId}/sketch/edit`, { method: 'POST', body }))

const move = async (orderId: number, dir: 'undo' | 'redo', discardInputChanges = false): Promise<WorkingSketch> =>
  toSketch(await api<RawSketch>(`/orders/${orderId}/sketch/${dir}`, { method: 'POST', body: discardInputChanges ? { discard_input_changes: true } : {} }))
export const undoSketch = (orderId: number, discard = false) => move(orderId, 'undo', discard)
export const redoSketch = (orderId: number, discard = false) => move(orderId, 'redo', discard)

export const listRevisions = async (orderId: number): Promise<SketchRevision[]> =>
  (await api<RawRevision[]>(`/orders/${orderId}/sketch/revisions`)).map(toRev)

/** JPEG of one page of a revision, in the order's ink and paper, as an object URL (the endpoint needs the Bearer header). */
export async function sketchPreviewUrl(orderId: number, revisionId: number, page = 1): Promise<string> {
  const { blob } = await apiFile(`/orders/${orderId}/sketch/preview?page=${page}&revision_id=${revisionId}`)
  return URL.createObjectURL(blob)
}

// ---------- the applied revision ----------

const appliedKey = (orderId: number) => `aivhrs-sketch-applied-${orderId}`

export function getApplied(orderId: number): number | null {
  try {
    const v = Number(localStorage.getItem(appliedKey(orderId)))
    return Number.isFinite(v) && v > 0 ? v : null
  } catch {
    return null
  }
}

export function setApplied(orderId: number, revisionId: number | null) {
  try {
    if (revisionId) localStorage.setItem(appliedKey(orderId), String(revisionId))
    else localStorage.removeItem(appliedKey(orderId))
  } catch {
    // Storage blocked: the applied revision falls back to the backend's current one.
  }
}

/**
 * The undo / redo steps that move the cursor from `fromId` to `toId`, or `null` when `toId` cannot be reached that way.
 * Undo goes to the parent; redo goes to the newest child, so a revision is reachable when it is an ancestor of the
 * cursor, or sits on the newest-child chain below one.
 */
export function pathTo(revs: SketchRevision[], fromId: number, toId: number): { undo: number; redo: number } | null {
  const byId = new Map(revs.map((r) => [r.id, r]))
  if (!byId.has(fromId) || !byId.has(toId)) return null
  const up = (id: number) => {
    const chain: number[] = []
    for (let r = byId.get(id); r; r = r.parentId ? byId.get(r.parentId) : undefined) chain.push(r.id)
    return chain
  }
  const targetLine = up(toId)
  const fromLine = up(fromId)
  const meet = fromLine.findIndex((id) => targetLine.includes(id))
  if (meet < 0) return null
  const lca = fromLine[meet]
  const down = targetLine.slice(0, targetLine.indexOf(lca)).reverse()
  let at = lca
  for (const id of down) {
    const newest = revs.filter((r) => r.parentId === at).sort((a, b) => b.seq - a.seq)[0]
    if (newest?.id !== id) return null
    at = id
  }
  return { undo: meet, redo: down.length }
}

/** Moves the backend cursor to `revisionId`. Throws `ApiError('UNREACHABLE')` when undo / redo cannot get there. */
export async function moveTo(orderId: number, revisionId: number, discardInputChanges = false): Promise<WorkingSketch | null> {
  const cur = await getSketch(orderId)
  if (!cur) return null
  if (cur.revision.id === revisionId) return cur
  const path = pathTo(await listRevisions(orderId), cur.revision.id, revisionId)
  if (!path) throw new ApiError(409, 'UNREACHABLE', 'This version can no longer be applied.')
  let last = cur
  for (let i = 0; i < path.undo; i++) last = await undoSketch(orderId, discardInputChanges)
  for (let i = 0; i < path.redo; i++) last = await redoSketch(orderId, discardInputChanges)
  return last
}

/** Before submitting: the workshop takes the backend's current revision, so put the cursor on the applied one. */
export async function syncAppliedForSubmit(orderId: number): Promise<void> {
  const applied = getApplied(orderId)
  if (!applied) return
  try {
    await moveTo(orderId, applied)
  } catch (e) {
    if (e instanceof ApiError && (e.code === 'UNREACHABLE' || e.code === 'REVISION_NOT_FOUND')) {
      setApplied(orderId, null)
      return
    }
    throw e
  }
}
