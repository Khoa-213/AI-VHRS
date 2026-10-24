import { MagnifyingGlass, Plus, Warning } from '@phosphor-icons/react'
import { useMemo, useState } from 'react'
import { useAsync } from '../../hooks/useAsync'
import { useT } from '../../i18n'
import {
  PAPER_SIZES, PEN_CATEGORIES, SURFACES, adminCompat, adminInks, adminPapers, adminPens, createInk, createPaper, createPen, patchInk,
  patchPaper, patchPen, setCompat, stockInk, stockPaper, stockPen,
  type AdminInk, type AdminPaper, type AdminPen, type PenCategory,
} from '../../services/manage'
import { orderErrorKey } from '../../services/orders'
import { ErrorLine, StockForm, decOnly, intOnly, useRun } from './catalogKit'

/*
 * Paper, pens and ink colors are one chain for the customer (GET /catalog/suggest-materials): a paper offers only the
 * active pens ticked as compatible with it (paper_pen_compats, a missing row means "no"), and a pen is offered only
 * with its own active ink colors (ink_colors.pen_type_id); a pen without one is hidden. So this screen shows every
 * item with its links, flags the ones a customer cannot order, and a new paper or pen is created together with its links.
 */

type Kind = 'paper' | 'pen'
type Filter = 'all' | 'issue' | 'off'
type Ctx = ReturnType<typeof useCatalog>

function useCatalog() {
  const papers = useAsync(adminPapers, [])
  const pens = useAsync(adminPens, [])
  const inks = useAsync(() => adminInks(), [])
  const compat = useAsync(adminCompat, [])
  const reload = () => Promise.all([papers.reload(), pens.reload(), inks.reload(), compat.reload()])

  const links = useMemo(() => (compat.data ?? []).filter((c) => c.compatible), [compat.data])
  const allInks = useMemo(() => inks.data ?? [], [inks.data])
  const inksOf = (penId: number) => allInks.filter((i) => i.penId === penId)
  const liveInks = (penId: number) => allInks.filter((i) => i.penId === penId && i.active)
  const pensOf = (paperId: number) => new Set(links.filter((c) => c.paperId === paperId).map((c) => c.penId))
  const papersOf = (penId: number) => new Set(links.filter((c) => c.penId === penId).map((c) => c.paperId))
  const penById = (id: number) => pens.data?.find((p) => p.id === id)
  // What the customer would actually be offered.
  const orderablePens = (paperId: number) => [...pensOf(paperId)].filter((id) => penById(id)?.active && liveInks(id).length > 0)
  const paperIssue = (p: AdminPaper) => p.active && orderablePens(p.id).length === 0
  const penIssue = (p: AdminPen) => p.active && (papersOf(p.id).size === 0 || liveInks(p.id).length === 0)

  return {
    papers: papers.data ?? [], pens: pens.data ?? [], loading: !papers.data || !pens.data || !inks.data || !compat.data,
    error: papers.error ?? pens.error ?? inks.error ?? compat.error,
    reload, inksOf, liveInks, pensOf, papersOf, orderablePens, paperIssue, penIssue,
  }
}

