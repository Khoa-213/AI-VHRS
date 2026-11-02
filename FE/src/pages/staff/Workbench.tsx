import { useState } from 'react'
import Shell from '../../components/ws/Shell'
import { STATUS_COLOR } from '../../constants/orderStatus'
import { useAsync } from '../../hooks/useAsync'
import { useDebounced } from '../../hooks/useDebounced'
import { useT } from '../../i18n'
import { Link } from '../../router/router'
import { errText, orderErrorKey, type OrderStatus } from '../../services/orders'
import { allWork, listWork } from '../../services/workshop'
import { fmt } from '../../utils/format'
import OrderDetail from './OrderDetail'
import { useUser } from '../../store/store'
import { isManagerRole } from './RequireStaff'

/** Orders on the left, the selected one on the right: intake, sketch, quotation and chat all happen here. */
export default function Workbench({ id, fulfillment = false }: { id?: number; fulfillment?: boolean }) {
  const t = useT()
  const user = useUser()
  const [filter, setFilter] = useState('ready')
  const [page, setPage] = useState(1)
  const filters: { id: string; statuses: OrderStatus[] }[] = [
    { id: 'ready', statuses: ['READY_TO_DELIVER'] },
    { id: 'delivering', statuses: ['DELIVERING'] },
    { id: 'awaiting', statuses: ['AWAITING_FINAL_PAYMENT'] },
    { id: 'completed', statuses: ['COMPLETED'] },
    { id: 'handoff', statuses: ['AWAITING_FINAL_PAYMENT', 'READY_TO_DELIVER', 'DELIVERING', 'COMPLETED'] },
  ]
  const [q, setQ] = useState('')
  const [type, setType] = useState('')
  const [pool, setPool] = useState(false)
  const dq = useDebounced(q, 400)
  const f = filters.find((x) => x.id === filter) ?? filters[0]
  const list = useAsync(async () => {
    const query = { q: dq, orderType: type || undefined, unassigned: pool }
    if (fulfillment) return listWork({ ...query, status: f.statuses, page, pageSize: 50 })
    const items = await allWork(query)
    return { items, total: items.length, page: 1, pageSize: items.length }
  }, [fulfillment, filter, dq, type, pool, page], 30000)
  const rows = list.data?.items ?? []

  return (
    <Shell
      area={isManagerRole(user?.apiRole) ? 'manager' : 'staff'}
      active={fulfillment ? 'fulfillment' : 'review'}
      title={t(fulfillment ? 'sp.title' : 'wk.title')}
      lede={t(fulfillment ? 'sp.lede' : 'wk.lede')}
      tools={fulfillment &&
        <div className="wk-tabs" role="tablist" aria-label={t('wk.queue')}>
          {filters.map((x) => (
            <button key={x.id} role="tab" aria-selected={filter === x.id} className={filter === x.id ? 'on' : ''} onClick={() => { setFilter(x.id); setPage(1) }}>{t(`sp.filter.${x.id}`)}</button>
          ))}
        </div>
      }
    >
      <div className="wk-layout">
        <aside className="wk-list" aria-label={t('wk.queue')}>
          <input className="vh-input wk-search" type="search" value={q} placeholder={t('wk.search')} aria-label={t('wk.search')} onChange={(e) => { setQ(e.target.value); setPage(1) }} />
          <div className="wk-filters">
            <select className="vh-select" aria-label={t('wk.typeFilter')} value={type} onChange={(e) => { setType(e.target.value); setPage(1) }}>
              <option value="">{t('wk.typeAll')}</option>
              {(['OT1_COPY_RESTORE', 'OT3_TEMPLATE'] as const).map((x) => <option key={x} value={x}>{t(`ot.${x}`)}</option>)}
            </select>
            <label className="wk-check" hidden={fulfillment}><input type="checkbox" checked={pool} onChange={(e) => { setPool(e.target.checked); setPage(1) }} /> {t('wk.poolOnly')}</label>
          </div>
          {!!list.error && <p className="lg-error" role="alert">{errText(t, orderErrorKey(list.error))}</p>}
          {list.loading && !list.data && <p className="sub" role="status">{t('co.loading')}</p>}
          <ul>
            {rows.map((o) => (
              <li key={o.id}>
                <Link to={`/staff/${fulfillment ? 'fulfillment' : 'review'}/${o.id}`} className={`wk-item${o.id === id ? ' on' : ''}`} aria-current={o.id === id ? 'page' : undefined}>
                  <span className="wk-item-main">
                    <b>{o.code}</b>
                    <span>{o.customerName} · {t(`ot.${o.type}`)} × {o.quantity}</span>
                  </span>
                  <span className="wk-item-side">
                    <span className="chip mute" style={{ color: STATUS_COLOR[o.status] }}>{t(`os.${o.status}`)}</span>
                    <span className="mono">{o.total !== null ? fmt(o.total) : o.estMax !== null ? fmt(o.estMax) : ''}</span>
                  </span>
                </Link>
              </li>
            ))}
            {list.data && !rows.length && <li className="sub">{t('sd.nothing')}</li>}
          </ul>
          {fulfillment && list.data && <div className="wk-actions">
            <button type="button" className="vh-btn vh-btn--ghost vh-btn--sm" disabled={page <= 1 || list.loading} onClick={() => setPage(page - 1)}>{t('sp.prev')}</button>
            <span className="sd-sub">{t('sp.page', { page, total: Math.max(1, Math.ceil(list.data.total / 50)) })}</span>
            <button type="button" className="vh-btn vh-btn--ghost vh-btn--sm" disabled={page * 50 >= list.data.total || list.loading} onClick={() => setPage(page + 1)}>{t('sp.next')}</button>
          </div>}
        </aside>

        <section className="wk-detail">
          {id ? <OrderDetail key={id} id={id} onChanged={() => void list.reload()} /> : <p className="sub">{t('wk.pick')}</p>}
        </section>
      </div>
    </Shell>
  )
}
