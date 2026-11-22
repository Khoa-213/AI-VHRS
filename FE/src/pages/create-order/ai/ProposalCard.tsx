import { useState } from 'react'
import { useT, useTn } from '../../../i18n'
import { proposalPreviewUrl, type AiChange, type AiProposal } from '../../../services/orderAi'
import { fmt } from '../../../utils/format'
import { BlobImage } from './SketchView'

const FIELDS = new Set([
  'text', 'template_id', 'handwriting_style_id', 'font_size_mm', 'alignment', 'layout', 'paper_type_id', 'pen_type_id', 'ink_color_id',
  'workshop_suggest_materials', 'quantity', 'physical_watermark', 'restoration_mode', 'customer_note', 'sketch',
])
const ALIGNMENTS = new Set(['LEFT', 'CENTER', 'RIGHT', 'JUSTIFY'])
const LONG = 90

/** One proposal of the assistant: what it changes, the new price, the new sketch, and the two decisions. */
export default function ProposalCard({ proposal, busy, locked, showPicture, continued, onApply, onReject }: {
  proposal: AiProposal
  /** The assistant or another request is working: nothing can be decided now. */
  busy: boolean
  /** Apply is held back for another reason (the quota, the order is being saved). */
  locked?: boolean
  showPicture: boolean
  /** This proposal continued an earlier pending one, so it contains that one too. */
  continued: boolean
  onApply: () => void
  onReject: () => void
}) {
  const t = useT()
  const tn = useTn()
  const open = proposal.status === 'PENDING'
  const [page, setPage] = useState(1)
  const pv = proposal.preview
  const at = pv ? Math.min(page, pv.pages) : 1

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

  const price = proposal.estimate
    ? (proposal.estimate.priceMin === proposal.estimate.priceMax
      ? fmt(proposal.estimate.priceMax)
      : `${fmt(proposal.estimate.priceMin)} – ${fmt(proposal.estimate.priceMax)}`)
    : null

  const badge = proposal.status === 'APPLIED' ? 'oa.applied' : proposal.status === 'REJECTED' ? 'oa.skipped' : null

  return (
    <div className={`oa-card oa-prop${open ? ' on' : ''}`} data-status={proposal.status}>
      <div className="oa-card-head">
        <b>{t('oa.proposal')}</b>
        {badge && <span className={`oa-badge${proposal.status === 'REJECTED' ? ' oa-badge--off' : ''}`}>{t(badge)}</span>}
      </div>

      {open && continued && <span className="oa-fine">{t('oa.continued')}</span>}

      {showPicture && pv && (
        <>
          <div className="oa-card-pic">
            <BlobImage id={`p${proposal.id}-${pv.revisionId}-${at}`} load={() => proposalPreviewUrl(pv.url, at)} className="oa-card-img" />
          </div>
          {pv.pages > 1 && (
            <div className="oa-pager">
              <button type="button" className="co-btn co-btn--line co-btn--sm" disabled={at <= 1} aria-label={t('oa.prevPage')} onClick={() => setPage(at - 1)}>‹</button>
              <span className="vh-mono">{t('oa.page', { n: at, total: pv.pages })}</span>
              <button type="button" className="co-btn co-btn--line co-btn--sm" disabled={at >= pv.pages} aria-label={t('oa.nextPage')} onClick={() => setPage(at + 1)}>›</button>
            </div>
          )}
          {pv.sketchOutdated && <p className="oa-blocked" role="status">{t('oa.proposalOutdated')}</p>}
        </>
      )}

      {proposal.changes.length > 0 && (
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
      )}

      {price && <p className="oa-price">{t('oa.price', { price })}</p>}

      {open && !proposal.applicable && (
        <p className="oa-blocked" role="status">{t(`oa.blocked.${proposal.blockedReason ?? 'ORDER_CHANGED'}`)}</p>
      )}

      {open && (
        <div className="oa-actions">
          <button type="button" className="co-btn co-btn--solid co-btn--sm" disabled={busy || locked || !proposal.applicable} onClick={onApply}>
            {t('oa.apply')}
          </button>
          <button type="button" className="co-btn co-btn--line co-btn--sm" disabled={busy} onClick={onReject}>{t('oa.skip')}</button>
        </div>
      )}
    </div>
  )
}
