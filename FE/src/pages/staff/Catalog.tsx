import { useMemo, useState } from 'react'
import type { Job as JobFn } from '../../services/async'
import SkipLink from '../../components/ui/SkipLink'
import ThemeToggle from '../../components/ui/ThemeToggle'
import LanguageToggle from '../../components/ui/LanguageToggle'
import { useAsync } from '../../hooks/useAsync'
import { useLocale, useT } from '../../i18n'
import {
  PAPER_SIZES, PEN_CATEGORIES, SURFACES, TEMPLATE_KINDS, adminCompat, adminInks, adminPapers, adminPens, adminRobots, adminStyles,
  adminTemplates, approveStyle, createInk, createPaper, createPen, createRobot, createTemplate, patchInk, patchPaper, patchPen, patchRobot,
  patchTemplate, priceVersions, rejectStyle, savePrice, setCompat, stockInk, stockPaper, stockPen,
  type AdminRobot, type PenCategory, type PriceList, type StockChange,
} from '../../services/manage'
import { errText, orderErrorKey } from '../../services/orders'
import { fmt } from '../../utils/format'
import StaffRail from './StaffRail'
import './dashboard.css'
import './polish.css'
import './workshop.css'

const TABS = ['papers', 'pens', 'inks', 'compat', 'templates', 'styles', 'robots', 'pricing'] as const
type Tab = (typeof TABS)[number]

/** Runs a change with one busy flag and one error line for the whole tab. */
function useRun(after: () => void) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const run = async (job: JobFn) => {
    if (busy) return false
    setBusy(true)
    setErr('')
    try {
      await job()
      after()
      return true
    } catch (e) {
      setErr(orderErrorKey(e))
      return false
    } finally {
      setBusy(false)
    }
  }
  return { busy, err, run }
}

/** Manager only: the catalog the customer chooses from, its stock, the writing templates, the robots and the price list. */
export default function Catalog() {
  const t = useT()
  const [tab, setTab] = useState<Tab>('papers')
  return (
    <div className="sd">
      <SkipLink />
      <StaffRail active="catalog" />
      <main className="sd-body" id="main">
        <header className="sd-top">
          <div>
            <h1>{t('mg.title')}</h1>
            <p>{t('mg.lede')}</p>
          </div>
          <div className="sd-top-right">
            <ThemeToggle className="vh-icon-btn" />
            <LanguageToggle className="vh-icon-btn" />
          </div>
        </header>
        <div className="wk-page mg">
          <div className="wk-tabs" role="tablist">
            {TABS.map((x) => (
              <button key={x} role="tab" aria-selected={tab === x} className={tab === x ? 'on' : ''} onClick={() => setTab(x)}>{t(`mg.tab.${x}`)}</button>
            ))}
          </div>
          {tab === 'papers' && <Papers />}
          {tab === 'pens' && <Pens />}
          {tab === 'inks' && <Inks />}
          {tab === 'compat' && <Compat />}
          {tab === 'templates' && <Templates />}
          {tab === 'styles' && <Styles />}
          {tab === 'robots' && <Robots />}
          {tab === 'pricing' && <Pricing />}
        </div>
      </main>
    </div>
  )
}

function ErrorLine({ err }: { err: string }) {
  const t = useT()
  return err ? <p className="lg-error" role="alert">{errText(t, err)}</p> : null
}

