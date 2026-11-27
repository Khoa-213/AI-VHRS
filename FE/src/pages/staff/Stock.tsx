import { Plus, Trash, Warning } from '@phosphor-icons/react'
import { useMemo, useState } from 'react'
import { useAsync } from '../../hooks/useAsync'
import { useLocale, useT } from '../../i18n'
import {
  createReceipt, setMinQty, stockMoves, stockOverview,
  type ItemKind, type MoveKind, type Receipt, type StockItem,
} from '../../services/manage'
import { orderErrorKey } from '../../services/orders'
import { ErrorLine, intOnly, useRun } from './catalogKit'

/*
 * Stock in and out (migration 0033). The Manager receives goods on one receipt with several lines and sets a minimum
 * level per item; the technician takes a job's paper in the desktop app (Prepare step) and the unused sheets come back
 * at Writing done. Every change is one row of the ledger, so the "Sổ kho" view adds up to the levels shown here.
 */

type View = 'levels' | 'ledger'
type LevelFilter = 'all' | ItemKind | 'attention'
const KINDS: ItemKind[] = ['PAPER', 'PEN', 'INK']
const MOVES: MoveKind[] = ['RECEIPT', 'ISSUE', 'RETURN', 'ADJUST']

const newRef = () => (typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `r${Date.now()}${Math.random().toString(36).slice(2)}`)
const key = (i: { kind: ItemKind; id: number }) => `${i.kind}:${i.id}`

export default function Stock() {
  const t = useT()
  const items = useAsync(stockOverview, [])
  const [view, setView] = useState<View>('levels')
  const [receipt, setReceipt] = useState<{ ref: string; first: string[] } | null>(null)
  const [saved, setSaved] = useState<Receipt | null>(null)
  const [ledgerTick, setLedgerTick] = useState(0)

  const open = (first: string[] = []) => {
    setSaved(null)
    setReceipt({ ref: newRef(), first })
  }

  return (
    <section className="wk-block sk">
      <div className="mg-row">
        <div className="mt-seg" role="tablist" aria-label={t('mg.tab.stock')}>
          {(['levels', 'ledger'] as const).map((v) => (
            <button key={v} role="tab" aria-selected={view === v} className={view === v ? 'on' : ''} onClick={() => setView(v)}>{t(`mg.sk.view.${v}`)}</button>
          ))}
        </div>
        <span className="wk-grow" />
        {!receipt && (
          <button className="vh-btn vh-btn--primary vh-btn--sm" onClick={() => open()}>
            <Plus size={14} weight="bold" aria-hidden />{t('mg.sk.newReceipt')}
          </button>
        )}
      </div>

      {saved && (
        <p className="note-ok" role="status">
          {t(saved.created ? 'mg.sk.saved' : 'mg.sk.savedAgain', { code: saved.code ?? `#${saved.id}`, n: saved.lines.length })}
        </p>
      )}
      {receipt && (
        <ReceiptForm
          key={receipt.ref}
          clientRef={receipt.ref}
          first={receipt.first}
          items={items.data ?? []}
          onCancel={() => setReceipt(null)}
          onSaved={(r) => {
            setSaved(r)
            setReceipt(null)
            setLedgerTick((x) => x + 1)
            void items.reload()
          }}
        />
      )}

      {view === 'levels'
        ? <Levels items={items.data ?? undefined} error={items.error} reload={() => void items.reload()} onReceive={(k) => open([k])} />
        : <Ledger key={ledgerTick} />}
    </section>
  )
}

// ---------- levels ----------