export default function Materials() {
  const t = useT()
  const c = useCatalog()
  const [kind, setKind] = useState<Kind>('paper')
  const [sel, setSel] = useState<number | 'new' | null>(null)
  const [q, setQ] = useState('')
  const [filter, setFilter] = useState<Filter>('all')

  const match = (x: { name: string; code: string; active: boolean }, issue: boolean) =>
    (!q.trim() || `${x.name} ${x.code}`.toLowerCase().includes(q.trim().toLowerCase()))
    && (filter === 'all' || (filter === 'off' ? !x.active : issue))
  const papers = c.papers.filter((p) => match(p, c.paperIssue(p)))
  const pens = c.pens.filter((p) => match(p, c.penIssue(p)))
  const issues = kind === 'paper' ? c.papers.filter(c.paperIssue).length : c.pens.filter(c.penIssue).length

  const switchKind = (k: Kind) => {
    setKind(k)
    setSel(null)
  }
  const paper = kind === 'paper' && typeof sel === 'number' ? c.papers.find((p) => p.id === sel) : undefined
  const pen = kind === 'pen' && typeof sel === 'number' ? c.pens.find((p) => p.id === sel) : undefined

  return (
    <div className="mt">
      <aside className="mt-list" aria-label={t('mg.tab.materials')}>
        <div className="mt-list-top">
          <div className="mt-seg" role="tablist">
            {(['paper', 'pen'] as const).map((k) => (
              <button key={k} role="tab" aria-selected={kind === k} className={kind === k ? 'on' : ''} onClick={() => switchKind(k)}>
                {t(k === 'paper' ? 'mg.m.paper' : 'mg.m.pens')}
                <span className="mt-count">{k === 'paper' ? c.papers.length : c.pens.length}</span>
              </button>
            ))}
          </div>
          <button className="vh-btn vh-btn--primary vh-btn--sm mt-new" onClick={() => setSel('new')}>
            <Plus size={14} weight="bold" aria-hidden />
            {t(kind === 'paper' ? 'mg.m.newPaper' : 'mg.m.newPen')}
          </button>
        </div>
        <label className="mt-search">
          <MagnifyingGlass size={16} aria-hidden />
          <input value={q} placeholder={t('mg.m.search')} aria-label={t('mg.m.search')} onChange={(e) => setQ(e.target.value)} />
        </label>
        <div className="mt-filters" role="group" aria-label={t('mg.m.filter')}>
          {(['all', 'issue', 'off'] as const).map((f) => (
            <button key={f} aria-pressed={filter === f} className={filter === f ? 'on' : ''} onClick={() => setFilter(f)}>
              {t(`mg.m.f.${f}`)}{f === 'issue' && issues > 0 ? ` · ${issues}` : ''}
            </button>
          ))}
        </div>

        {!!c.error && <ErrorLine err={orderErrorKey(c.error)} />}
        {c.loading && <p className="sd-sub" role="status">{t('co.loading')}</p>}
        <ul className="mt-items">
          {kind === 'paper' && papers.map((p) => {
            const n = c.orderablePens(p.id).length
            return (
              <li key={p.id}>
                <button className={`mt-item${sel === p.id ? ' on' : ''}${p.active ? '' : ' off'}`} aria-current={sel === p.id || undefined} onClick={() => setSel(p.id)}>
                  <span className="mt-item-main">
                    <b>{p.name}</b>
                    <small>{p.code} · {p.size} · {p.gsm} gsm</small>
                  </span>
                  <span className="mt-item-side">
                    {c.paperIssue(p)
                      ? <span className="mt-flag"><Warning size={12} weight="bold" aria-hidden />{t('mg.m.noLinkPaper')}</span>
                      : <span className="mt-tag">{t('mg.m.nPens', { n })}</span>}
                    <span className="mt-stock">{t('mg.inStock', { n: p.stock })}</span>
                  </span>
                </button>
              </li>
            )
          })}
          {kind === 'pen' && pens.map((p) => {
            const noPaper = c.papersOf(p.id).size === 0
            return (
              <li key={p.id}>
                <button className={`mt-item${sel === p.id ? ' on' : ''}${p.active ? '' : ' off'}`} aria-current={sel === p.id || undefined} onClick={() => setSel(p.id)}>
                  <span className="mt-item-main">
                    <b>{p.name}</b>
                    <small>{p.code} · {t(`pen.${p.category}`)}</small>
                    <InkDots inks={c.liveInks(p.id)} />
                  </span>
                  <span className="mt-item-side">
                    {c.penIssue(p)
                      ? <span className="mt-flag"><Warning size={12} weight="bold" aria-hidden />{t(noPaper ? 'mg.m.noLinkPen' : 'mg.m.noInk')}</span>
                      : <span className="mt-tag">{t('mg.m.nPapers', { n: c.papersOf(p.id).size })}</span>}
                    <span className="mt-stock">{t('mg.inStock', { n: p.stock })}</span>
                  </span>
                </button>
              </li>
            )
          })}
          {!c.loading && (kind === 'paper' ? !papers.length : !pens.length) && <li className="sd-sub">{t('mg.m.empty')}</li>}
        </ul>
      </aside>

      <section className="wk-block mt-detail">
        {sel === 'new' && kind === 'paper' && <NewPaper c={c} onDone={(id) => setSel(id)} onCancel={() => setSel(null)} />}
        {sel === 'new' && kind === 'pen' && <NewPen c={c} onDone={(id) => setSel(id)} onCancel={() => setSel(null)} />}
        {paper && <PaperDetail key={paper.id} c={c} paper={paper} />}
        {pen && <PenDetail key={pen.id} c={c} pen={pen} />}
        {sel === null && <p className="mt-empty">{t('mg.m.pick')}</p>}
      </section>
    </div>
  )
}

