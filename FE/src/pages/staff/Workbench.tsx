import { useState, type ReactNode } from 'react'
import { CaretRight, MagnifyingGlass } from '@phosphor-icons/react'
import Shell from '../../components/ws/Shell'
import { useAsync } from '../../hooks/useAsync'
import { useT } from '../../i18n'
import { Link } from '../../router/router'
import { errText, orderErrorKey, type OrderStatus } from '../../services/orders'
import { allWork, type WorkOrder } from '../../services/workshop'
import { fmt } from '../../utils/format'
import OrderDetail from './OrderDetail'
import { useUser } from '../../store/store'
import { isManagerRole } from './RequireStaff'

type Scope = 'mine' | 'pool' | 'all'
type GroupId = 'intake' | 'sketch' | 'customer' | 'production' | 'closed'
type Stage = 'open' | GroupId

/** Orders by what has to happen next. Anything not listed (a draft never reaches the workshop) counts as closed. */
const GROUPS: { id: GroupId; statuses: OrderStatus[] }[] = [
  { id: 'intake', statuses: ['SUBMITTED'] },
  { id: 'sketch', statuses: ['ACCEPTED'] },
  { id: 'customer', statuses: ['NEED_INFO', 'AWAITING_PRIVACY', 'QUOTED', 'AWAITING_DEPOSIT', 'AWAITING_ACCEPTANCE', 'AWAITING_FINAL_PAYMENT'] },
  { id: 'production', statuses: ['CONFIRMED', 'READY_TO_DELIVER', 'DELIVERING'] },
  { id: 'closed', statuses: ['COMPLETED', 'CANCELLED', 'REJECTED'] },
]
const groupOf = (o: WorkOrder): GroupId => GROUPS.find((g) => g.statuses.includes(o.status))?.id ?? 'closed'
/** Rows per group in the overview, and per page of one group or a search. */
const PREVIEW = 5
const PAGE = 20
const HOUR = 3_600_000
/** An order waiting on the workshop this long is flagged. */
const LATE_MS = 48 * HOUR
const UNSCHEDULED = ['NOT_STARTED', 'PENDING_SCHEDULE', 'FAILED', 'REWRITE_REQUIRED']

/** The shipping desk reads the same orders by hand-over state instead of by next step. */
const FULFILLMENT_FILTERS: { id: string; statuses: OrderStatus[] }[] = [
  { id: 'ready', statuses: ['READY_TO_DELIVER'] },
  { id: 'delivering', statuses: ['DELIVERING'] },
  { id: 'awaiting', statuses: ['AWAITING_FINAL_PAYMENT'] },
  { id: 'completed', statuses: ['COMPLETED'] },
  { id: 'handoff', statuses: ['AWAITING_FINAL_PAYMENT', 'READY_TO_DELIVER', 'DELIVERING', 'COMPLETED'] },
]

const sentAt = (o: WorkOrder) => Date.parse(o.submittedAt ?? o.createdAt)
const waitsOnUs = (o: WorkOrder) => o.status === 'SUBMITTED' || o.status === 'ACCEPTED' || (o.status === 'CONFIRMED' && UNSCHEDULED.includes(o.production))

