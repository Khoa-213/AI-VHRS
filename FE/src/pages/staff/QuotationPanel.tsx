import { useState } from 'react'
import type { Job } from '../../services/async'
import { useAsync } from '../../hooks/useAsync'
import { useLocale, useT } from '../../i18n'
import { getInks, getPapers, getPens, orderErrorKey, errText } from '../../services/orders'
import {
  COMPLEXITIES, adjustQuotation, approveAdjustment, cancelQuotation, clearAdjustment, createQuotation, listQuotations, quotationPdf,
  rejectAdjustment, sendQuotation, type Complexity, type MaterialOption, type WorkOrder, type WorkQuotation,
} from '../../services/workshop'
import { useUser } from '../../store/store'
import { fmt } from '../../utils/format'
import { isManagerRole } from './RequireStaff'

const LIVE = ['DRAFT', 'PENDING_APPROVAL', 'SENT']

/** Quotation of an order. Writable while the order is ACCEPTED; afterwards it is only shown. */
export default function QuotationPanel({ order, readOnly = false, onChanged }: { order: WorkOrder; readOnly?: boolean; onChanged: () => void }) {
  const t = useT()
  const locale = useLocale()
  const user = useUser()
  const manager = isManagerRole(user?.apiRole)
  const list = useAsync(() => listQuotations(order.id), [order.id, order.status])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [complexity, setComplexity] = useState<Complexity | ''>(order.complexity ?? '')
  const [options, setOptions] = useState<MaterialOption[]>([])
  const [eta, setEta] = useState('')
  const [chars, setChars] = useState('')
  const [total, setTotal] = useState('')
  const [reason, setReason] = useState('')

  const quotes = [...(list.data ?? [])].sort((a, b) => b.version - a.version)
  const live = quotes.find((q) => LIVE.includes(q.status))
  const shown: WorkQuotation | undefined = live ?? quotes[0]
  const canCreate = !readOnly && order.status === 'ACCEPTED' && !live && order.finalSketchVersion !== null
  const suggest = order.workshopSuggest

  const run = async (job: Job) => {
    if (busy) return
    setBusy(true)
    setErr('')
    try {
      await job()
      await list.reload()
      onChanged()
    } catch (e) {
      setErr(orderErrorKey(e))
    } finally {
      setBusy(false)
    }
  }

  const day = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString(locale, { day: 'numeric', month: 'short', year: 'numeric' }) : '–')
  const openPdf = async (id: number) => {
    try {
      window.open(await quotationPdf(id), '_blank', 'noopener')
    } catch (e) {
      setErr(orderErrorKey(e))
    }
  }

  return (
    <section className="wk-block" aria-label={t('wk.quotation')}>
      <h3>{t('wk.quotation')}</h3>
      {err && <p className="lg-error" role="alert">{errText(t, err)}</p>}
      {list.loading && !list.data && <p className="sd-sub" role="status">{t('co.loading')}</p>}

      {!readOnly && order.status === 'ACCEPTED' && order.finalSketchVersion === null && !live && <p className="sd-sub">{t('wk.needFinalSketch')}</p>}

      {canCreate && (
        <div className="vh-stack" style={{ gap: 12 }}>
          <div className="wk-form">
            <label className="vh-label">
              {t('wk.complexity')}
              <select className="vh-select" value={complexity} onChange={(e) => setComplexity(e.target.value as Complexity | '')}>
                <option value="">{t('wk.complexity.auto')}</option>
                {COMPLEXITIES.map((c) => <option key={c} value={c}>{t(`cx.${c}`)}</option>)}
              </select>
            </label>
            <label className="vh-label">
              {t('ov.eta')}
              <input className="vh-input" type="date" value={eta} onChange={(e) => setEta(e.target.value)} />
            </label>
            <label className="vh-label">
              {t('wk.charsOverride')}
              <input className="vh-input" inputMode="numeric" value={chars} placeholder={String(order.charCount ?? 0)} onChange={(e) => setChars(e.target.value.replace(/\D/g, '').slice(0, 6))} />
            </label>
          </div>
          {suggest && (
            <div className="vh-stack" style={{ gap: 8 }}>
              <span className="vh-label">{t('wk.optionsTitle')}</span>
              <p className="sd-sub">{t('wk.optionsHint')}</p>
              {options.map((o, i) => (
                <OptionRow key={i} value={o} onChange={(v) => setOptions(options.map((x, j) => (j === i ? v : x)))} onRemove={() => setOptions(options.filter((_, j) => j !== i))} />
              ))}
              {options.length < 3 && (
                <button className="vh-btn vh-btn--ghost vh-btn--sm wk-self" onClick={() => setOptions([...options, { paper_type_id: 0, pen_type_id: 0, ink_color_id: 0 }])}>{t('wk.addOption')}</button>
              )}
            </div>
          )}
          <button
            className="vh-btn vh-btn--primary vh-btn--md wk-self"
            disabled={busy || (suggest && (!options.length || options.some((o) => !o.paper_type_id || !o.pen_type_id || !o.ink_color_id)))}
            onClick={() => void run(() => createQuotation(order.id, {
              ...(complexity ? { complexity } : {}),
              ...(chars ? { char_count: Number(chars) } : {}),
              ...(suggest ? { options } : {}),
              ...(eta ? { eta: new Date(`${eta}T17:00:00+07:00`).toISOString() } : {}),
            }))}
          >
            {t(busy ? 'wk.creating' : 'wk.createQuote')}
          </button>
        </div>
      )}

      {shown && (
        <div className="vh-stack" style={{ gap: 12 }}>
          <dl className="wk-rows">
            <div><dt>{t('ov.quote', { v: shown.version })}</dt><dd><span className="wk-status">{t(`qs.${shown.status}`)}</span></dd></div>
            <div><dt>{t('wk.complexity')}</dt><dd>{t(`cx.${shown.complexity}`)}</dd></div>
            <div><dt>{t('wk.chars')}</dt><dd>{shown.charCount}</dd></div>
            <div><dt>{t('wk.computed')}</dt><dd className="vh-mono">{fmt(shown.computedTotal)}</dd></div>
            {shown.adjustedTotal !== null && (
              <div>
                <dt>{t('wk.adjusted')} · {t(`adj.${shown.adjustment}`)}</dt>
                <dd className="vh-mono">{fmt(shown.adjustedTotal)}{shown.adjustmentPct !== null ? ` (${shown.adjustmentPct > 0 ? '+' : ''}${shown.adjustmentPct}%)` : ''}</dd>
              </div>
            )}
            <div><dt>{t('or.total')}</dt><dd className="vh-mono"><b>{fmt(shown.finalTotal)}</b></dd></div>
            <div><dt>{t('co.minDeposit')}</dt><dd>{shown.minDepositPct}%</dd></div>
            <div><dt>{t('ov.eta')}</dt><dd>{day(shown.eta)}</dd></div>
            {shown.validUntil && <div><dt>{t('ov.validUntil')}</dt><dd>{day(shown.validUntil)}</dd></div>}
          </dl>

          {shown.options.length > 1 && (
            <ul className="wk-options">
              {shown.options.map((o) => <li key={o.option}>{t('ov.optionN', { n: o.option })}: {o.paper} · {o.pen} · {o.ink} · <span className="vh-mono">{fmt(o.total)}</span></li>)}
            </ul>
          )}

          <details className="wk-lines">
            <summary>{t('wk.lines')}</summary>
            <dl className="wk-rows">
              {shown.lines.map((l, i) => (
                <div key={i}><dt>{shown.options.length > 1 ? `${l.option}. ` : ''}{l.item}{l.calc ? ` (${l.calc})` : ''}</dt><dd className="vh-mono">{fmt(l.amount)}</dd></div>
              ))}
            </dl>
          </details>

          {shown.adjustmentReason && <p className="sd-sub">{t('wk.adjustReason')}: {shown.adjustmentReason}</p>}
          {shown.hasPdf && <button className="vh-link wk-self" onClick={() => void openPdf(shown.id)}>{t('ov.pdf')}</button>}

          {!readOnly && live && live.id === shown.id && live.status !== 'SENT' && (
            <>
              {shown.options.length <= 1 && (
                <div className="wk-form">
                  <label className="vh-label">
                    {t('wk.adjustTo')}
                    <input className="vh-input" inputMode="numeric" value={total} placeholder={String(Math.round(shown.computedTotal))} onChange={(e) => setTotal(e.target.value.replace(/\D/g, ''))} />
                  </label>
                  <label className="vh-label wk-grow">
                    {t('wk.adjustReason')}
                    <input className="vh-input" value={reason} maxLength={500} onChange={(e) => setReason(e.target.value)} />
                  </label>
                  <button className="vh-btn vh-btn--ghost vh-btn--sm" disabled={busy || !total || !reason.trim()} onClick={() => void run(() => adjustQuotation(shown.id, Number(total), reason.trim()))}>{t('wk.applyAdjust')}</button>
                  {shown.adjustedTotal !== null && <button className="vh-btn vh-btn--ghost vh-btn--sm" disabled={busy} onClick={() => void run(() => clearAdjustment(shown.id))}>{t('wk.clearAdjust')}</button>}
                </div>
              )}
              {shown.adjustment === 'PENDING_MANAGER' && (
                <div className="vh-callout vh-callout--amber">
                  <b>{t('wk.pendingManager')}</b>
                  <span>{t('wk.pendingManagerBody')}</span>
                  {manager && (
                    <div className="wk-actions">
                      <button className="vh-btn vh-btn--primary vh-btn--sm" disabled={busy} onClick={() => void run(() => approveAdjustment(shown.id))}>{t('wk.approveAdjust')}</button>
                      <button className="vh-btn vh-btn--ghost vh-btn--sm" disabled={busy || !reason.trim()} onClick={() => void run(() => rejectAdjustment(shown.id, reason.trim()))}>{t('wk.rejectAdjust')}</button>
                    </div>
                  )}
                </div>
              )}
              <div className="wk-actions">
                <button className="vh-btn vh-btn--primary vh-btn--md" disabled={busy || shown.adjustment === 'PENDING_MANAGER' || shown.status === 'PENDING_APPROVAL'} onClick={() => void run(() => sendQuotation(shown.id))}>{t('wk.sendQuote')}</button>
                <button className="vh-btn vh-btn--ghost vh-btn--md" disabled={busy} onClick={() => void run(() => cancelQuotation(shown.id))}>{t('wk.cancelQuote')}</button>
              </div>
            </>
          )}
          {!readOnly && live?.status === 'SENT' && (
            <div className="wk-actions">
              <span className="sd-sub">{t('wk.sentWaiting')}</span>
              <button className="vh-btn vh-btn--ghost vh-btn--sm" disabled={busy} onClick={() => void run(() => cancelQuotation(shown.id))}>{t('wk.cancelQuote')}</button>
            </div>
          )}
        </div>
      )}
      {list.data && !shown && readOnly && <p className="sd-sub">{t('wk.noQuote')}</p>}
    </section>
  )
}

