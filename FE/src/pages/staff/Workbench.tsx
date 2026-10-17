import { useState } from 'react'
import Shell from '../../components/ws/Shell'
import { STATUS_COLOR } from '../../constants/orderStatus'
import { useAsync } from '../../hooks/useAsync'
import { useDebounced } from '../../hooks/useDebounced'
import { useT } from '../../i18n'
import { Link } from '../../router/router'
import { errText, orderErrorKey, type OrderStatus } from '../../services/orders'
import { listWork } from '../../services/workshop'
import { fmt } from '../../utils/format'
import OrderDetail from './OrderDetail'
import { useUser } from '../../store/store'
import { isManagerRole } from './RequireStaff'

const FILTERS: { id: string; statuses?: OrderStatus[] }[] = [
  { id: 'todo', statuses: ['SUBMITTED', 'ACCEPTED'] },
  { id: 'customer', statuses: ['NEED_INFO', 'AWAITING_PRIVACY', 'QUOTED', 'AWAITING_DEPOSIT'] },
  { id: 'production', statuses: ['CONFIRMED', 'AWAITING_ACCEPTANCE', 'AWAITING_FINAL_PAYMENT', 'READY_TO_DELIVER', 'DELIVERING'] },
  { id: 'all' },
]

/** Orders on the left, the selected one on the right: intake, sketch, quotation and chat all happen here. */
export default function Workbench({ id }: { id?: number }) {
  const t = useT()
  const user = useUser()
  const [filter, setFilter] = useState('todo')
  const [q, setQ] = useState('')
  const [type, setType] = useState('')
  const [pool, setPool] = useState(false)
  const dq = useDebounced(q, 400)
  const f = FILTERS.find((x) => x.id === filter) ?? FILTERS[0]
  const list = useAsync(() => listWork({ status: f.statuses, q: dq, orderType: type || undefined, unassigned: pool, pageSize: 50 }), [filter, dq, type, pool], 30000)
  const rows = list.data?.items ?? []

  return (
    <Shell
      area={isManagerRole(user?.apiRole) ? 'manager' : 'staff'}
      active="review"
      title={t('wk.title')}
      lede={t('wk.lede')}
      tools={
        <div className="seg" role="tablist" aria-label={t('wk.queue')}>
          {FILTERS.map((x) => (
            <button key={x.id} role="tab" aria-selected={filter === x.id} className={filter === x.id ? 'on' : ''} onClick={() => setFilter(x.id)}>{t(`wk.filter.${x.id}`)}</button>
          ))}
        </div>
      }
    >
      <div className="wk-layout">
        <aside className="wk-list" aria-label={t('wk.queue')}>
          <input className="vh-input wk-search" type="search" value={q} placeholder={t('wk.search')} aria-label={t('wk.search')} onChange={(e) => setQ(e.target.value)} />
          <div className="wk-filters">
            <select className="vh-select" aria-label={t('wk.typeFilter')} value={type} onChange={(e) => setType(e.target.value)}>
              <option value="">{t('wk.typeAll')}</option>
              {(['OT1_COPY_RESTORE', 'OT3_TEMPLATE'] as const).map((x) => <option key={x} value={x}>{t(`ot.${x}`)}</option>)}
            </select>
            <label className="wk-check"><input type="checkbox" checked={pool} onChange={(e) => setPool(e.target.checked)} /> {t('wk.poolOnly')}</label>
          </div>
          {!!list.error && <p className="lg-error" role="alert">{errText(t, orderErrorKey(list.error))}</p>}
          {list.loading && !list.data && <p className="sub" role="status">{t('co.loading')}</p>}
          <ul>
            {rows.map((o) => (
              <li key={o.id}>
                <Link to={`/staff/review/${o.id}`} className={`wk-item${o.id === id ? ' on' : ''}`} aria-current={o.id === id ? 'page' : undefined}>
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
        </aside>

        <section className="wk-detail">
          {id ? <OrderDetail key={id} id={id} onChanged={() => void list.reload()} /> : <p className="sub">{t('wk.pick')}</p>}
        </section>
      </div>
    </Shell>
  )
}
