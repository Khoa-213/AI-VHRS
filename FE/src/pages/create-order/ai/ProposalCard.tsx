import { useT, useTn } from '../../../i18n'
import type { AiChange, AiProposal } from '../../../services/orderAi'
import { fmt } from '../../../utils/format'

const FIELDS = new Set([
  'text', 'template_id', 'handwriting_style_id', 'font_size_mm', 'alignment', 'layout', 'paper_type_id', 'pen_type_id', 'ink_color_id',
  'workshop_suggest_materials', 'quantity', 'physical_watermark', 'restoration_mode', 'customer_note', 'sketch',
])
const ALIGNMENTS = new Set(['LEFT', 'CENTER', 'RIGHT', 'JUSTIFY'])
const LONG = 90

/**
 * What one answer of the assistant changed on the order, as a compact line that opens to the list of changes. The order is
 * changed as soon as the assistant answers (CreateOrder applies the proposal), so there is nothing to decide here: the new
 * sketch is in the sketch box beside the form, and Undo in the chat header goes back.
 */
export default function ProposalCard({ proposal }: { proposal: AiProposal }) {
  const t = useT()
  const tn = useTn()

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
    <details className="oa-prop" data-status={proposal.status}>
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
    </details>
  )
}
