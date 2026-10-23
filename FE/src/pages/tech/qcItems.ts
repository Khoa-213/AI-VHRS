import type { TFn } from '../../i18n'
import type { PhotoKind } from '../../services/technician'

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

/** What a job tells the checklist: names come from the API and are shown as received. */
export interface QcSubject {
  paperName: string | null
  penName: string | null
  inkName: string | null
  quantity: number
}

/** Everything the technician checks before the customer sees the result, grouped by where they look. */
export function qcGroups(j: QcSubject, t: TFn): QcGroup[] {
  const pieces = j.quantity || 1
  return [
    {
      id: 'sheet',
      title: t('qc.sheet'),
      items: [
        { id: 'paper', title: t('qc.paper', { name: j.paperName ?? '-' }), detail: t('qc.paperDetailJob') },
        { id: 'bleed', title: t('qc.bleed'), detail: t('qc.bleedDetail') },
      ],
    },
    {
      id: 'writing',
      title: t('qc.writing'),
      items: [
        { id: 'text', title: t('qc.text'), detail: t('qc.textDetailJob') },
        { id: 'marks', title: t('qc.marks'), detail: t('qc.marksDetail') },
        { id: 'strokes', title: t('qc.strokes'), detail: t('qc.strokesDetail') },
        { id: 'ink', title: t('qc.ink', { name: j.inkName ?? '-' }), detail: t('qc.inkDetail', { pen: j.penName ?? '-' }) },
        { id: 'marksout', title: t('qc.marksOut'), detail: t('qc.marksOutDetail') },
      ],
    },
    {
      id: 'pieces',
      title: t('qc.pieces'),
      items: [
        { id: 'count', title: pieces > 1 ? t('qc.countMany', { n: pieces }) : t('qc.countOne'), detail: t(pieces > 1 ? 'qc.countManyDetail' : 'qc.countOneDetail') },
        { id: 'dry', title: t('qc.dry'), detail: t('qc.dryDetail') },
        { id: 'pack', title: t('qc.pack'), detail: t('qc.packDetail') },
      ],
    },
  ]
}

/** One slot per kind of photo the backend knows. OVERALL and CLOSE_UP are required (BR-21). */
export const PHOTO_SLOTS: { kind: PhotoKind; label: string; hint: string; required: boolean }[] = [
  { kind: 'OVERALL', label: 'Whole sheet', hint: 'Flat, all four corners visible', required: true },
  { kind: 'CLOSE_UP', label: 'Close-up', hint: 'A few words, in focus', required: true },
  { kind: 'OTHER', label: 'Packed', hint: 'Optional, the stack before it ships', required: false },
]

export const QC_FAIL_REASONS = ['Ink smudge', 'Missing strokes', 'Wrong paper', 'Text mismatch', 'Pen skipped', 'Other']
