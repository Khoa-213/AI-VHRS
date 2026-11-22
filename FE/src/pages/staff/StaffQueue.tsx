import { useEffect, useRef, useState } from 'react'
import { CaretLeft, CaretRight, MagnifyingGlass, X } from '@phosphor-icons/react'
import AdminSelect from '../../components/admin/AdminSelect'
import Shell from '../../components/ws/Shell'
import { useAsync } from '../../hooks/useAsync'
import { useDebounced } from '../../hooks/useDebounced'
import { useLocale, useT } from '../../i18n'
import { Link, navigate, useSearch } from '../../router/router'
import { errText, orderErrorKey, type OrderStatus } from '../../services/orders'
import { listWork, queueCounts, type WorkOrder } from '../../services/workshop'
import { useOnNotification } from '../../store/notifications'
import OrderDetail from './OrderDetail'

const GROUPS: { id: string; statuses: OrderStatus[] }[] = [
  { id: 'intake', statuses: ['SUBMITTED'] },
  { id: 'sketch', statuses: ['ACCEPTED'] },
  { id: 'customer', statuses: ['NEED_INFO', 'AWAITING_PRIVACY', 'QUOTED', 'AWAITING_DEPOSIT', 'AWAITING_ACCEPTANCE', 'AWAITING_FINAL_PAYMENT'] },
  { id: 'production', statuses: ['CONFIRMED', 'READY_TO_DELIVER', 'DELIVERING'] },
  { id: 'closed', statuses: ['COMPLETED', 'CANCELLED', 'REJECTED'] },
]
const PAGE = 20