/** Orders on the left, grouped by the next step; the selected one on the right: intake, sketch, quotation and chat all happen here. */
export default function Workbench({ id, fulfillment = false }: { id?: number; fulfillment?: boolean }) {
  const t = useT()
  const user = useUser()
  const manager = isManagerRole(user?.apiRole)
  const [scope, setScope] = useState<Scope>(manager ? 'all' : 'mine')
  const [stage, setStage] = useState<Stage>('open')
  const [q, setQ] = useState('')
  const [limit, setLimit] = useState(PAGE)
  const [filter, setFilter] = useState('ready')
  const [closedGroups, setClosedGroups] = useState<GroupId[]>([])
  const list = useAsync(() => allWork(), [], 30000)
  const all = list.data ?? []
  const now = Date.now()

  const inScope = (o: WorkOrder, s: Scope) => (s === 'pool' ? o.assignedStaffId === null : s === 'mine' ? o.assignedStaffId === user?.id : true)
  const scoped = all.filter((o) => inScope(o, scope))
  const ofGroup = (g: GroupId) => scoped.filter((o) => groupOf(o) === g)
  // Open orders: the longest wait first. Closed ones: the newest first.
  const oldest = (a: WorkOrder, b: WorkOrder) => sentAt(a) - sentAt(b)
  const newest = (a: WorkOrder, b: WorkOrder) => sentAt(b) - sentAt(a)

  const next = (o: WorkOrder): string => {
    switch (o.status) {
      case 'SUBMITTED':
        if (manager) return t(o.assignedStaffId === null ? 'wk.next.assign' : 'wk.next.staffIntake')
        return t(o.assignedStaffId === null ? 'wk.next.claim' : 'wk.next.intake')
      case 'ACCEPTED': return t('wk.next.sketch')
      case 'CONFIRMED': return t(UNSCHEDULED.includes(o.production) ? 'wk.next.schedule' : 'wk.next.production')
      case 'NEED_INFO': case 'AWAITING_PRIVACY': case 'QUOTED': case 'AWAITING_DEPOSIT':
      case 'AWAITING_ACCEPTANCE': case 'AWAITING_FINAL_PAYMENT': case 'READY_TO_DELIVER': case 'DELIVERING':
        return t(`wk.next.${o.status}`)
      default: return t(`os.${o.status}`)
    }
  }
  const age = (o: WorkOrder) => {
    const h = Math.floor((now - sentAt(o)) / HOUR)
    return h < 1 ? t('wk.ol.justNow') : h < 24 ? t('wk.ol.hours', { n: h }) : t('wk.ol.days', { n: Math.floor(h / 24) })
  }

  const pickStage = (s: Stage) => { setStage(s); setLimit(PAGE); setQ('') }
  const more = (left: number) => <button className="ol-more" onClick={() => setLimit((n) => n + PAGE)}>{t('wk.ol.more', { n: Math.min(PAGE, left), left })}</button>

  const row = (o: WorkOrder) => {
    const late = waitsOnUs(o) && now - sentAt(o) >= LATE_MS
    const amount = o.total ?? o.estMax
    return (
      <li key={o.id}>
        <Link to={`/staff/${fulfillment ? 'fulfillment' : 'review'}/${o.id}`} className={`ol-row${o.id === id ? ' on' : ''}`} aria-current={o.id === id ? 'page' : undefined}>
          <span className="ol-row-top">
            <b>{o.code}</b>
            {o.assignedStaffId === null && <span className="ol-pool">{t('wk.unclaimed')}</span>}
            <span className={`ol-age${late ? ' late' : ''}`}>{age(o)}</span>
          </span>
          <span className="ol-row-next">
            <i className={`ol-dot g-${groupOf(o)}`} aria-hidden="true" />
            <span>{next(o)}</span>
            {amount !== null && <small>{fmt(amount)}</small>}
          </span>
          <span className="ol-row-meta">{o.customerName} · {t(`ot.${o.type}`)} × {o.quantity}</span>
        </Link>
      </li>
    )
  }

  const needle = q.trim().toLowerCase()
  let body: ReactNode
  let shown = 0
  let total = 0
  if (fulfillment && !needle) {
    const f = FULFILLMENT_FILTERS.find((x) => x.id === filter) ?? FULFILLMENT_FILTERS[0]
    const rows = all.filter((o) => f.statuses.includes(o.status)).sort(f.id === 'completed' ? newest : oldest)
    shown = Math.min(limit, rows.length)
    total = rows.length
    body = (
      <section className="ol-sec">
        <ul>{rows.slice(0, limit).map(row)}</ul>
        {rows.length > limit && more(rows.length - limit)}
        {!rows.length && <p className="ol-empty">{t('wk.ol.empty')}</p>}
      </section>
    )
  } else if (needle) {
    // Search covers every order the account can see, whatever the scope or stage.
    const hits = all.filter((o) => o.code.toLowerCase().includes(needle) || o.customerName.toLowerCase().includes(needle)).sort(newest)
    shown = Math.min(limit, hits.length)
    total = hits.length
    body = (
      <section className="ol-sec">
        <h3 className="ol-sec-head static"><span>{t('wk.ol.searchTitle')}</span><em className="ol-count">{hits.length}</em></h3>
        <ul>{hits.slice(0, limit).map(row)}</ul>
        {hits.length > limit && more(hits.length - limit)}
        {!hits.length && <p className="ol-empty">{t('wk.ol.noMatch')}</p>}
      </section>
    )
  } else if (stage === 'open') {
    body = GROUPS.filter((g) => g.id !== 'closed').map((g) => {
      const rows = ofGroup(g.id).sort(oldest)
      const open = !closedGroups.includes(g.id)
      const hidden = rows.length > PREVIEW
      if (open) shown += Math.min(PREVIEW, rows.length)
      total += rows.length
      return (
        <section key={g.id} className="ol-sec">
          <h3>
            <button className="ol-sec-head" aria-expanded={open} onClick={() => setClosedGroups((c) => (open ? [...c, g.id] : c.filter((x) => x !== g.id)))}>
              <CaretRight size={12} weight="bold" className={open ? 'open' : ''} aria-hidden="true" />
              <span>{t(`wk.ol.g.${g.id}`)}</span>
              <em className={`ol-count g-${g.id}${rows.length ? '' : ' zero'}`}>{rows.length}</em>
            </button>
          </h3>
          {open && (
            <>
              <ul>{rows.slice(0, PREVIEW).map(row)}</ul>
              {hidden && <button className="ol-more" onClick={() => pickStage(g.id)}>{t('wk.ol.seeAll', { n: rows.length })}</button>}
              {!rows.length && <p className="ol-empty">{t('wk.ol.empty')}</p>}
            </>
          )}
        </section>
      )
    })
  } else {
    const rows = ofGroup(stage).sort(stage === 'closed' ? newest : oldest)
    shown = Math.min(limit, rows.length)
    total = rows.length
    body = (
      <section className="ol-sec">
        <ul>{rows.slice(0, limit).map(row)}</ul>
        {rows.length > limit && more(rows.length - limit)}
        {!rows.length && <p className="ol-empty">{t('wk.ol.empty')}</p>}
      </section>
    )
  }

  const scopes: Scope[] = manager ? ['all', 'pool'] : ['mine', 'pool']
  const openIn = (s: Scope) => all.filter((o) => inScope(o, s) && groupOf(o) !== 'closed').length
  const stages: { id: Stage; n: number }[] = [
    { id: 'open', n: scoped.filter((o) => groupOf(o) !== 'closed').length },
    ...GROUPS.map((g) => ({ id: g.id, n: ofGroup(g.id).length })),
  ]

  return (
    <Shell
      area={manager ? 'manager' : 'staff'}
      active={fulfillment ? 'fulfillment' : 'review'}
      title={t(fulfillment ? 'sp.title' : 'wk.title')}
      lede={t(fulfillment ? 'sp.lede' : 'wk.lede')}
      tools={fulfillment &&
        <div className="wk-tabs" role="tablist" aria-label={t('wk.queue')}>
          {FULFILLMENT_FILTERS.map((x) => (
            <button key={x.id} role="tab" aria-selected={filter === x.id} className={filter === x.id ? 'on' : ''} onClick={() => { setFilter(x.id); setLimit(PAGE); setQ('') }}>{t(`sp.filter.${x.id}`)}</button>
          ))}
        </div>
      }
    >
      <div className="wk-layout">
        <aside className="ol" aria-label={t('wk.queue')}>
          <div className="ol-top">
            {!fulfillment && <div className="ol-scope" role="group" aria-label={t('wk.ol.scope')}>
              {scopes.map((s) => (
                <button key={s} aria-pressed={scope === s} className={scope === s ? 'on' : ''} onClick={() => { setScope(s); setLimit(PAGE) }}>
                  {t(`wk.ol.${s}`)} {list.data && <span>{openIn(s)}</span>}
                </button>
              ))}
            </div>}
            <label className="ol-search">
              <MagnifyingGlass size={16} aria-hidden="true" />
              <input type="search" value={q} placeholder={t('wk.search')} aria-label={t('wk.search')} onChange={(e) => { setQ(e.target.value); setLimit(PAGE) }} />
            </label>
            {!fulfillment && <div className="ol-stages" role="group" aria-label={t('wk.ol.stages')}>
              {stages.map((s) => {
                const on = !needle && stage === s.id
                return (
                  <button key={s.id} aria-pressed={on} className={on ? 'on' : ''} onClick={() => pickStage(s.id)}>
                    {t(`wk.ol.g.${s.id}`)} {list.data && <span>{s.n}</span>}
                  </button>
                )
              })}
            </div>}
          </div>
          <div className="ol-scroll">
            {!!list.error && <p className="lg-error" role="alert">{errText(t, orderErrorKey(list.error))}</p>}
            {list.loading && !list.data && <p className="sub" role="status">{t('co.loading')}</p>}
            {list.data && body}
          </div>
          {list.data && <p className="ol-foot">{t('wk.ol.showing', { n: shown, total })}</p>}
        </aside>

        <section className="wk-detail">
          {id ? <OrderDetail key={id} id={id} onChanged={() => void list.reload()} /> : <p className="sub">{t('wk.pick')}</p>}
        </section>
      </div>
    </Shell>
  )
}
