import { ArrowRight, CalendarCheck, ClipboardText, PencilSimple, SquaresFour, Truck } from '@phosphor-icons/react'
import { useState } from 'react'
import { Donut } from '../../components/ws/charts'
import { Kpi, avatarTone, initials } from '../../components/ws/parts'
import Shell from '../../components/ws/Shell'
import { STATUS_COLOR } from '../../constants/orderStatus'
import { useAsync } from '../../hooks/useAsync'
import { useLocale, useT } from '../../i18n'
import { Link } from '../../router/router'
import { errText, orderErrorKey, type OrderStatus } from '../../services/orders'
import { allWork, type WorkOrder } from '../../services/workshop'
import { useUser } from '../../store/store'
import { fmt } from '../../utils/format'

/** Orders grouped by what the workshop has to do next. */
export const GROUPS: { id: string; statuses: OrderStatus[] }[] = [
  { id: 'intake', statuses: ['SUBMITTED'] },
  { id: 'sketch', statuses: ['ACCEPTED'] },
  { id: 'customer', statuses: ['NEED_INFO', 'AWAITING_PRIVACY', 'QUOTED', 'AWAITING_DEPOSIT'] },
  { id: 'production', statuses: ['CONFIRMED', 'AWAITING_ACCEPTANCE', 'AWAITING_FINAL_PAYMENT', 'READY_TO_DELIVER', 'DELIVERING'] },
]
export const OPEN: OrderStatus[] = GROUPS.flatMap((g) => g.statuses)
const SLICE_COLORS = ['var(--acc)', 'var(--staff-series-2)', 'var(--staff-series-3)', 'var(--staff-series-4)']

/** Orders submitted on each of the last seven days, oldest first. */
export function lastSevenDays(orders: WorkOrder[], locale: string) {
  const days = Array.from({ length: 7 }, (_, i) => {
    const d = new Date()
    d.setHours(0, 0, 0, 0)
    d.setDate(d.getDate() - (6 - i))
    return d
  })
  const key = (d: Date) => d.toDateString()
  const counts = days.map((d) => orders.filter((o) => o.submittedAt && key(new Date(o.submittedAt)) === key(d)).length)
  return { counts, labels: days.map((d) => d.toLocaleDateString(locale, { weekday: 'short' })), days }
}

export function OrderRow({ order: o, mine }: { order: WorkOrder; mine: boolean }) {
  const t = useT()
  return (
    <Link to={`/staff/review/${o.id}`} className="item">
      <span className={`avatar ${avatarTone(o.customerName)}`}>{initials(o.customerName)}</span>
      <div className="t">
        <b>{t(`ot.${o.type}`)} × {o.quantity}</b>
        <span>{o.code} · {o.customerName}{o.assignedStaffId === null && o.status === 'SUBMITTED' ? ` · ${t('wk.unclaimed')}` : mine ? ` · ${t('wk.mine')}` : ''}</span>
      </div>
      <span className="chip mute" style={{ color: STATUS_COLOR[o.status] }}>{t(`os.${o.status}`)}</span>
      <span className="amt mono">{o.total !== null ? fmt(o.total) : o.estMax !== null ? fmt(o.estMax) : ''}</span>
    </Link>
  )
}

