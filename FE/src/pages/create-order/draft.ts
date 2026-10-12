import type { InputMode } from '../../types'

/**
 * The create-order form and the full-screen canvas are separate pages, so the
 * form state that must survive the round trip lives in sessionStorage.
 */
export interface CreateDraft {
  type: string | null
  text: string
  fontStyle: string
  step: number
  mode: InputMode
  drawUrl: string | null
  strokes: number
  sizeId: string
  landscape: boolean
}

export const DRAW_PATH = '/create-order/draw'

export const CANVAS_SIZES = [
  { id: 'a4', label: 'A4', w: 210, h: 297 },
  { id: 'a5', label: 'A5', w: 148, h: 210 },
  { id: 'a6', label: 'A6', w: 105, h: 148 },
  { id: 'a7', label: 'A7', w: 74, h: 105 },
] as const

const KEY = 'vhrs.create-draft'

export const EMPTY_DRAFT: CreateDraft = {
  type: null, text: '', fontStyle: 'script', step: 0, mode: 'text',
  drawUrl: null, strokes: 0, sizeId: 'a4', landscape: false,
}

export function loadDraft(): CreateDraft {
  try {
    const raw = sessionStorage.getItem(KEY)
    if (raw) return { ...EMPTY_DRAFT, ...JSON.parse(raw) }
  } catch {
    /* storage blocked or corrupt: start clean */
  }
  return { ...EMPTY_DRAFT }
}

export function saveDraft(patch: Partial<CreateDraft>) {
  const next = { ...loadDraft(), ...patch }
  try {
    sessionStorage.setItem(KEY, JSON.stringify(next))
  } catch {
    // Quota hit (large canvas): keep everything except the bitmap.
    try {
      sessionStorage.setItem(KEY, JSON.stringify({ ...next, drawUrl: null }))
    } catch {
      /* give up silently */
    }
  }
}

export function clearDraft() {
  try {
    sessionStorage.removeItem(KEY)
  } catch {
    /* ignore */
  }
}
