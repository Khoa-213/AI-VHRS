import type { TFn } from '../../i18n'
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
export function qcGroups(o: Order, t: TFn, tn: (s: string) => string): QcGroup[] {
  const sp = o.spec
  const pieces = sp.qty || 1
  const layout = tn(layoutById(o.layout).name)
  return [
    {
      id: 'sheet',
      title: t('qc.sheet'),
      items: [
        { id: 'paper', title: t('qc.paper', { name: tn(sp.paper) }), detail: t('qc.paperDetail', { type: tn(sp.type), land: sp.land ? t('qc.landscape') : '' }) },
        { id: 'layout', title: t('qc.layout', { name: layout }), detail: t('qc.layoutDetail') },
        { id: 'bleed', title: t('qc.bleed'), detail: t('qc.bleedDetail') },
      ],
    },
    {
      id: 'writing',
      title: t('qc.writing'),
      items: [
        { id: 'text', title: t('qc.text'), detail: t('qc.textDetail') },
        { id: 'marks', title: t('qc.marks'), detail: t('qc.marksDetail') },
        { id: 'strokes', title: t('qc.strokes'), detail: t('qc.strokesDetail') },
        { id: 'ink', title: t('qc.ink', { name: tn(sp.ink) }), detail: t('qc.inkDetail', { pen: tn(sp.pen) }) },
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

export const PHOTO_SLOTS = [
  { id: 'sheet', label: 'Whole sheet', hint: 'Flat, all four corners visible', required: true },
  { id: 'close', label: 'Close-up', hint: 'A few words, in focus', required: true },
  { id: 'packed', label: 'Packed', hint: 'Optional, the stack before it ships', required: false },
] as const

export const QC_FAIL_REASONS = ['Ink smudge', 'Missing strokes', 'Wrong paper', 'Text mismatch', 'Pen skipped', 'Other']