function Levels({ items, error, reload, onReceive }: { items: StockItem[] | undefined; error: unknown; reload: () => void; onReceive: (key: string) => void }) {
  const t = useT()
  const [filter, setFilter] = useState<LevelFilter>('all')
  const [mins, setMins] = useState<Record<string, string>>({})
  const { busy, err, run } = useRun(reload)
  const all = items ?? []
  const attention = all.filter((i) => i.active && i.status !== 'OK').length
  const rows = all.filter((i) => (filter === 'all' ? true : filter === 'attention' ? i.active && i.status !== 'OK' : i.kind === filter))

  const saveMin = (i: StockItem) => {
    const v = mins[key(i)]
    if (v === undefined || v === '' || Number(v) === i.min) return
    void run(() => setMinQty(i.kind, i.id, Number(v))).then((ok) => ok && setMins((m) => {
      const n = { ...m }
      delete n[key(i)]
      return n
    }))
  }

  return (
    <>
      <div className="mt-filters" role="group" aria-label={t('mg.m.filter')}>
        {(['all', ...KINDS, 'attention'] as const).map((f) => (
          <button key={f} aria-pressed={filter === f} className={filter === f ? 'on' : ''} onClick={() => setFilter(f)}>
            {t(`mg.sk.f.${f}`)}{f === 'attention' && attention > 0 ? ` · ${attention}` : ''}
          </button>
        ))}
      </div>
      <ErrorLine err={err || (error ? orderErrorKey(error) : '')} />
      {!items && !error && <p className="sd-sub" role="status">{t('co.loading')}</p>}
      <p className="sd-sub">{t('mg.sk.levelsHint')}</p>
      <div className="mgr-table-wrap">
        <table className="mgr-table">
          <thead>
            <tr>
              <th scope="col">{t('mg.sk.item')}</th>
              <th scope="col" className="num">{t('mg.sk.stock')}</th>
              <th scope="col" className="num">{t('mg.sk.kept')}</th>
              <th scope="col" className="num">{t('mg.sk.free')}</th>
              <th scope="col" className="num">{t('mg.sk.min')}</th>
              <th scope="col">{t('mg.sk.status')}</th>
              <th scope="col"><span className="staff-sr">{t('mg.sk.receive')}</span></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((i) => (
              <tr key={key(i)} style={i.active ? undefined : { opacity: 0.55 }}>
                <th scope="row">
                  <span className="mg-name">
                    <b>
                      {i.kind === 'INK' && i.hex && <span aria-hidden style={{ display: 'inline-block', width: 10, height: 10, borderRadius: 5, background: i.hex, marginRight: 6, boxShadow: 'inset 0 0 0 1px rgba(0,0,0,.2)' }} />}
                      {i.name}
                    </b>
                    <small>{t(`mg.sk.k.${i.kind}`)}{i.spec ? ` · ${i.spec}` : ''}{i.active ? '' : ` · ${t('mg.m.f.off')}`}</small>
                  </span>
                </th>
                <td className="num"><b>{i.stock}</b> {t(`mg.sk.u.${i.kind}`)}</td>
                <td className="num">{i.kind === 'PAPER' ? i.kept : '–'}</td>
                <td className="num">{i.kind === 'PAPER' ? i.free : '–'}</td>
                <td className="num">
                  <input
                    className="vh-input"
                    style={{ width: 72, height: 32, textAlign: 'right' }}
                    inputMode="numeric"
                    aria-label={t('mg.sk.minOf', { name: i.name })}
                    value={mins[key(i)] ?? String(i.min)}
                    disabled={busy}
                    onChange={(e) => setMins({ ...mins, [key(i)]: intOnly(e.target.value) })}
                    onBlur={() => saveMin(i)}
                    onKeyDown={(e) => e.key === 'Enter' && saveMin(i)}
                  />
                </td>
                <td>
                  {i.status === 'OK'
                    ? <span className="mt-tag">{t('mg.sk.s.OK')}</span>
                    : <span className="mt-flag"><Warning size={12} weight="bold" aria-hidden />{t(`mg.sk.s.${i.status}`)}</span>}
                </td>
                <td className="num">
                  <button className="vh-btn vh-btn--ghost vh-btn--sm" onClick={() => onReceive(key(i))} aria-label={t('mg.sk.receiveOf', { name: i.name })}>{t('mg.sk.receive')}</button>
                </td>
              </tr>
            ))}
            {items && !rows.length && <tr><td colSpan={7} className="sd-sub">{t('mg.m.empty')}</td></tr>}
          </tbody>
        </table>
      </div>
    </>
  )
}

// ---------- the receipt ----------

interface Line { pick: string; qty: string }