function InkDots({ inks }: { inks: AdminInk[] }) {
  if (!inks.length) return null
  return (
    <span className="mt-dots" aria-hidden>
      {inks.slice(0, 8).map((i) => <i key={i.id} style={{ background: i.hex ?? 'var(--ink3)' }} />)}
    </span>
  )
}

/** Name, price or surcharge, stock and the active switch of one paper or pen. */
function Head({ name, sub, active, onActive, price, onPrice, priceLabel, stock, onStock, busy }: {
  name: string; sub: string; active: boolean; onActive: (v: boolean) => void; price: number; onPrice: (v: number) => void; priceLabel: string
  stock: number; onStock: (c: Parameters<typeof stockPaper>[1]) => void; busy: boolean
}) {
  const t = useT()
  const [value, setValue] = useState(String(price))
  const [stockOpen, setStockOpen] = useState(false)
  return (
    <>
      <header className="mt-head">
        <div>
          <h3>{name}</h3>
          <p className="sd-sub">{sub}</p>
        </div>
        <label className="wk-check"><input type="checkbox" checked={active} disabled={busy} onChange={(e) => onActive(e.target.checked)} /> {t('mg.active')}</label>
      </header>
      <div className="mt-facts">
        <label className="mt-fact">
          <span>{priceLabel}</span>
          <span className="mt-fact-row">
            <input className="vh-input" inputMode="numeric" value={value} onChange={(e) => setValue(intOnly(e.target.value))} />
            <button className="vh-btn vh-btn--ghost vh-btn--sm" disabled={busy || value === '' || Number(value) === price} onClick={() => onPrice(Number(value))}>{t('mg.save')}</button>
          </span>
        </label>
        <div className="mt-fact">
          <span>{t('mg.stock')}</span>
          <span className="mt-fact-row">
            <b className="vh-mono">{stock}</b>
            <button className="vh-link" onClick={() => setStockOpen(!stockOpen)}>{t('mg.m.adjust')}</button>
          </span>
        </div>
      </div>
      {stockOpen && <StockForm busy={busy} onCancel={() => setStockOpen(false)} onSend={(s) => { onStock(s); setStockOpen(false) }} />}
    </>
  )
}

// ---------- paper ----------

function PaperDetail({ c, paper }: { c: Ctx; paper: AdminPaper }) {
  const t = useT()
  const { busy, err, run } = useRun(() => void c.reload())
  const on = c.pensOf(paper.id)
  return (
    <>
      <ErrorLine err={err} />
      <Head
        name={paper.name} sub={`${paper.code} · ${paper.size} · ${t(`surface.${paper.surface}`)} · ${paper.gsm} gsm`} busy={busy}
        active={paper.active} onActive={(v) => void run(() => patchPaper(paper.id, { is_active: v }))}
        price={paper.unitPrice} priceLabel={t('mg.price')} onPrice={(v) => void run(() => patchPaper(paper.id, { unit_price: v }))}
        stock={paper.stock} onStock={(s) => void run(() => stockPaper(paper.id, s))}
      />
      {c.paperIssue(paper) && <p className="wk-warn" role="status">{t('mg.m.warnPaper')}</p>}
      <div className="mt-sect">
        <h4>{t('mg.m.pensTitle')}</h4>
        <p className="sd-sub">{t('mg.m.hintPaper')}</p>
        <ul className="mt-links">
          {c.pens.map((p) => (
            <li key={p.id}>
              <label className={`mt-link${on.has(p.id) ? ' on' : ''}${p.active ? '' : ' off'}`}>
                <input type="checkbox" checked={on.has(p.id)} disabled={busy} onChange={(e) => void run(() => setCompat(paper.id, p.id, e.target.checked))} />
                <span className="mt-link-main">
                  <b>{p.name}</b>
                  <small>{t(`pen.${p.category}`)}{p.active ? '' : ` · ${t('mg.inactive')}`}{c.liveInks(p.id).length ? '' : ` · ${t('mg.m.noInkShort')}`}</small>
                </span>
                <InkDots inks={c.liveInks(p.id)} />
              </label>
            </li>
          ))}
        </ul>
      </div>
    </>
  )
}

