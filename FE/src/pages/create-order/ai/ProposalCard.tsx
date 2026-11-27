import { useT, useTn } from '../../../i18n'
import type { AiChange, AiProposal } from '../../../services/orderAi'
import { fmt } from '../../../utils/format'

const FIELDS = new Set([
  'text', 'template_id', 'handwriting_style_id', 'font_size_mm', 'alignment', 'layout', 'paper_type_id', 'pen_type_id', 'ink_color_id',
  'workshop_suggest_materials', 'quantity', 'physical_watermark', 'restoration_mode', 'customer_note', 'sketch',
])
const ALIGNMENTS = new Set(['LEFT', 'CENTER', 'RIGHT', 'JUSTIFY'])
const LONG = 90

export type ProposalAction = 'apply' | 'skip' | 'revert'

/**
 * What one answer of the assistant changes on the order, as a compact line that opens to the list of changes. An answer that
 * only changes what Undo brings back (words, layout, materials, sketch) is on the order as soon as it arrives (OrderAssistant
 * applies it); one that changes more, or draws over the customer's own edits, waits here with Apply and Skip. An applied
 * answer can be taken back whole while the order has not changed since.
 */
export default function ProposalCard({ proposal, busy = false, onAction }: {
  proposal: AiProposal
  busy?: boolean
  onAction?: (action: ProposalAction, proposal: AiProposal) => void
}) {
  const t = useT()
  const tn = useTn()
  const waiting = proposal.status === 'PENDING' && proposal.applicable
  const reason = (r: string) => (r === 'DISCARDS_MANUAL_EDITS' ? t('oa.reason.DISCARDS_MANUAL_EDITS') : t(FIELDS.has(r) ? `oa.field.${r}` : 'oa.field.other'))

  const cut = (s: string) => (s.length > LONG ? `${s.slice(0, LONG)}…` : s)
  const show = (c: AiChange, v: unknown): string => {
    if (v === null || v === undefined || v === '') return t('oa.empty')
    if (c.field === 'layout') return t('oa.layout')
    if (typeof v === 'boolean') return t(v ? 'oa.yes' : 'oa.no')
    if (typeof v === 'object') {
      const name = (v as { name?: unknown }).name
      return typeof name === 'string' ? tn(name) : t('oa.layout')
    }
    if (c.field === 'font_size_mm') return `${String(v)} mm`
    if (c.field === 'alignment' && ALIGNMENTS.has(String(v))) return t(`co.align.${String(v)}`)
    return cut(String(v))
  }
  const label = (c: AiChange) => t(FIELDS.has(c.field) ? `oa.field.${c.field}` : 'oa.field.other')

  if (!proposal.changes.length) return null
  const price = proposal.estimate
    ? (proposal.estimate.priceMin === proposal.estimate.priceMax
      ? fmt(proposal.estimate.priceMax)
      : `${fmt(proposal.estimate.priceMin)} – ${fmt(proposal.estimate.priceMax)}`)
    : null
  const state = proposal.status === 'APPLIED' ? 'oa.applied' : proposal.status === 'REJECTED' ? 'oa.skipped' : 'oa.notApplied'

  return (
    <details className="oa-prop" data-status={proposal.status} open={waiting && proposal.needsConfirmation ? true : undefined}>
      <summary>
        <span className={`oa-dot${proposal.status === 'APPLIED' ? ' ok' : ''}`} aria-hidden="true" />
        <b>{t(state)}</b>
        <span className="oa-prop-n">{t('oa.changesN', { n: proposal.changes.length })}</span>
        {price && <span className="oa-prop-price vh-mono">{price}</span>}
      </summary>
      <dl className="oa-changes">
        {proposal.changes.map((c) => (
          <div key={c.field} className="oa-change">
            <dt>{label(c)}</dt>
            <dd>
              {c.field === 'sketch'
                ? <span>{c.before === null || c.before === undefined ? t('oa.sketchFirst') : t('oa.sketchNew')}</span>
                : <><span className="oa-before">{show(c, c.before)}</span><span aria-hidden="true" className="oa-arrow">→</span><span className="oa-after">{show(c, c.after)}</span></>}
            </dd>
          </div>
        ))}
      </dl>
      {proposal.preview?.sketchOutdated && <p className="oa-blocked" role="status">{t('oa.proposalOutdated')}</p>}
      {waiting && proposal.needsConfirmation && (
        <div className="oa-confirm" role="status">
          <p>{t('oa.confirmWhy')}</p>
          <ul>{proposal.confirmReasons.map((r) => <li key={r}>{reason(r)}</li>)}</ul>
        </div>
      )}
      {onAction && waiting && (
        <div className="oa-prop-actions">
          <button type="button" className="oa-btn" disabled={busy} onClick={() => onAction('apply', proposal)}>{t('oa.apply')}</button>
          <button type="button" className="oa-btn oa-btn--line" disabled={busy} onClick={() => onAction('skip', proposal)}>{t('oa.skip')}</button>
        </div>
      )}
      {onAction && proposal.status === 'APPLIED' && proposal.revertible && (
        <div className="oa-prop-actions">
          <button type="button" className="oa-btn oa-btn--line" disabled={busy} title={t('oa.revertHint')} onClick={() => onAction('revert', proposal)}>{t('oa.revert')}</button>
        </div>
      )}
    </details>
  )
}