/** Stock change of one row: add or set a level, with the reason the backend audits. */
function StockForm({ onSend, onCancel, busy }: { onSend: (c: StockChange) => void; onCancel: () => void; busy: boolean }) {
  const t = useT()
  const [mode, setMode] = useState<'ADD' | 'SET'>('ADD')
  const [qty, setQty] = useState('')
  const [reason, setReason] = useState('')
  const n = Number(qty)
  const ok = qty !== '' && Number.isInteger(n) && (mode === 'ADD' || n >= 0) && reason.trim().length > 0
  return (
    <div className="wk-form">
      <label className="vh-label">
        {t('mg.stock.mode')}
        <select className="vh-select" value={mode} onChange={(e) => setMode(e.target.value as 'ADD' | 'SET')}>
          <option value="ADD">{t('mg.stock.add')}</option>
          <option value="SET">{t('mg.stock.set')}</option>
        </select>
      </label>
      <label className="vh-label">
        {t('mg.stock.qty')}
        <input className="vh-input" inputMode="numeric" value={qty} onChange={(e) => setQty(e.target.value.replace(/[^\d-]/g, ''))} />
      </label>
      <label className="vh-label wk-grow">
        {t('mg.stock.reason')}
        <input className="vh-input" value={reason} maxLength={1000} onChange={(e) => setReason(e.target.value)} />
      </label>
      <button className="vh-btn vh-btn--ghost vh-btn--sm" onClick={onCancel}>{t('ov.back')}</button>
      <button className="vh-btn vh-btn--primary vh-btn--sm" disabled={busy || !ok} onClick={() => onSend({ mode, quantity: n, reason: reason.trim() })}>{t('mg.stock.save')}</button>
    </div>
  )
}

const intOnly = (v: string) => v.replace(/\D/g, '').slice(0, 10)
const decOnly = (v: string) => v.replace(/[^\d.]/g, '').slice(0, 8)

// ---------- papers ----------

function Papers() {
  const t = useT()
  const list = useAsync(adminPapers, [])
  const { busy, err, run } = useRun(() => void list.reload())
  const [stockFor, setStockFor] = useState<number | null>(null)
  const [price, setPrice] = useState<Record<number, string>>({})
  const [form, setForm] = useState({ code: '', name: '', gsm: '80', surface: 'PLAIN', size: 'A4', price: '', stock: '0' })
  return (
    <section className="wk-block">
      <ErrorLine err={err} />
      <details className="wk-lines">
        <summary>{t('mg.add')}</summary>
        <div className="wk-form">
          <label className="vh-label">{t('mg.code')}<input className="vh-input" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} /></label>
          <label className="vh-label wk-grow">{t('mg.name')}<input className="vh-input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
          <label className="vh-label">{t('mg.gsm')}<input className="vh-input" inputMode="numeric" value={form.gsm} onChange={(e) => setForm({ ...form, gsm: intOnly(e.target.value) })} /></label>
          <label className="vh-label">{t('mg.surface')}
            <select className="vh-select" value={form.surface} onChange={(e) => setForm({ ...form, surface: e.target.value })}>{SURFACES.map((s) => <option key={s} value={s}>{t(`surface.${s}`)}</option>)}</select>
          </label>
          <label className="vh-label">{t('mg.size')}
            <select className="vh-select" value={form.size} onChange={(e) => setForm({ ...form, size: e.target.value })}>{PAPER_SIZES.map((s) => <option key={s} value={s}>{s}</option>)}</select>
          </label>
          <label className="vh-label">{t('mg.price')}<input className="vh-input" inputMode="numeric" value={form.price} onChange={(e) => setForm({ ...form, price: intOnly(e.target.value) })} /></label>
          <label className="vh-label">{t('mg.stock')}<input className="vh-input" inputMode="numeric" value={form.stock} onChange={(e) => setForm({ ...form, stock: intOnly(e.target.value) })} /></label>
          <button
            className="vh-btn vh-btn--primary vh-btn--md"
            disabled={busy || !form.code || !form.name || !form.price}
            onClick={() => void run(() => createPaper({ code: form.code, name: form.name, gsm: Number(form.gsm), surface: form.surface, size: form.size, unit_price: Number(form.price), stock_qty: Number(form.stock) || 0 }))}
          >{t('mg.create')}</button>
        </div>
      </details>
      <ul className="mg-rows">
        {(list.data ?? []).map((p) => (
          <li key={p.id} className={p.active ? '' : 'off'}>
            <div className="mg-row">
              <span className="mg-name"><b>{p.name}</b><small>{p.code} · {p.size} · {t(`surface.${p.surface}`)} · {p.gsm} gsm</small></span>
              <label className="mg-inline">{t('mg.price')}
                <input className="vh-input" inputMode="numeric" value={price[p.id] ?? String(p.unitPrice)} onChange={(e) => setPrice({ ...price, [p.id]: intOnly(e.target.value) })} />
              </label>
              <button className="vh-btn vh-btn--ghost vh-btn--sm" disabled={busy || price[p.id] === undefined || Number(price[p.id]) === p.unitPrice} onClick={() => void run(() => patchPaper(p.id, { unit_price: Number(price[p.id]) }))}>{t('mg.save')}</button>
              <span className="vh-mono mg-stock">{t('mg.inStock', { n: p.stock })}</span>
              <button className="vh-link" onClick={() => setStockFor(stockFor === p.id ? null : p.id)}>{t('mg.stock')}</button>
              <label className="wk-check"><input type="checkbox" checked={p.active} disabled={busy} onChange={(e) => void run(() => patchPaper(p.id, { is_active: e.target.checked }))} /> {t('mg.active')}</label>
            </div>
            {stockFor === p.id && <StockForm busy={busy} onCancel={() => setStockFor(null)} onSend={(c) => void run(() => stockPaper(p.id, c)).then((ok) => ok && setStockFor(null))} />}
          </li>
        ))}
      </ul>
    </section>
  )
}

