/** Paper sizes the full-screen canvas can produce (mm). */
export const CANVAS_SIZES = [
  { id: 'a4', label: 'A4', w: 210, h: 297 },
  { id: 'a5', label: 'A5', w: 148, h: 210 },
  { id: 'a6', label: 'A6', w: 105, h: 148 },
  { id: 'a7', label: 'A7', w: 74, h: 105 },
] as const

export const DRAW_PATH = '/create-order/draw'
export const drawPathFor = (draftId: string) => `${DRAW_PATH}/${encodeURIComponent(draftId)}`
export const draftPathFor = (draftId: string) => `/create-order/draft/${encodeURIComponent(draftId)}`