function ReceiptForm({ clientRef, first, items, onCancel, onSaved }: {
  clientRef: string; first: string[]; items: StockItem[]; onCancel: () => void; onSaved: (r: Receipt) => void
}) {
  const t = useT()
  const [supplier, setSupplier] = useState('')
  const [date, setDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [note, setNote] = useState('')
  const [lines, setLines] = useState<Line[]>(() => (first.length ? first : ['']).map((pick) => ({ pick, qty: '' })))
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const byKey = useMemo(() => new Map(items.map((i) => [key(i), i])), [items])
  const active = items.filter((i) => i.active)

  const picked = lines.map((l) => l.pick).filter(Boolean)
  const dup = picked.length !== new Set(picked).size
  const filled = lines.filter((l) => l.pick && Number(l.qty) > 0)
  const ok = filled.length > 0 && filled.length === lines.filter((l) => l.pick || l.qty).length && !dup && !busy

  const set = (i: number, patch: Partial<Line>) => setLines(lines.map((l, j) => (j === i ? { ...l, ...patch } : l)))
  const save = async () => {
    setBusy(true)
    setErr('')
    try {
      onSaved(await createReceipt({
        supplier: supplier.trim() || null, received_on: date || null, note: note.trim() || null, client_ref: clientRef,
        lines: filled.map((l) => {
          const [kind, id] = l.pick.split(':')
          return { item_kind: kind as ItemKind, item_id: Number(id), quantity: Number(l.qty) }
        }),
      }))
    } catch (e) {
      setErr(orderErrorKey(e))     // the same clientRef stays: sending again cannot add the goods twice
    } finally {
      setBusy(false)
    }
  }

  return (
    <ul className="mg-rows" aria-label={t('mg.sk.newReceipt')}>
      <li>
        <b>{t('mg.sk.newReceipt')}</b>
        <div className="wk-form">
          <label className="vh-label wk-grow">{t('mg.sk.supplier')}<input className="vh-input" value={supplier} maxLength={200} onChange={(e) => setSupplier(e.target.value)} /></label>
          <label className="vh-label">{t('mg.sk.date')}<input className="vh-input" type="date" value={date} onChange={(e) => setDate(e.target.value)} /></label>
        </div>
        {lines.map((l, i) => {
          const it = byKey.get(l.pick)
          const isDup = !!l.pick && picked.indexOf(l.pick) !== picked.lastIndexOf(l.pick)
          return (
            <div key={i} className="wk-form">
              <label className="vh-label wk-grow">
                {t('mg.sk.item')}
                <select className="vh-select" value={l.pick} onChange={(e) => set(i, { pick: e.target.value })} aria-invalid={isDup || undefined}>
                  <option value="">{t('mg.sk.pick')}</option>
                  {KINDS.map((k) => (
                    <optgroup key={k} label={t(`mg.sk.k.${k}`)}>
                      {active.filter((x) => x.kind === k).map((x) => <option key={key(x)} value={key(x)}>{x.name}{x.spec ? ` · ${x.spec}` : ''}</option>)}
                    </optgroup>
                  ))}
                </select>
              </label>
              <label className="vh-label">
                {t('mg.sk.qty')}{it ? ` (${t(`mg.sk.u.${it.kind}`)})` : ''}
                <input className="vh-input" inputMode="numeric" style={{ width: 110 }} value={l.qty} onChange={(e) => set(i, { qty: intOnly(e.target.value) })} />
              </label>
              <span className="sd-sub" style={{ minWidth: 120 }}>
                {it ? t('mg.sk.after', { to: it.stock + (Number(l.qty) || 0), unit: t(`mg.sk.u.${it.kind}`) }) : ''}
              </span>
              <button className="vh-btn vh-btn--ghost vh-btn--sm" disabled={lines.length === 1} aria-label={t('co.remove')} onClick={() => setLines(lines.filter((_, j) => j !== i))}>
                <Trash size={14} aria-hidden />
              </button>
              {isDup && <span className="lg-error" role="alert">{t('mg.sk.dup')}</span>}
            </div>
          )
        })}
        <button className="vh-btn vh-btn--ghost vh-btn--sm wk-self" onClick={() => setLines([...lines, { pick: '', qty: '' }])}>
          <Plus size={14} aria-hidden />{t('mg.sk.addLine')}
        </button>
        <label className="vh-label">{t('mg.sk.note')}<input className="vh-input" value={note} maxLength={1000} onChange={(e) => setNote(e.target.value)} /></label>
        <ErrorLine err={err} />
        <div className="mg-row">
          <span className="sd-sub wk-grow">{t('mg.sk.summary', { n: filled.length })}</span>
          <button className="vh-btn vh-btn--ghost vh-btn--sm" onClick={onCancel} disabled={busy}>{t('mg.sk.cancel')}</button>
          <button className="vh-btn vh-btn--primary vh-btn--sm" disabled={!ok} onClick={() => void save()}>{t(busy ? 'mg.sk.saving' : 'mg.sk.save')}</button>
        </div>
      </li>
    </ul>
  )
}

// ---------- the ledger ----------

const PAGE = 50

function Ledger() {
  const t = useT()
  const locale = useLocale()
  const [kind, setKind] = useState<MoveKind | undefined>()
  const [itemKind, setItemKind] = useState<ItemKind | undefined>()
  const [page, setPage] = useState(1)
  const list = useAsync(() => stockMoves({ kind, item_kind: itemKind, page, page_size: PAGE }), [kind, itemKind, page])
  const pages = list.data ? Math.max(1, Math.ceil(list.data.total / PAGE)) : 1
  return (
    <>
      <div className="mt-filters" role="group" aria-label={t('mg.sk.moveKind')}>
        <button aria-pressed={!kind} className={!kind ? 'on' : ''} onClick={() => { setKind(undefined); setPage(1) }}>{t('mg.sk.f.all')}</button>
        {MOVES.map((m) => (
          <button key={m} aria-pressed={kind === m} className={kind === m ? 'on' : ''} onClick={() => { setKind(m); setPage(1) }}>{t(`mg.sk.m.${m}`)}</button>
        ))}
        <span style={{ width: 12 }} />
        {KINDS.map((k) => (
          <button key={k} aria-pressed={itemKind === k} className={itemKind === k ? 'on' : ''} onClick={() => { setItemKind(itemKind === k ? undefined : k); setPage(1) }}>{t(`mg.sk.k.${k}`)}</button>
        ))}
      </div>
      <ErrorLine err={list.error ? orderErrorKey(list.error) : ''} />
      {!list.data && !list.error && <p className="sd-sub" role="status">{t('co.loading')}</p>}
      <div className="mgr-table-wrap">
        <table className="mgr-table">
          <thead>
            <tr>
              <th scope="col">{t('mg.sk.when')}</th>
              <th scope="col">{t('mg.sk.moveKind')}</th>
              <th scope="col">{t('mg.sk.item')}</th>
              <th scope="col" className="num">{t('mg.sk.qty')}</th>
              <th scope="col" className="num">{t('mg.sk.afterCol')}</th>
              <th scope="col">{t('mg.sk.doc')}</th>
              <th scope="col">{t('mg.sk.by')}</th>
              <th scope="col">{t('mg.sk.reason')}</th>
            </tr>
          </thead>
          <tbody>
            {(list.data?.items ?? []).map((m) => (
              <tr key={m.id}>
                <td>{new Date(m.at).toLocaleString(locale, { dateStyle: 'short', timeStyle: 'short' })}</td>
                <td>{t(`mg.sk.m.${m.kind}`)}</td>
                <th scope="row">{m.itemName}</th>
                <td className="num">
                  {m.quantity > 0 ? `+${m.quantity}` : m.quantity} {t(`mg.sk.u.${m.itemKind}`)}
                </td>
                <td className="num">{m.after}{m.shortfall > 0 && <span className="mt-flag" title={t('mg.sk.shortfall', { n: m.shortfall })}> −{m.shortfall}</span>}</td>
                <td>{m.receiptCode ?? (m.jobId ? `Job #${m.jobId}` : '–')}</td>
                <td>{m.actor ?? '–'}</td>
                <td>{m.reason ?? '–'}</td>
              </tr>
            ))}
            {list.data && !list.data.items.length && <tr><td colSpan={8} className="sd-sub">{t('mg.sk.noMoves')}</td></tr>}
          </tbody>
        </table>
      </div>
      {pages > 1 && (
        <div className="mg-row">
          <button className="vh-btn vh-btn--ghost vh-btn--sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>{t('mg.sk.prev')}</button>
          <span className="sd-sub">{t('mg.sk.page', { n: page, of: pages })}</span>
          <button className="vh-btn vh-btn--ghost vh-btn--sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>{t('mg.sk.next')}</button>
        </div>
      )}
    </>
  )
}