/** One material option of a quotation: paper, then a pen that works with it, then an ink for that pen. */
function OptionRow({ value, onChange, onRemove }: { value: MaterialOption; onChange: (v: MaterialOption) => void; onRemove: () => void }) {
  const t = useT()
  const papers = useAsync(getPapers, [])
  const pens = useAsync(() => (value.paper_type_id ? getPens(value.paper_type_id) : Promise.resolve([])), [value.paper_type_id])
  const inks = useAsync(() => (value.pen_type_id ? getInks(value.pen_type_id) : Promise.resolve([])), [value.pen_type_id])
  return (
    <div className="wk-form wk-option">
      <select className="vh-select" aria-label={t('co.paper')} value={value.paper_type_id || ''} onChange={(e) => onChange({ paper_type_id: Number(e.target.value), pen_type_id: 0, ink_color_id: 0 })}>
        <option value="">{t('co.paper')}</option>
        {(papers.data ?? []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select>
      <select className="vh-select" aria-label={t('co.pen')} value={value.pen_type_id || ''} disabled={!value.paper_type_id} onChange={(e) => onChange({ ...value, pen_type_id: Number(e.target.value), ink_color_id: 0 })}>
        <option value="">{t('co.pen')}</option>
        {(pens.data ?? []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select>
      <select className="vh-select" aria-label={t('co.ink')} value={value.ink_color_id || ''} disabled={!value.pen_type_id} onChange={(e) => onChange({ ...value, ink_color_id: Number(e.target.value) })}>
        <option value="">{t('co.ink')}</option>
        {(inks.data ?? []).map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
      </select>
      <button className="vh-btn vh-btn--ghost vh-btn--sm" onClick={onRemove}>{t('co.remove')}</button>
    </div>
  )
}