// ---------- pens ----------

function Pens() {
  const t = useT()
  const list = useAsync(adminPens, [])
  const { busy, err, run } = useRun(() => void list.reload())
  const [stockFor, setStockFor] = useState<number | null>(null)
  const [sur, setSur] = useState<Record<number, string>>({})
  const [form, setForm] = useState({ code: '', name: '', category: 'GEL' as PenCategory, width: '0.5', target: '0.8', min: '0.5', max: '1.2', hard: '1.6', vmax: '30', surcharge: '0' })
  const f = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: k === 'surcharge' ? intOnly(e.target.value) : ['code', 'name', 'category'].includes(k) ? e.target.value : decOnly(e.target.value) })
  const [lo, mid, hi, max] = [Number(form.min), Number(form.target), Number(form.max), Number(form.hard)]
  const band = lo > 0 && lo < mid && mid < hi && hi < max
  return (
    <section className="wk-block">
      <ErrorLine err={err} />
      <details className="wk-lines">
        <summary>{t('mg.add')}</summary>
        <div className="wk-form">
          <label className="vh-label">{t('mg.code')}<input className="vh-input" value={form.code} onChange={f('code')} /></label>
          <label className="vh-label wk-grow">{t('mg.name')}<input className="vh-input" value={form.name} onChange={f('name')} /></label>
          <label className="vh-label">{t('mg.category')}
            <select className="vh-select" value={form.category} onChange={f('category')}>{PEN_CATEGORIES.map((c) => <option key={c} value={c}>{t(`pen.${c}`)}</option>)}</select>
          </label>
          <label className="vh-label">{t('mg.width')}<input className="vh-input" value={form.width} onChange={f('width')} /></label>
          <label className="vh-label">{t('mg.fMin')}<input className="vh-input" value={form.min} onChange={f('min')} /></label>
          <label className="vh-label">{t('mg.fTarget')}<input className="vh-input" value={form.target} onChange={f('target')} /></label>
          <label className="vh-label">{t('mg.fMax')}<input className="vh-input" value={form.max} onChange={f('max')} /></label>
          <label className="vh-label">{t('mg.fHard')}<input className="vh-input" value={form.hard} onChange={f('hard')} /></label>
          <label className="vh-label">{t('mg.vMax')}<input className="vh-input" value={form.vmax} onChange={f('vmax')} /></label>
          <label className="vh-label">{t('mg.surcharge')}<input className="vh-input" inputMode="numeric" value={form.surcharge} onChange={f('surcharge')} /></label>
          <button
            className="vh-btn vh-btn--primary vh-btn--md"
            disabled={busy || !form.code || !form.name || !band}
            onClick={() => void run(() => createPen({
              code: form.code, name: form.name, category: form.category, stroke_width_mm: Number(form.width), f_target_n: Number(form.target), f_min_n: Number(form.min),
              f_max_n: Number(form.max), f_hard_n: Number(form.hard), v_max_mm_s: Number(form.vmax), surcharge: Number(form.surcharge) || 0,
            }))}
          >{t('mg.create')}</button>
        </div>
        {!band && <p className="wk-warn">{t('mg.forceBand')}</p>}
      </details>
      <ul className="mg-rows">
        {(list.data ?? []).map((p) => (
          <li key={p.id} className={p.active ? '' : 'off'}>
            <div className="mg-row">
              <span className="mg-name"><b>{p.name}</b><small>{p.code} · {t(`pen.${p.category}`)} · {p.widthMm} mm · {p.fMin}/{p.fTarget}/{p.fMax}/{p.fHard} N · {p.vMax} mm/s</small></span>
              <label className="mg-inline">{t('mg.surcharge')}
                <input className="vh-input" inputMode="numeric" value={sur[p.id] ?? String(p.surcharge)} onChange={(e) => setSur({ ...sur, [p.id]: intOnly(e.target.value) })} />
              </label>
              <button className="vh-btn vh-btn--ghost vh-btn--sm" disabled={busy || sur[p.id] === undefined || Number(sur[p.id]) === p.surcharge} onClick={() => void run(() => patchPen(p.id, { surcharge: Number(sur[p.id]) }))}>{t('mg.save')}</button>
              <span className="vh-mono mg-stock">{t('mg.inStock', { n: p.stock })}</span>
              <button className="vh-link" onClick={() => setStockFor(stockFor === p.id ? null : p.id)}>{t('mg.stock')}</button>
              <label className="wk-check"><input type="checkbox" checked={p.active} disabled={busy} onChange={(e) => void run(() => patchPen(p.id, { is_active: e.target.checked }))} /> {t('mg.active')}</label>
            </div>
            {stockFor === p.id && <StockForm busy={busy} onCancel={() => setStockFor(null)} onSend={(c) => void run(() => stockPen(p.id, c)).then((ok) => ok && setStockFor(null))} />}
          </li>
        ))}
      </ul>
    </section>
  )
}