function NewPaper({ c, onDone, onCancel }: { c: Ctx; onDone: (id: number) => void; onCancel: () => void }) {
  const t = useT()
  const { busy, err, run } = useRun(() => void c.reload())
  const [form, setForm] = useState({ code: '', name: '', gsm: '80', surface: 'PLAIN', size: 'A4', price: '', stock: '0' })
  const [pens, setPens] = useState<Set<number>>(new Set())
  const [partial, setPartial] = useState<{ id: number; name: string } | null>(null)
  const ok = form.code && form.name && form.price && pens.size > 0

  const create = async () => {
    let made: AdminPaper | null = null
    const done = await run(async () => {
      made = await createPaper({ code: form.code, name: form.name, gsm: Number(form.gsm), surface: form.surface, size: form.size, unit_price: Number(form.price), stock_qty: Number(form.stock) || 0 })
      for (const id of pens) await setCompat(made.id, id, true)
    })
    const m = made as AdminPaper | null
    if (m && !done) setPartial({ id: m.id, name: m.name })
    else if (m) onDone(m.id)
  }

  return (
    <>
      <header className="mt-head"><h3>{t('mg.m.newPaper')}</h3></header>
      <ErrorLine err={err} />
      {partial && (
        <p className="wk-warn" role="status">
          {t('mg.m.partial', { name: partial.name })} <button className="vh-link" onClick={() => onDone(partial.id)}>{t('mg.m.openIt')}</button>
        </p>
      )}
      <div className="wk-form">
        <label className="vh-label">{t('mg.code')}<input className="vh-input" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} /></label>
        <label className="vh-label wk-grow">{t('mg.name')}<input className="vh-input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
        <label className="vh-label">{t('mg.size')}
          <select className="vh-select" value={form.size} onChange={(e) => setForm({ ...form, size: e.target.value })}>{PAPER_SIZES.map((s) => <option key={s} value={s}>{s}</option>)}</select>
        </label>
        <label className="vh-label">{t('mg.surface')}
          <select className="vh-select" value={form.surface} onChange={(e) => setForm({ ...form, surface: e.target.value })}>{SURFACES.map((s) => <option key={s} value={s}>{t(`surface.${s}`)}</option>)}</select>
        </label>
        <label className="vh-label">{t('mg.gsm')}<input className="vh-input" inputMode="numeric" value={form.gsm} onChange={(e) => setForm({ ...form, gsm: intOnly(e.target.value) })} /></label>
        <label className="vh-label">{t('mg.price')}<input className="vh-input" inputMode="numeric" value={form.price} onChange={(e) => setForm({ ...form, price: intOnly(e.target.value) })} /></label>
        <label className="vh-label">{t('mg.stock')}<input className="vh-input" inputMode="numeric" value={form.stock} onChange={(e) => setForm({ ...form, stock: intOnly(e.target.value) })} /></label>
      </div>
      <div className="mt-sect">
        <h4>{t('mg.m.pensTitle')}</h4>
        <p className="sd-sub">{t('mg.m.needPen')}</p>
        <ul className="mt-links">
          {c.pens.filter((p) => p.active).map((p) => (
            <li key={p.id}>
              <label className={`mt-link${pens.has(p.id) ? ' on' : ''}`}>
                <input type="checkbox" checked={pens.has(p.id)} onChange={(e) => setPens(toggle(pens, p.id, e.target.checked))} />
                <span className="mt-link-main">
                  <b>{p.name}</b>
                  <small>{t(`pen.${p.category}`)}{c.liveInks(p.id).length ? '' : ` · ${t('mg.m.noInkShort')}`}</small>
                </span>
                <InkDots inks={c.liveInks(p.id)} />
              </label>
            </li>
          ))}
        </ul>
      </div>
      <div className="wk-actions">
        <button className="vh-btn vh-btn--ghost vh-btn--md" onClick={onCancel}>{t('mg.m.cancel')}</button>
        <button className="vh-btn vh-btn--primary vh-btn--md" disabled={busy || !ok || !!partial} onClick={() => void create()}>{t('mg.m.createPaper')}</button>
      </div>
    </>
  )
}

