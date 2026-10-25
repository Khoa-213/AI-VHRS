import { CalendarCheck, ClipboardText, PencilSimple, SquaresFour } from '@phosphor-icons/react'
import { Donut, WeekBars } from '../../components/ws/charts'
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
const SLICE_COLORS = ['var(--acc)', '#e5d6b8', '#c1d8da', '#b8bed5']

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
  const list = useAsync(() => allWork(), [], 30000)
  const orders = list.data ?? []
  const mineId = user?.id
  const count = (...s: OrderStatus[]) => orders.filter((o) => s.includes(o.status)).length
  const week = lastSevenDays(orders, locale)
  const todo = orders.filter((o) => o.status === 'SUBMITTED' || o.status === 'ACCEPTED').slice(0, 5)
  const sketch = orders.filter((o) => o.status === 'ACCEPTED').slice(0, 4)
  const icon = (I: typeof SquaresFour) => <I size={20} aria-hidden />

  return (
    <Shell area="staff" active="dashboard" title={t('wk.hello', { name: user?.name ?? t('sd.staff') })} lede={t('wk.helloLede')}>
      {!!list.error && <p className="lg-error" role="alert">{errText(t, orderErrorKey(list.error))}</p>}
      {list.loading && !list.data && <p className="sub" role="status">{t('co.loading')}</p>}

      <div className="row3">
        <Kpi icon={icon(ClipboardText)} tone="a" title={t('wk.kpi.intake')} value={count('SUBMITTED')} note={t('wk.kpi.intakeHint')} to="/staff/review" />
        <Kpi icon={icon(PencilSimple)} tone="p" title={t('wk.kpi.sketch')} value={count('ACCEPTED')} note={t('wk.kpi.sketchHint')} to="/staff/review" />
        <Kpi icon={icon(CalendarCheck)} tone="b" title={t('wk.kpi.production')} value={count('CONFIRMED')} note={t('wk.kpi.productionHint')} to="/staff/review" />
      </div>

      <div className="flex">
        <section className="panel" style={{ flex: '2 1 560px' }} aria-labelledby="d1">
          <div className="ph"><h2 id="d1">{t('wk.chart.received')}</h2><span className="sub">{t('wk.chart.last7')}</span></div>
          <WeekBars values={week.counts} labels={week.labels} unit={t('wk.chart.orders')} caption={t('wk.chart.caption', { max: Math.max(...week.counts) })} />
        </section>
        <section className="panel" style={{ flex: '1 1 340px' }} aria-labelledby="d2">
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