/** Same Staff frame and order detail, with a server-paged pool and personal workflow. */
export default function StaffQueue({ id }: { id?: number }) {
  const t = useT()
  const locale = useLocale()
  const [collapsed, setCollapsed] = useState<string[]>([])
  const search = useSearch()
  const params = new URLSearchParams(search)
  const scope = params.get('scope') === 'mine' ? 'mine' : 'pool'
  const stage = GROUPS.some((g) => g.id === params.get('stage')) ? params.get('stage')! : 'open'
  const query = params.get('q') ?? ''
  const q = useDebounced(query, 250)
  const page = Math.max(1, Math.floor(Number(params.get('page')) || 1))
  const ids = (params.get('ids') ?? '').split(',').map(Number).filter((n) => Number.isSafeInteger(n) && n > 0).slice(0, 100)
  const batch = ids.length > 0
  const statuses: OrderStatus[] = scope === 'pool' && !batch ? ['SUBMITTED'] : stage === 'open'
    ? GROUPS.filter((g) => g.id !== 'closed').flatMap((g) => g.statuses)
    : GROUPS.find((g) => g.id === stage)!.statuses
  const key = JSON.stringify([scope, stage, q, page, ids])
  const counts = useAsync(queueCounts, [], 15000)
  const list = useAsync(async () => ({ key, ...await listWork({
    unassigned: !batch && scope === 'pool', mine: !batch && scope === 'mine',
    status: batch ? undefined : q.trim() ? (scope === 'pool' ? ['SUBMITTED'] : undefined) : statuses,
    q, page, pageSize: PAGE, orderIds: batch ? ids : undefined,
  }) }), [key], 15000)
  const current = list.data?.key === key ? list.data : null
  const scroll = useRef<HTMLDivElement>(null)
  const position = useRef({ top: 0, window: 0 })
  const returnTo = `/staff/review${search}`
  const change = (values: Record<string, string | null>) => {
    const next = new URLSearchParams(search)
    next.delete('page')
    for (const [name, value] of Object.entries(values)) value === null ? next.delete(name) : next.set(name, value)
    navigate(`/staff/review${id ? `/${id}` : ''}?${next}`, { replace: !!values.q || values.q === '' })
    position.current = { top: 0, window: 0 }
  }
  const reload = () => { void list.reload(); void counts.reload(); window.dispatchEvent(new Event('staff-queue-changed')) }
  useOnNotification(reload)
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      if (id) { document.querySelector('.ws-staff>.app2')?.scrollTo({ top: 0 }); return }
      if (scroll.current) scroll.current.scrollTop = position.current.top
      document.querySelector('.ws-staff>.app2')?.scrollTo({ top: position.current.window })
    })
    return () => cancelAnimationFrame(frame)
  }, [id])
  useEffect(() => {
    if (current && page > 1 && !current.items.length) change({ page: String(Math.max(1, Math.ceil(current.total / PAGE))) })
  }, [current, page])

  const groupCount = (statuses: OrderStatus[]) => statuses.reduce((sum, s) => sum + (counts.data?.mine[s] ?? 0), 0)
  const mineOpen = groupCount(GROUPS.filter((g) => g.id !== 'closed').flatMap((g) => g.statuses))
  const now = Date.now()
  const row = (o: WorkOrder) => {
    const sent = new Date(o.submittedAt ?? o.createdAt)
    const minutes = Math.max(0, Math.floor((now - sent.getTime()) / 60000))
    const wait = minutes < 60 ? t('staff.queue.waitMinutes', { n: minutes }) : minutes < 1440
      ? t('staff.queue.waitHours', { n: Math.floor(minutes / 60) }) : t('staff.queue.waitDays', { n: Math.floor(minutes / 1440) })
    const time = sent.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' })
    const date = sent.toDateString() === new Date(now).toDateString()
      ? t('staff.queue.today', { time }) : sent.toLocaleString(locale, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
    return <li key={o.id}><Link to={`/staff/review/${o.id}${search}`} className={`ol-row${id === o.id ? ' on' : ''}`} aria-current={id === o.id ? 'page' : undefined} onClick={() => {
      position.current = { top: scroll.current?.scrollTop ?? 0, window: document.querySelector('.ws-staff>.app2')?.scrollTop ?? 0 }
    }}><span className="ol-row-top"><b>{o.code}</b></span>
      <span className="ol-row-meta">{o.customerName} · {date}</span>
      <span className={`ol-age${minutes >= 2880 ? ' late' : ''}`}>{wait}</span>
      {scope === 'mine' && <span className="ol-row-next">{t(`os.${o.status}`)}</span>}
    </Link></li>
  }
  const groups = batch || q.trim() || scope === 'pool' || stage !== 'open'
    ? [{ id: batch ? 'batch' : q.trim() ? 'searchTitle' : scope === 'pool' ? 'intake' : stage, rows: current?.items ?? [], n: current?.total ?? 0 }]
    : GROUPS.filter((g) => g.id !== 'closed' && (g.id !== 'intake' || groupCount(g.statuses) > 0)).map((g) => ({ ...g,
      rows: (current?.items ?? []).filter((o) => g.statuses.includes(o.status)), n: groupCount(g.statuses),
    }))

  return <Shell area="staff" active="review" title={t('wk.title')}>
    <div className={`wk-layout${!id ? ` staff-board${scope === 'pool' || batch || q.trim() || stage !== 'open' ? ' staff-board-single staff-intake-list' : ''}` : ''}`}>
      <aside className="ol" aria-label={t('wk.queue')}>
        <div className="ol-top">
          <div className="ol-scope" role="group" aria-label={t('wk.ol.scope')}>
            {(['pool', 'mine'] as const).map((s) => <button key={s} aria-pressed={scope === s && !batch} className={scope === s && !batch ? 'on' : ''} onClick={() => change({ scope: s, stage: null, q: null, ids: null })}>
              {t(`wk.ol.${s}`)} {counts.data && <span className="ol-scope-count">{s === 'pool' ? counts.data.pool : mineOpen}</span>}
            </button>)}
          </div>
          <label className="ol-search"><MagnifyingGlass size={16} aria-hidden /><input type="search" maxLength={100} value={query} placeholder={t('wk.search')} aria-label={t('wk.search')} onChange={(e) => change({ q: e.target.value })} />
            {query && <button type="button" className="ol-clear" aria-label={t('wk.ol.clearSearch')} onClick={() => change({ q: null })}><X size={15} aria-hidden /></button>}
          </label>
          {scope === 'mine' && !batch && <div className="ol-filter"><AdminSelect label={t('wk.ol.stages')} value={stage} onChange={(value) => change({ stage: value })} options={[
            { value: 'open', label: t('wk.ol.g.open') },
            ...GROUPS.filter((g) => g.id !== 'intake' || groupCount(g.statuses) > 0).map((g) => ({ value: g.id, label: counts.data ? `${t(`wk.ol.g.${g.id}`)} (${groupCount(g.statuses)})` : t(`wk.ol.g.${g.id}`) })),
          ]} /></div>}
        </div>
        {batch && <p className="sub">{t('staff.queue.batch', { n: ids.length })} <button className="link" onClick={() => change({ ids: null })}>{t('staff.queue.allQueue')}</button></p>}
        {!!(list.error || counts.error) && <p className="lg-error" role="alert">{errText(t, orderErrorKey(list.error || counts.error))}</p>}
        <div className="ol-scroll" ref={scroll} aria-busy={!current}>
          {!current && !list.error && <p className="sub" role="status">{t('co.loading')}</p>}
          {current && groups.map((g) => {
            const collapsible = scope === 'mine' && !batch && !q.trim()
            const open = !collapsible || !collapsed.includes(g.id)
            const heading = <><span>{g.id === 'batch' ? t('staff.queue.batchTitle') : t(`wk.ol.${g.id === 'searchTitle' ? g.id : `g.${g.id}`}`)}</span><em className="ol-count">{counts.data || batch || q.trim() || scope === 'pool' || stage !== 'open' ? g.n : '…'}</em></>
            return <section className="ol-sec" key={g.id}>
              <h3>{collapsible ? <button type="button" className="ol-sec-head" aria-expanded={open} aria-controls={`staff-queue-${g.id}`} onClick={() => setCollapsed((ids) => open ? [...ids, g.id] : ids.filter((value) => value !== g.id))}>
                <CaretRight size={12} weight="bold" className={open ? 'open' : ''} aria-hidden />{heading}
              </button> : <span className="ol-sec-head static">{heading}</span>}</h3>
            <div id={`staff-queue-${g.id}`} hidden={!open}>
            <ul>{g.rows.map(row)}</ul>
            {!g.rows.length && <p className="ol-empty">{t(g.n ? 'staff.queue.otherPage' : 'wk.ol.empty')}</p>}
            {scope === 'mine' && !batch && !q.trim() && stage === 'open' && g.rows.length < g.n && <button className="ol-more" onClick={() => change({ stage: g.id })}>{t('wk.ol.seeAll', { n: g.n })}</button>}
            </div>
          </section>
          })}
        </div>
        {current && <div className="ol-foot staff-queue-pages"><span>{t('staff.queue.page', { page, pages: Math.max(1, Math.ceil(current.total / PAGE)), total: current.total })}</span><div>
          <button className="ol-more" aria-label={t('staff.queue.prev')} disabled={page <= 1} onClick={() => change({ page: String(page - 1) })}><CaretLeft size={16} aria-hidden /></button>
          <button className="ol-more" aria-label={t('staff.queue.next')} disabled={page * PAGE >= current.total} onClick={() => change({ page: String(page + 1) })}><CaretRight size={16} aria-hidden /></button>
        </div></div>}
      </aside>
      <section className="wk-detail">{id && <OrderDetail key={id} id={id} onChanged={reload} returnTo={returnTo} />}</section>
    </div>
  </Shell>
}