// ---------- pen ----------

function PenDetail({ c, pen }: { c: Ctx; pen: AdminPen }) {
  const t = useT()
  const { busy, err, run } = useRun(() => void c.reload())
  const on = c.papersOf(pen.id)
  const inks = c.inksOf(pen.id)
  const [ink, setInk] = useState({ name: '', hex: '#1b2440', price: '0', stock: '0' })
  const noPaper = on.size === 0
  return (
    <>
      <ErrorLine err={err} />
      <Head
        name={pen.name} sub={`${pen.code} · ${t(`pen.${pen.category}`)} · ${pen.widthMm} mm · ${pen.fMin}/${pen.fTarget}/${pen.fMax}/${pen.fHard} N · ${pen.vMax} mm/s`} busy={busy}
        active={pen.active} onActive={(v) => void run(() => patchPen(pen.id, { is_active: v }))}
        price={pen.surcharge} priceLabel={t('mg.surcharge')} onPrice={(v) => void run(() => patchPen(pen.id, { surcharge: v }))}
        stock={pen.stock} onStock={(s) => void run(() => stockPen(pen.id, s))}
      />
      {c.penIssue(pen) && <p className="wk-warn" role="status">{t(noPaper ? 'mg.m.warnPenPaper' : 'mg.m.warnPenInk')}</p>}

      <div className="mt-sect">
        <h4>{t('mg.m.inksTitle')}</h4>
        <p className="sd-sub">{t('mg.inksLede')}</p>
        <ul className="mt-inks">
          {inks.map((i) => <InkRow key={i.id} ink={i} busy={busy} run={run} />)}
        </ul>
        <div className="wk-form mt-add">
          <label className="vh-label wk-grow">{t('mg.name')}<input className="vh-input" value={ink.name} maxLength={60} onChange={(e) => setInk({ ...ink, name: e.target.value })} /></label>
          <label className="vh-label">{t('mg.color')}<input className="mg-color" type="color" value={ink.hex} onChange={(e) => setInk({ ...ink, hex: e.target.value })} /></label>
          <label className="vh-label">{t('mg.price')}<input className="vh-input" inputMode="numeric" value={ink.price} onChange={(e) => setInk({ ...ink, price: intOnly(e.target.value) })} /></label>
          <label className="vh-label">{t('mg.stock')}<input className="vh-input" inputMode="numeric" value={ink.stock} onChange={(e) => setInk({ ...ink, stock: intOnly(e.target.value) })} /></label>
          <button
            className="vh-btn vh-btn--ghost vh-btn--md"
            disabled={busy || !ink.name.trim()}
            onClick={() => void run(() => createInk(pen.id, { name: ink.name.trim(), hex_code: ink.hex, unit_price: Number(ink.price) || 0, stock_qty: Number(ink.stock) || 0 })).then((ok) => ok && setInk({ ...ink, name: '' }))}
          >{t('mg.addInk')}</button>
        </div>
      </div>

      <div className="mt-sect">
        <h4>{t('mg.m.papersTitle')}</h4>
        <p className="sd-sub">{t('mg.m.hintPen')}</p>
        <ul className="mt-links">
          {c.papers.map((p) => (
            <li key={p.id}>
              <label className={`mt-link${on.has(p.id) ? ' on' : ''}${p.active ? '' : ' off'}`}>
                <input type="checkbox" checked={on.has(p.id)} disabled={busy} onChange={(e) => void run(() => setCompat(p.id, pen.id, e.target.checked))} />
                <span className="mt-link-main">
                  <b>{p.name}</b>
                  <small>{p.size} · {t(`surface.${p.surface}`)} · {p.gsm} gsm{p.active ? '' : ` · ${t('mg.inactive')}`}</small>
                </span>
              </label>
            </li>
          ))}
        </ul>
      </div>
    </>
  )
}

