import { Check, Plus } from '@phosphor-icons/react'
import { useState } from 'react'
import { useAsync } from '../../hooks/useAsync'
import { useT } from '../../i18n'
import { errText, orderErrorKey } from '../../services/orders'
import { materialSuggestions, type MaterialCombo, type MaterialOption } from '../../services/workshop'
import './staff-extras.css'

const FIRST = 6
const same = (a: MaterialOption, b: MaterialOption) =>
  a.paper_type_id === b.paper_type_id && a.pen_type_id === b.pen_type_id && a.ink_color_id === b.ink_color_id

/**
 * Paper, pen and ink combinations the server still allows for the order (`GET /workshop/orders/{id}/material-suggestions`):
 * the customer's own picks are kept and the compatibility rules applied. Picking one fills a quotation option; the
 * quotation is created as before.
 */
export default function MaterialSuggestions({ orderId, options, max, onPick }: {
  orderId: number; options: MaterialOption[]; max: number; onPick: (o: MaterialOption) => void
}) {
  const t = useT()
  const q = useAsync(() => materialSuggestions(orderId), [orderId])
  const [all, setAll] = useState(false)
  const s = q.data
  const combos = s?.combos ?? []
  const shown = all ? combos : combos.slice(0, FIRST)
  const kept = s ? [s.fixed.paper, s.fixed.pen, s.fixed.ink].filter(Boolean).join(' · ') : ''
  const more = combos.length > FIRST
  const capped = !!s && s.total > combos.length
  const full = options.length >= max && options.every((o) => o.paper_type_id && o.pen_type_id && o.ink_color_id)

  const pick = (c: MaterialCombo) => onPick({ paper_type_id: c.paper_type_id, pen_type_id: c.pen_type_id, ink_color_id: c.ink_color_id })

  return (
    <div className="stx-suggest" aria-labelledby={`stm-h-${orderId}`}>
      <div className="stx-head">
        <span className="vh-label" id={`stm-h-${orderId}`}>{t('stm.title')}</span>
        {s && <span className="sd-sub">{t('stm.count', { n: s.total })}</span>}
      </div>
      {kept && <p className="sd-sub">{t('stm.kept', { names: kept })}</p>}
      {q.loading && !s && <p className="sd-sub" role="status">{t('co.loading')}</p>}
      {q.error != null && (
        <div className="stx-error" role="alert">
          <p className="lg-error">{errText(t, orderErrorKey(q.error))}</p>
          <button type="button" className="vh-btn vh-btn--ghost vh-btn--sm" onClick={() => void q.reload()}>{t('td.api.reload')}</button>
        </div>
      )}
      {s && !q.error && !combos.length && <p className="sd-sub">{t('stm.empty')}</p>}
      {shown.length > 0 && (
        <ul className="stx-combos">
          {shown.map((c) => {
            const added = options.some((o) => same(o, c))
            return (
              <li key={`${c.paper_type_id}-${c.pen_type_id}-${c.ink_color_id}`}>
                <span className="stx-combo-name">{c.paper}<span aria-hidden> · </span>{c.pen}<span aria-hidden> · </span>{c.ink}</span>
                <button type="button" className="vh-btn vh-btn--ghost vh-btn--sm" disabled={added || full} aria-pressed={added} onClick={() => pick(c)}>
                  {added ? <Check size={15} aria-hidden /> : <Plus size={15} aria-hidden />}
                  {t(added ? 'stm.added' : 'stm.use')}
                </button>
              </li>
            )
          })}
        </ul>
      )}
      {more && (
        <button type="button" className="vh-link wk-self" onClick={() => setAll(!all)}>{t(all ? 'stm.less' : 'stm.more', { n: combos.length })}</button>
      )}
      {capped && <p className="sd-sub">{t('stm.capped', { n: combos.length, total: s.total })}</p>}
      {full && combos.length > 0 && <p className="sd-sub">{t('stm.full', { n: max })}</p>}
    </div>
  )
}