// ---------- inks ----------

function Inks() {
  const t = useT()
  const pens = useAsync(adminPens, [])
  const [penId, setPenId] = useState<number | null>(null)
  const pid = penId ?? pens.data?.[0]?.id ?? null
  const list = useAsync(() => (pid ? adminInks(pid) : Promise.resolve([])), [pid])
  const { busy, err, run } = useRun(() => void list.reload())
  const [stockFor, setStockFor] = useState<number | null>(null)
  const [form, setForm] = useState({ name: '', hex: '#1b2440', price: '0', stock: '0' })
  const [price, setPrice] = useState<Record<number, string>>({})
  return (
    <section className="wk-block">
      <ErrorLine err={err} />
      <p className="sd-sub">{t('mg.inksLede')}</p>
      <label className="vh-label wk-grow">
        {t('mg.forPen')}
        <select className="vh-select" value={pid ?? ''} onChange={(e) => setPenId(Number(e.target.value))}>
          {(pens.data ?? []).map((p) => <option key={p.id} value={p.id}>{p.name} · {p.code}{p.active ? '' : ` (${t('mg.inactive')})`}</option>)}
        </select>
      </label>
      {pid && (
        <details className="wk-lines" open={!list.data?.length}>
          <summary>{t('mg.addInk')}</summary>
          <div className="wk-form">
            <label className="vh-label wk-grow">{t('mg.name')}<input className="vh-input" value={form.name} maxLength={60} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
            <label className="vh-label">{t('mg.color')}<input className="mg-color" type="color" value={form.hex} onChange={(e) => setForm({ ...form, hex: e.target.value })} /></label>
            <label className="vh-label">{t('mg.price')}<input className="vh-input" inputMode="numeric" value={form.price} onChange={(e) => setForm({ ...form, price: intOnly(e.target.value) })} /></label>
            <label className="vh-label">{t('mg.stock')}<input className="vh-input" inputMode="numeric" value={form.stock} onChange={(e) => setForm({ ...form, stock: intOnly(e.target.value) })} /></label>
            <button
              className="vh-btn vh-btn--primary vh-btn--md"
              disabled={busy || !form.name.trim()}
              onClick={() => void run(() => createInk(pid, { name: form.name.trim(), hex_code: form.hex, unit_price: Number(form.price) || 0, stock_qty: Number(form.stock) || 0 })).then((ok) => ok && setForm({ ...form, name: '' }))}
            >{t('mg.create')}</button>
          </div>
        </details>
      )}
      {list.data && !list.data.length && <p className="sd-sub">{t('co.noInks')}</p>}
      <ul className="mg-rows">
        {(list.data ?? []).map((i) => (
          <li key={i.id} className={i.active ? '' : 'off'}>
            <div className="mg-row">
              <span className="mg-name"><b><i className="co-ink-dot co-ink-dot--sm" style={{ background: i.hex ?? 'var(--t5)' }} /> {i.name}</b><small>{i.hex ?? ''}</small></span>
              <input className="mg-color" type="color" aria-label={t('mg.color')} value={i.hex ?? '#000000'} disabled={busy} onChange={(e) => void run(() => patchInk(i.id, { hex_code: e.target.value }))} />
              <label className="mg-inline">{t('mg.price')}
                <input className="vh-input" inputMode="numeric" value={price[i.id] ?? String(i.unitPrice)} onChange={(e) => setPrice({ ...price, [i.id]: intOnly(e.target.value) })} />
              </label>
              <button className="vh-btn vh-btn--ghost vh-btn--sm" disabled={busy || price[i.id] === undefined || Number(price[i.id]) === i.unitPrice} onClick={() => void run(() => patchInk(i.id, { unit_price: Number(price[i.id]) }))}>{t('mg.save')}</button>
              <span className="vh-mono mg-stock">{t('mg.inStock', { n: i.stock })}</span>
              <button className="vh-link" onClick={() => setStockFor(stockFor === i.id ? null : i.id)}>{t('mg.stock')}</button>
              <label className="wk-check"><input type="checkbox" checked={i.active} disabled={busy} onChange={(e) => void run(() => patchInk(i.id, { is_active: e.target.checked }))} /> {t('mg.active')}</label>
            </div>
            {stockFor === i.id && <StockForm busy={busy} onCancel={() => setStockFor(null)} onSend={(c) => void run(() => stockInk(i.id, c)).then((ok) => ok && setStockFor(null))} />}
          </li>
        ))}
      </ul>
    </section>
  )
}