function InkRow({ ink, busy, run }: { ink: AdminInk; busy: boolean; run: ReturnType<typeof useRun>['run'] }) {
  const t = useT()
  const [price, setPrice] = useState(String(ink.unitPrice))
  const [stockOpen, setStockOpen] = useState(false)
  return (
    <li className={ink.active ? '' : 'off'}>
      <div className="mt-ink">
        <input className="mg-color" type="color" aria-label={t('mg.color')} value={ink.hex ?? '#000000'} disabled={busy} onChange={(e) => void run(() => patchInk(ink.id, { hex_code: e.target.value }))} />
        <b className="mt-ink-name">{ink.name}</b>
        <label className="mg-inline">{t('mg.price')}
          <input className="vh-input" inputMode="numeric" value={price} onChange={(e) => setPrice(intOnly(e.target.value))} />
        </label>
        <button className="vh-btn vh-btn--ghost vh-btn--sm" disabled={busy || price === '' || Number(price) === ink.unitPrice} onClick={() => void run(() => patchInk(ink.id, { unit_price: Number(price) }))}>{t('mg.save')}</button>
        <span className="vh-mono mg-stock">{t('mg.inStock', { n: ink.stock })}</span>
        <button className="vh-link" onClick={() => setStockOpen(!stockOpen)}>{t('mg.m.adjust')}</button>
        <label className="wk-check"><input type="checkbox" checked={ink.active} disabled={busy} onChange={(e) => void run(() => patchInk(ink.id, { is_active: e.target.checked }))} /> {t('mg.active')}</label>
      </div>
      {stockOpen && <StockForm busy={busy} onCancel={() => setStockOpen(false)} onSend={(s) => void run(() => stockInk(ink.id, s)).then((ok) => ok && setStockOpen(false))} />}
    </li>
  )
}

