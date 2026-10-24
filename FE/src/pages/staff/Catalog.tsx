import { useState } from 'react'
import Shell from '../../components/ws/Shell'
import { useAsync } from '../../hooks/useAsync'
import { useLocale, useT } from '../../i18n'
import {
  PEN_CATEGORIES, TEMPLATE_KINDS, adminRobots, adminStyles, adminTemplates, approveStyle, createRobot, createTemplate, patchRobot,
  patchTemplate, priceVersions, rejectStyle, savePrice,
  type AdminRobot, type PenCategory, type PriceList,
} from '../../services/manage'
import { orderErrorKey } from '../../services/orders'
import { fmt } from '../../utils/format'
import { ErrorLine, decOnly, intOnly, useRun } from './catalogKit'
import Materials from './Materials'

const TABS = ['materials', 'templates', 'styles', 'robots'] as const
type Tab = (typeof TABS)[number]

/** Manager only: the catalog the customer chooses from, its stock, the writing templates, the robots and the price list. */
export default function Catalog() {
  const t = useT()
  const [tab, setTab] = useState<Tab>('materials')
  return (
    <Shell area="manager" active="catalog" title={t('mg.title')} lede={t('mg.lede')}>
      <div className="wk-page mg">
        <div className="wk-tabs" role="tablist">
          {TABS.map((x) => (
            <button key={x} role="tab" aria-selected={tab === x} className={tab === x ? 'on' : ''} onClick={() => setTab(x)}>{t(`mg.tab.${x}`)}</button>
          ))}
        </div>
        {tab === 'materials' && <Materials />}
        {tab === 'templates' && <Templates />}
        {tab === 'styles' && <Styles />}
        {tab === 'robots' && <Robots />}
      </div>
    </Shell>
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

export function PricingPanel() {
  const t = useT()
  const locale = useLocale()
  const list = useAsync(priceVersions, [])
  const [edit, setEdit] = useState<Record<string, string>>({})
  const [note, setNote] = useState('')
  const { busy, err, run } = useRun(() => {
    setEdit({})
    setNote('')
    void list.reload()
  })
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