export default function StaffDashboard() {
  const t = useT()
  const locale = useLocale()
  const user = useUser()
  const [period, setPeriod] = useState<7 | 30>(7)
  const list = useAsync(() => allWork(), [], 30000)
  const orders = list.data ?? []
  const mineId = user?.id
  const count = (...s: OrderStatus[]) => orders.filter((o) => s.includes(o.status)).length
  const days = Array.from({ length: period }, (_, i) => {
    const date = new Date()
    date.setHours(0, 0, 0, 0)
    date.setDate(date.getDate() - (period - 1 - i))
    return date
  })
  const counts = days.map((date) => orders.filter((o) => o.submittedAt && new Date(o.submittedAt).toDateString() === date.toDateString()).length)
  const received = counts.reduce((sum, n) => sum + n, 0)
  const ceiling = Math.max(2, Math.ceil(Math.max(0, ...counts) / 2) * 2)
  const ticks = days.map((date, i) => ({ date, i })).filter(({ i }) => i % Math.ceil(period / 7) === 0 || i === period - 1)
  const points = counts.map((value, i) => `${40 + i * 640 / (period - 1)},${194 - value / ceiling * 148}`)
  const line = `M${points.join(' L')}`
  const todo = orders.filter((o) => o.status === 'SUBMITTED' || o.status === 'ACCEPTED').slice(0, 5)
  const sketch = orders.filter((o) => o.status === 'ACCEPTED').slice(0, 4)
  const icon = (I: typeof SquaresFour) => <I size={20} aria-hidden />

  return (
    <Shell area="staff" active="dashboard" title={t('rail.dashboard')} tools={<Link to="/staff/review" className="staff-primary-link">{t('rail.review')}<ArrowRight size={17} aria-hidden /></Link>}>
      {!!list.error && <p className="lg-error" role="alert">{errText(t, orderErrorKey(list.error))}</p>}
      {list.loading && !list.data && <p className="sub" role="status">{t('co.loading')}</p>}

      <div className="row4 staff-kpis">
        <Kpi actionIcon={<ArrowRight size={16} aria-hidden />} icon={icon(ClipboardText)} tone="a" title={t('wk.kpi.intake')} value={count('SUBMITTED')} to="/staff/review" />
        <Kpi actionIcon={<ArrowRight size={16} aria-hidden />} icon={icon(PencilSimple)} tone="p" title={t('wk.kpi.sketch')} value={count('ACCEPTED')} to="/staff/review" />
        <Kpi actionIcon={<ArrowRight size={16} aria-hidden />} icon={icon(CalendarCheck)} tone="b" title={t('wk.kpi.production')} value={count('CONFIRMED')} to="/staff/review" />
        <Kpi actionIcon={<ArrowRight size={16} aria-hidden />} icon={icon(Truck)} tone="t" title={t('sp.filter.ready')} value={count('READY_TO_DELIVER')} to="/staff/fulfillment" />
      </div>

      <div className="staff-insights">
        <section className="panel staff-performance" aria-labelledby="d1">
          <div className="ph"><h2 id="d1">{t('wk.chart.received')}</h2><div className="staff-period" role="group" aria-label={t('staff.ui.period')}>
            {([7, 30] as const).map((n) => <button key={n} type="button" aria-pressed={period === n} className={period === n ? 'on' : ''} onClick={() => setPeriod(n)}>{t('staff.ui.days', { n })}</button>)}
          </div></div>
          <div className="staff-chart-total"><b>{received}</b><span>{t('wk.chart.orders')}</span></div>
          <svg viewBox="0 0 720 240" role="img" aria-label={t('staff.ui.received', { n: received, days: period })}>
            {[0, 1, 2].map((n) => <g key={n}><path d={`M40 ${46 + n * 74}H680`} stroke="var(--line)" /><text x="0" y={50 + n * 74} fill="var(--ink3)" fontSize="12">{Math.round(ceiling * (1 - n / 2))}</text></g>)}
            <path d={`${line} L680,194 L40,194 Z`} fill="var(--acc-soft)" />
            <path d={line} fill="none" stroke="var(--ink)" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
            {ticks.map(({ date, i }) => <text key={i} x={40 + i * 640 / (period - 1)} y="226" textAnchor="middle" fontSize="11" fill="var(--ink3)">{date.toLocaleDateString(locale, { day: 'numeric', month: 'numeric' })}</text>)}
            {counts.map((value, i) => <circle key={i} cx={40 + i * 640 / (period - 1)} cy={194 - value / ceiling * 148} r="4" fill="var(--ink)"><title>{days[i].toLocaleDateString(locale)}: {value}</title></circle>)}
          </svg>
          <details className="staff-chart-data">
            <summary>{t('adm.viz.table')}</summary>
            <table><caption className="staff-sr">{t('staff.ui.received', { n: received, days: period })}</caption><thead><tr><th scope="col">{t('adm.viz.day')}</th><th scope="col">{t('wk.chart.orders')}</th></tr></thead><tbody>{days.map((date, i) => <tr key={i}><th scope="row">{date.toLocaleDateString(locale)}</th><td>{counts[i]}</td></tr>)}</tbody></table>
          </details>
        </section>
        <section className="panel staff-distribution" aria-labelledby="d2">
          <div className="ph"><h2 id="d2">{t('wk.chart.where')}</h2></div>
          <Donut
            centerLabel={t('wk.chart.open')}
            caption={t('wk.chart.openCaption', { n: orders.filter((o) => OPEN.includes(o.status)).length })}
            slices={GROUPS.map((g, i) => ({ label: t(`wk.group.${g.id}`), value: count(...g.statuses), color: SLICE_COLORS[i] }))}
          />
        </section>
      </div>

      <div className="flex">
        <section className="panel" style={{ flex: '1 1 440px' }} aria-labelledby="d3">
          <div className="ph"><h2 id="d3">{t('wk.queue')}</h2><Link to="/staff/review" className="link">{t('wk.seeAll')}</Link></div>
          <div className="list">
            {todo.map((o) => <OrderRow key={o.id} order={o} mine={o.assignedStaffId === mineId} />)}
            {list.data && !todo.length && <p className="sub">{t('sd.nothing')}</p>}
          </div>
        </section>
        <section className="panel" style={{ flex: '1 1 440px' }} aria-labelledby="d4">
          <div className="ph"><h2 id="d4">{t('wk.group.sketch')}</h2><Link to="/staff/review" className="link">{t('wk.seeAll')}</Link></div>
          <p className="sub">{t('wk.group.sketch.note')}</p>
          <div className="list">
            {sketch.map((o) => <OrderRow key={o.id} order={o} mine={o.assignedStaffId === mineId} />)}
            {list.data && !sketch.length && <p className="sub">{t('sd.nothing')}</p>}
          </div>
        </section>
      </div>
    </Shell>
  )
}
