import { layoutById } from '../../constants/catalog'
import type { Order } from '../../types'

export interface QcItem {
  id: string
  title: string
  detail: string
}

export interface QcGroup {
  id: string
  title: string
  items: QcItem[]
}

/** Everything the technician checks before the customer sees the result, grouped by where they look. */
export function qcGroups(o: Order): QcGroup[] {
  const sp = o.spec
  const pieces = sp.qty || 1
  const layout = layoutById(o.layout).name
  return [
    {
      id: 'sheet',
      title: 'Paper and layout',
      items: [
        { id: 'paper', title: `Paper is ${sp.paper}`, detail: `${sp.type}${sp.land ? ', landscape' : ''}, no creases or tears` },
        { id: 'layout', title: `Layout is ${layout}`, detail: 'Margins even, text sits where the preview showed' },
        { id: 'bleed', title: 'No ink bleeding through', detail: 'Turn the sheet over and look at the back' },
      ],
    },
    {
      id: 'writing',
      title: 'The writing',
      items: [
        { id: 'text', title: 'Text matches the order', detail: 'Read it against the text on the right, word by word' },
        { id: 'marks', title: 'Diacritics and punctuation present', detail: 'Every accent, dot and comma is there' },
        { id: 'strokes', title: 'Strokes are unbroken', detail: 'No skipped segments or gaps inside letters' },
        { id: 'ink', title: `${sp.ink} is even`, detail: `${sp.pen}, same weight and shade across the line` },
        { id: 'marksout', title: 'No smudges or stray marks', detail: 'Check around the edges and under the last line' },
      ],
    },
    {
      id: 'pieces',
      title: 'Pieces and packing',
      items: [
        { id: 'count', title: pieces > 1 ? `All ${pieces} pieces counted` : 'The piece is accounted for', detail: pieces > 1 ? 'Sample the first, middle and last piece' : 'One sheet, nothing missing' },
        { id: 'dry', title: 'Ink is dry', detail: 'Touch a margin, never the writing' },
        { id: 'pack', title: 'Packed flat with a protective sheet', detail: 'Ready for courier pickup' },
      ],
    },
  ]
}

export const PHOTO_SLOTS = [
  { id: 'sheet', label: 'Whole sheet', hint: 'Flat, all four corners visible', required: true },
  { id: 'close', label: 'Close-up', hint: 'A few words, in focus', required: true },
  { id: 'packed', label: 'Packed', hint: 'Optional, the stack before it ships', required: false },
] as const

export const QC_FAIL_REASONS = ['Ink smudge', 'Missing strokes', 'Wrong paper', 'Text mismatch', 'Pen skipped', 'Other']