// ---------- compatibility ----------

function Compat() {
  const t = useT()
  const papers = useAsync(adminPapers, [])
  const pens = useAsync(adminPens, [])
  const rows = useAsync(adminCompat, [])
  const { busy, err, run } = useRun(() => void rows.reload())
  const [paperId, setPaperId] = useState<number | null>(null)
  const pid = paperId ?? papers.data?.[0]?.id ?? null
  const on = useMemo(() => new Set((rows.data ?? []).filter((c) => c.compatible && c.paperId === pid).map((c) => c.penId)), [rows.data, pid])
  return (
    <section className="wk-block">
      <ErrorLine err={err} />
      <p className="sd-sub">{t('mg.compatLede')}</p>
      <label className="vh-label wk-grow">
        {t('mg.forPaper')}
        <select className="vh-select" value={pid ?? ''} onChange={(e) => setPaperId(Number(e.target.value))}>
          {(papers.data ?? []).map((p) => <option key={p.id} value={p.id}>{p.name} · {p.size}{p.active ? '' : ` (${t('mg.inactive')})`}</option>)}
        </select>
      </label>
      {pid && (
        <ul className="mg-rows">
          {(pens.data ?? []).map((p) => (
            <li key={p.id} className={p.active ? '' : 'off'}>
              <label className="mg-row wk-check">
                <input type="checkbox" checked={on.has(p.id)} disabled={busy} onChange={(e) => void run(() => setCompat(pid, p.id, e.target.checked))} />
                <span className="mg-name"><b>{p.name}</b><small>{p.code} · {t(`pen.${p.category}`)}</small></span>
              </label>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

// ---------- templates ----------

function Templates() {
  const t = useT()
  const list = useAsync(adminTemplates, [])
  const { busy, err, run } = useRun(() => void list.reload())
  const [form, setForm] = useState({ code: '', name: '', kind: 'SINGLE_LINE_FONT', font: 'hershey:' })
  return (
    <section className="wk-block">
      <ErrorLine err={err} />
      <details className="wk-lines">
        <summary>{t('mg.add')}</summary>
        <div className="wk-form">
          <label className="vh-label">{t('mg.code')}<input className="vh-input" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} /></label>
          <label className="vh-label wk-grow">{t('mg.name')}<input className="vh-input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
          <label className="vh-label">{t('mg.kind')}
            <select className="vh-select" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>{TEMPLATE_KINDS.map((k) => <option key={k} value={k}>{t(`tpl.${k}`)}</option>)}</select>
          </label>
          <label className="vh-label wk-grow">{t('mg.fontUri')}<input className="vh-input" value={form.font} onChange={(e) => setForm({ ...form, font: e.target.value })} /></label>
          <button className="vh-btn vh-btn--primary vh-btn--md" disabled={busy || !form.code || !form.name || form.font.length < 3} onClick={() => void run(() => createTemplate({ code: form.code, name: form.name, kind: form.kind, font_uri: form.font }))}>{t('mg.create')}</button>
        </div>
        <p className="sd-sub">{t('mg.fontHint')}</p>
      </details>
      <ul className="mg-rows">
        {(list.data ?? []).map((x) => (
          <li key={x.id} className={x.active ? '' : 'off'}>
            <div className="mg-row">
              <span className="mg-name"><b>{x.name}</b><small>{x.code} · {t(`tpl.${x.kind}`)} · {x.fontUri}</small></span>
              <label className="wk-check"><input type="checkbox" checked={x.active} disabled={busy} onChange={(e) => void run(() => patchTemplate(x.id, { is_active: e.target.checked }))} /> {t('mg.active')}</label>
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}

// ---------- handwriting styles waiting for review ----------

function Styles() {
  const t = useT()
  const locale = useLocale()
  const list = useAsync(() => adminStyles('PENDING_REVIEW'), [])
  const { busy, err, run } = useRun(() => void list.reload())
  const [reason, setReason] = useState<Record<number, string>>({})
  return (
    <section className="wk-block">
      <ErrorLine err={err} />
      <p className="sd-sub">{t('mg.stylesLede')}</p>
      {list.data && !list.data.length && <p className="sd-sub">{t('mg.stylesNone')}</p>}
      <ul className="mg-rows">
        {(list.data ?? []).map((s) => (
          <li key={s.id}>
            <div className="mg-row">
              <span className="mg-name"><b>{s.name}</b><small>#{s.ownerId} · {new Date(s.createdAt).toLocaleDateString(locale)} · {s.coverage !== null ? `${s.coverage}%` : '–'} · {t(s.rightToUse ? 'mg.rightYes' : 'mg.rightNo')}</small></span>
              <input className="vh-input mg-reason" value={reason[s.id] ?? ''} placeholder={t('wk.rejectAdjustReason')} aria-label={t('wk.rejectAdjustReason')} onChange={(e) => setReason({ ...reason, [s.id]: e.target.value })} />
              <button className="vh-btn vh-btn--primary vh-btn--sm" disabled={busy || !s.rightToUse} onClick={() => void run(() => approveStyle(s.id))}>{t('wk.approveAdjust')}</button>
              <button className="vh-btn vh-btn--ghost vh-btn--sm" disabled={busy || !(reason[s.id] ?? '').trim()} onClick={() => void run(() => rejectStyle(s.id, (reason[s.id] ?? '').trim()))}>{t('wk.rejectAdjust')}</button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}

// ---------- robots ----------

const ROBOT_STATUS: AdminRobot['status'][] = ['AVAILABLE', 'MAINTENANCE', 'BROKEN']

function Robots() {
  const t = useT()
  const list = useAsync(adminRobots, [])
  const { busy, err, run } = useRun(() => void list.reload())
  const [form, setForm] = useState({ code: '', station: '' })
  const [moved, setMoved] = useState<{ code: string; jobs: number[] } | null>(null)
  const toggleCat = (r: AdminRobot, c: PenCategory) => {
    const has = r.penCategories.includes(c)
    return run(() => patchRobot(r.id, { supported_pen_categories: has ? r.penCategories.filter((x) => x !== c) : [...r.penCategories, c] }))
  }
  return (
    <section className="wk-block">
      <ErrorLine err={err} />
      {moved && !!moved.jobs.length && <p className="wk-warn" role="status">{t('mg.robotJobs', { code: moved.code, n: moved.jobs.length })}</p>}
      <details className="wk-lines">
        <summary>{t('mg.add')}</summary>
        <div className="wk-form">
          <label className="vh-label">{t('mg.code')}<input className="vh-input" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} /></label>
          <label className="vh-label wk-grow">{t('mg.station')}<input className="vh-input" value={form.station} maxLength={50} onChange={(e) => setForm({ ...form, station: e.target.value })} /></label>
          <button className="vh-btn vh-btn--primary vh-btn--md" disabled={busy || form.code.length < 2} onClick={() => void run(() => createRobot({ code: form.code, station: form.station || null })).then((ok) => ok && setForm({ code: '', station: '' }))}>{t('mg.create')}</button>
        </div>
      </details>
      <ul className="mg-rows">
        {(list.data ?? []).map((r) => (
          <li key={r.id}>
            <div className="mg-row">
              <span className="mg-name"><b>{r.code}</b><small>{r.type}{r.station ? ` · ${r.station}` : ''}{r.simulated ? ` · ${t('wk.simulated')}` : ''}</small></span>
              <label className="mg-inline">{t('mg.status')}
                <select
                  className="vh-select"
                  value={r.status}
                  disabled={busy || r.status === 'BUSY'}
                  onChange={(e) => void run(async () => {
                    const res = await patchRobot(r.id, { status: e.target.value as AdminRobot['status'] })
                    setMoved({ code: res.code, jobs: res.affectedJobs })
                  })}
                >
                  {(r.status === 'BUSY' ? [...ROBOT_STATUS, 'BUSY' as const] : ROBOT_STATUS).map((s) => <option key={s} value={s} disabled={s === 'BUSY'}>{t(`rs.${s}`)}</option>)}
                </select>
              </label>
            </div>
            <div className="mg-cats" role="group" aria-label={t('mg.penCats')}>
              <span className="sd-sub">{t('mg.penCats')}{r.penCategories.length ? '' : ` (${t('mg.anyPen')})`}</span>
              {PEN_CATEGORIES.map((c) => (
                <label key={c} className="wk-check"><input type="checkbox" checked={r.penCategories.includes(c)} disabled={busy} onChange={() => void toggleCat(r, c)} /> {t(`pen.${c}`)}</label>
              ))}
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}

// ---------- price list ----------

const FIELDS: { key: keyof PriceList; api: string; label: string; money?: boolean }[] = [
  { key: 'uOt1', api: 'u_ot1', label: 'mg.p.uOt1', money: true },
  { key: 'uOt2', api: 'u_ot2', label: 'mg.p.uOt2', money: true },
  { key: 'uOt3', api: 'u_ot3', label: 'mg.p.uOt3', money: true },
  { key: 'wMin', api: 'w_min', label: 'mg.p.wMin', money: true },
  { key: 'sOt1', api: 's_ot1', label: 'mg.p.sOt1', money: true },
  { key: 'sOt2', api: 's_ot2', label: 'mg.p.sOt2', money: true },
  { key: 'sOt3', api: 's_ot3', label: 'mg.p.sOt3', money: true },
  { key: 'kSimple', api: 'k_simple', label: 'mg.p.kSimple' },
  { key: 'kMedium', api: 'k_medium', label: 'mg.p.kMedium' },
  { key: 'kComplex', api: 'k_complex', label: 'mg.p.kComplex' },
  { key: 'minDepositPct', api: 'p_min_pct', label: 'mg.p.minDeposit' },
  { key: 'adjustThresholdPct', api: 'adjust_threshold_pct', label: 'mg.p.threshold' },
  { key: 'canvasMmPerChar', api: 'canvas_mm_per_char', label: 'mg.p.canvas' },
]

function Pricing() {
  const t = useT()
  const locale = useLocale()
  const list = useAsync(priceVersions, [])
  const { busy, err, run } = useRun(() => {
    setEdit({})
    setNote('')
    void list.reload()
  })
  const [edit, setEdit] = useState<Record<string, string>>({})
  const [note, setNote] = useState('')
  const [tiers, setTiers] = useState<{ minQty: string; pct: string }[] | null>(null)
  const versions = list.data ?? []
  const cur = versions.find((v) => v.active) ?? versions[0]
  if (!cur) return <section className="wk-block"><ErrorLine err={list.error ? orderErrorKey(list.error) : ''} /></section>

  const shownTiers = tiers ?? cur.tiers.map((x) => ({ minQty: String(x.minQty), pct: String(x.pct) }))
  const changes: Record<string, unknown> = {}
  for (const f of FIELDS) {
    const v = edit[f.key]
    if (v !== undefined && v !== '' && Number(v) !== cur[f.key]) changes[f.api] = Number(v)
  }
  if (tiers) changes.discount_tiers = tiers.filter((x) => x.minQty && x.pct).map((x) => ({ min_qty: Number(x.minQty), pct: Number(x.pct) }))
  if (note.trim()) changes.note = note.trim()
  const hasChange = Object.keys(changes).some((k) => k !== 'note')

  return (
    <section className="wk-block">
      <ErrorLine err={err} />
      <p className="sd-sub">{t('mg.priceLede', { v: cur.version })}</p>
      <div className="wk-form mg-price">
        {FIELDS.map((f) => (
          <label key={f.key} className="vh-label">
            {t(f.label)}
            <input
              className="vh-input"
              inputMode="decimal"
              value={edit[f.key] ?? String(cur[f.key])}
              onChange={(e) => setEdit({ ...edit, [f.key]: f.money ? intOnly(e.target.value) : decOnly(e.target.value) })}
            />
          </label>
        ))}
      </div>
      <div className="vh-stack" style={{ gap: 8 }}>
        <span className="vh-label">{t('mg.p.tiers')}</span>
        {shownTiers.map((x, i) => (
          <div key={i} className="wk-form">
            <label className="vh-label">{t('mg.p.tierQty')}<input className="vh-input" inputMode="numeric" value={x.minQty} onChange={(e) => setTiers(shownTiers.map((y, j) => (j === i ? { ...y, minQty: intOnly(e.target.value) } : y)))} /></label>
            <label className="vh-label">{t('mg.p.tierPct')}<input className="vh-input" inputMode="decimal" value={x.pct} onChange={(e) => setTiers(shownTiers.map((y, j) => (j === i ? { ...y, pct: decOnly(e.target.value) } : y)))} /></label>
            <button className="vh-btn vh-btn--ghost vh-btn--sm" onClick={() => setTiers(shownTiers.filter((_, j) => j !== i))}>{t('co.remove')}</button>
          </div>
        ))}
        <button className="vh-btn vh-btn--ghost vh-btn--sm wk-self" onClick={() => setTiers([...shownTiers, { minQty: '', pct: '' }])}>{t('mg.p.addTier')}</button>
      </div>
      <label className="vh-label">
        {t('mg.p.note')}
        <input className="vh-input" value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} />
      </label>
      <button className="vh-btn vh-btn--primary vh-btn--md wk-self" disabled={busy || !hasChange} onClick={() => void run(() => savePrice(changes))}>{t('mg.p.save')}</button>
      <p className="sd-sub">{t('mg.p.saveHint')}</p>

      <details className="wk-lines">
        <summary>{t('mg.p.history')}</summary>
        <dl className="wk-rows">
          {versions.map((v) => (
            <div key={v.version}>
              <dt>v{v.version}{v.active ? ` · ${t('mg.active')}` : ''} · {new Date(v.createdAt).toLocaleDateString(locale)}</dt>
              <dd>{v.note ?? '–'} · {t('mg.p.minDeposit')} {v.minDepositPct}% · {t('mg.p.threshold')} {v.adjustThresholdPct}% · {fmt(v.uOt3)}</dd>
            </div>
          ))}
        </dl>
      </details>
    </section>
  )
}