function NewPen({ c, onDone, onCancel }: { c: Ctx; onDone: (id: number) => void; onCancel: () => void }) {
  const t = useT()
  const { busy, err, run } = useRun(() => void c.reload())
  const [form, setForm] = useState({ code: '', name: '', category: 'GEL' as PenCategory, width: '0.5', target: '0.8', min: '0.5', max: '1.2', hard: '1.6', vmax: '30', surcharge: '0' })
  const [papers, setPapers] = useState<Set<number>>(new Set())
  const [inks, setInks] = useState([{ name: '', hex: '#1b2440', price: '0' }])
  const [partial, setPartial] = useState<{ id: number; name: string } | null>(null)
  const f = (k: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm({ ...form, [k]: k === 'surcharge' ? intOnly(e.target.value) : ['code', 'name', 'category'].includes(k) ? e.target.value : decOnly(e.target.value) })
  const [lo, mid, hi, max] = [Number(form.min), Number(form.target), Number(form.max), Number(form.hard)]
  const band = lo > 0 && lo < mid && mid < hi && hi < max
  const named = inks.filter((i) => i.name.trim())
  const ok = form.code && form.name && band && papers.size > 0 && named.length > 0

  const create = async () => {
    let made: AdminPen | null = null
    const done = await run(async () => {
      made = await createPen({
        code: form.code, name: form.name, category: form.category, stroke_width_mm: Number(form.width), f_target_n: Number(form.target), f_min_n: Number(form.min),
        f_max_n: Number(form.max), f_hard_n: Number(form.hard), v_max_mm_s: Number(form.vmax), surcharge: Number(form.surcharge) || 0,
      })
      for (const i of named) await createInk(made.id, { name: i.name.trim(), hex_code: i.hex, unit_price: Number(i.price) || 0 })
      for (const id of papers) await setCompat(id, made.id, true)
    })
    const m = made as AdminPen | null
    if (m && !done) setPartial({ id: m.id, name: m.name })
    else if (m) onDone(m.id)
  }

  return (
    <>
      <header className="mt-head"><h3>{t('mg.m.newPen')}</h3></header>
      <ErrorLine err={err} />
      {partial && (
        <p className="wk-warn" role="status">
          {t('mg.m.partial', { name: partial.name })} <button className="vh-link" onClick={() => onDone(partial.id)}>{t('mg.m.openIt')}</button>
        </p>
      )}
      <div className="wk-form">
        <label className="vh-label">{t('mg.code')}<input className="vh-input" value={form.code} onChange={f('code')} /></label>
        <label className="vh-label wk-grow">{t('mg.name')}<input className="vh-input" value={form.name} onChange={f('name')} /></label>
        <label className="vh-label">{t('mg.category')}
          <select className="vh-select" value={form.category} onChange={f('category')}>{PEN_CATEGORIES.map((x) => <option key={x} value={x}>{t(`pen.${x}`)}</option>)}</select>
        </label>
        <label className="vh-label">{t('mg.surcharge')}<input className="vh-input" inputMode="numeric" value={form.surcharge} onChange={f('surcharge')} /></label>
      </div>
      <details className="wk-lines">
        <summary>{t('mg.m.profile')}</summary>
        <div className="wk-form">
          <label className="vh-label">{t('mg.width')}<input className="vh-input" value={form.width} onChange={f('width')} /></label>
          <label className="vh-label">{t('mg.fMin')}<input className="vh-input" value={form.min} onChange={f('min')} /></label>
          <label className="vh-label">{t('mg.fTarget')}<input className="vh-input" value={form.target} onChange={f('target')} /></label>
          <label className="vh-label">{t('mg.fMax')}<input className="vh-input" value={form.max} onChange={f('max')} /></label>
          <label className="vh-label">{t('mg.fHard')}<input className="vh-input" value={form.hard} onChange={f('hard')} /></label>
          <label className="vh-label">{t('mg.vMax')}<input className="vh-input" value={form.vmax} onChange={f('vmax')} /></label>
        </div>
      </details>
      {!band && <p className="wk-warn">{t('mg.forceBand')}</p>}

      <div className="mt-sect">
        <h4>{t('mg.m.inksTitle')}</h4>
        {inks.map((i, n) => (
          <div key={n} className="wk-form mt-add">
            <label className="vh-label wk-grow">{t('mg.m.inkRow', { n: n + 1 })}<input className="vh-input" value={i.name} maxLength={60} onChange={(e) => setInks(inks.map((x, j) => (j === n ? { ...x, name: e.target.value } : x)))} /></label>
            <label className="vh-label">{t('mg.color')}<input className="mg-color" type="color" value={i.hex} onChange={(e) => setInks(inks.map((x, j) => (j === n ? { ...x, hex: e.target.value } : x)))} /></label>
            <label className="vh-label">{t('mg.price')}<input className="vh-input" inputMode="numeric" value={i.price} onChange={(e) => setInks(inks.map((x, j) => (j === n ? { ...x, price: intOnly(e.target.value) } : x)))} /></label>
            {inks.length > 1 && <button className="vh-btn vh-btn--ghost vh-btn--sm" onClick={() => setInks(inks.filter((_, j) => j !== n))}>{t('co.remove')}</button>}
          </div>
        ))}
        <button className="vh-btn vh-btn--ghost vh-btn--sm wk-self" onClick={() => setInks([...inks, { name: '', hex: '#1b2440', price: '0' }])}>{t('mg.m.addInkRow')}</button>
      </div>

      <div className="mt-sect">
        <h4>{t('mg.m.papersTitle')}</h4>
        <p className="sd-sub">{t('mg.m.needPaper')}</p>
        <ul className="mt-links">
          {c.papers.filter((p) => p.active).map((p) => (
            <li key={p.id}>
              <label className={`mt-link${papers.has(p.id) ? ' on' : ''}`}>
                <input type="checkbox" checked={papers.has(p.id)} onChange={(e) => setPapers(toggle(papers, p.id, e.target.checked))} />
                <span className="mt-link-main">
                  <b>{p.name}</b>
                  <small>{p.size} · {t(`surface.${p.surface}`)} · {p.gsm} gsm</small>
                </span>
              </label>
            </li>
          ))}
        </ul>
      </div>
      <div className="wk-actions">
        <button className="vh-btn vh-btn--ghost vh-btn--md" onClick={onCancel}>{t('mg.m.cancel')}</button>
        <button className="vh-btn vh-btn--primary vh-btn--md" disabled={busy || !ok || !!partial} onClick={() => void create()}>{t('mg.m.createPen')}</button>
      </div>
    </>
  )
}

const toggle = (s: Set<number>, id: number, on: boolean) => {
  const next = new Set(s)
  if (on) next.add(id)
  else next.delete(id)
  return next
}
