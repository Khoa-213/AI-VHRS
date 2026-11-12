import {
  ArrowRight, CalendarCheck, CaretRight, CheckCircle, ClipboardText, Clock, SealCheck, WarningCircle,
} from '@phosphor-icons/react'
import { useState } from 'react'
import { Donut } from '../../components/ws/charts'
import { Kpi, avatarTone, initials } from '../../components/ws/parts'
import Shell from '../../components/ws/Shell'
import { useAsync } from '../../hooks/useAsync'
import { useLocale, useT } from '../../i18n'
import { Link } from '../../router/router'
import { managerDashboard, managerRobotStatus } from '../../services/managerOps'
import { errText, orderErrorKey } from '../../services/orders'
import { allWork, getStaffDirectory } from '../../services/workshop'
import { dayOf, isoDay, lastDays } from '../../utils/managerDates'
import { Chip, LineChart, Panel, Period, StateChip } from './managerKit'

const SLICE_COLORS = ['var(--acc)', 'var(--staff-series-2)', 'var(--staff-series-3)', 'var(--staff-series-4)']
const PERIODS = [7, 30] as const

/**
 * Manager home (UC-45) in the Staff frame. Numbers come from `GET /manager/dashboard`, robot state from
 * `GET /manager/robot-status`. The received-orders chart counts submitted orders per day from the workshop list, because the
 * dashboard has no history; staff load comes from the staff directory.
 */
export default function ManagerDashboard() {
  const t = useT()
  const locale = useLocale()
  const dash = useAsync(managerDashboard, [], 30000)
  const robots = useAsync(managerRobotStatus, [], 30000)
  const orders = useAsync(() => allWork(), [], 60000)
  const staff = useAsync(getStaffDirectory, [], 60000)
  const [period, setPeriod] = useState<(typeof PERIODS)[number]>(7)

  const d = dash.data
  const openTotal = d ? Object.values(d.ordersByStatus).reduce((a, n) => a + n, 0) : 0
  const red = (robots.data ?? []).filter((r) => r.level >= 4)
  const offline = (robots.data ?? []).filter((r) => r.state === 'OFFLINE')
  const day = (iso: string) => dayOf(iso).toLocaleDateString(locale, { day: 'numeric', month: 'short' })
  const time = (iso: string) => new Date(iso).toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' })
  const icon = (I: typeof ClipboardText) => <I size={20} aria-hidden />

  // What needs the Manager, most serious first. Each line opens the screen where it is handled.
  const todo: { tone: 'bad' | 'warn'; title: string; body?: string; to: string }[] = []
  if (red.length) todo.push({ tone: 'bad', title: t('mgr.at.red', { n: red.length }), body: t('mgr.at.redBody', { codes: red.map((r) => r.robotCode).join(', ') }), to: '/staff/robots' })
  if (d) {
    if (d.lateOrders.length) todo.push({ tone: 'bad', title: t('mgr.at.late', { n: d.lateOrders.length }), body: t('mgr.at.lateBody'), to: '/staff/schedule' })
    if (d.pending.openIncidents) todo.push({ tone: 'warn', title: t('mgr.at.incidents', { n: d.pending.openIncidents }), to: '/staff/robots' })
    if (d.pending.priceAdjustments) todo.push({ tone: 'warn', title: t('mgr.at.adjust', { n: d.pending.priceAdjustments }), to: '/staff/approvals' })
    if (d.pending.ordersToSchedule) todo.push({ tone: 'warn', title: t('mgr.at.schedule', { n: d.pending.ordersToSchedule }), to: '/staff/schedule' })
    if (d.pending.unclaimedOrders) todo.push({ tone: 'warn', title: t('mgr.at.unclaimed', { n: d.pending.unclaimedOrders }), to: '/staff/review' })
    if (d.pending.refundsToConfirm) todo.push({ tone: 'warn', title: t('mgr.at.refunds', { n: d.pending.refundsToConfirm }), to: '/staff/refunds' })
    if (d.lowStock.length) todo.push({ tone: 'warn', title: t('mgr.at.stock', { n: d.lowStock.length }), to: '/staff/catalog' })
  }
  if (offline.length) todo.push({ tone: 'warn', title: t('mgr.at.offline', { n: offline.length }), body: offline.map((r) => r.robotCode).join(', '), to: '/staff/robots' })
  const level = todo.some((a) => a.tone === 'bad') ? 'bad' : todo.length ? 'warn' : 'good'

  const days = lastDays(period)
  const received = days.map((iso) => (orders.data ?? []).filter((o) => o.submittedAt && isoDay(new Date(o.submittedAt)) === iso).length)
  const receivedTotal = received.reduce((a, n) => a + n, 0)

  const statuses = Object.entries(d?.ordersByStatus ?? {}).sort((a, b) => b[1] - a[1])
  const slices = [
    ...statuses.slice(0, 3).map(([s, n], i) => ({ label: t(`os.${s}`), value: n, color: SLICE_COLORS[i] })),
    ...(statuses.length > 3 ? [{ label: t('mgr.other'), value: statuses.slice(3).reduce((a, [, n]) => a + n, 0), color: SLICE_COLORS[3] }] : []),
  ]
  const topLoad = Math.max(1, ...(staff.data ?? []).map((s) => s.openOrders))
  const err = [dash.error, robots.error, orders.error, staff.error].find(Boolean)
  const arrow = <ArrowRight size={16} aria-hidden />

  return (
    <Shell
      area="manager"
      active="dashboard"
      title={t('rail.dashboard')}
      tools={<Link to="/staff/reports" className="staff-primary-link">{t('mgr.nav.reports')}<ArrowRight size={17} aria-hidden /></Link>}
    >
      {!!err && <p className="lg-error" role="alert">{errText(t, orderErrorKey(err))}</p>}
      {dash.loading && !d && <p className="sub" role="status">{t('co.loading')}</p>}

      {d && (
        <div className={`mgr-banner ${level}`} role="status">
          {level === 'good' ? <CheckCircle size={26} weight="fill" aria-hidden /> : <WarningCircle size={26} weight="fill" aria-hidden />}
          <div style={{ flex: 1, minWidth: 200 }}>
            <b>{t(`mgr.banner.${level}`)}</b>
            {todo.length > 0 && <span>{todo.map((a) => a.title).join('; ')}</span>}
          </div>
        </div>
      )}

      {d && (
        <div className="row4 staff-kpis">
          <Kpi actionIcon={arrow} icon={icon(ClipboardText)} title={t('mgr.kpi.open')} value={openTotal} to="/staff/review"
            note={d.pending.unclaimedOrders ? t('mgr.kpi.unclaimed', { n: d.pending.unclaimedOrders }) : t('mgr.kpi.allClaimed')} />
          <Kpi actionIcon={arrow} icon={icon(SealCheck)} title={t('mgr.kpi.adjust')} value={d.pending.priceAdjustments} to="/staff/approvals"
            badge={d.pending.priceAdjustments ? t('mgr.kpi.waiting') : undefined} badgeTone="ac" />
          <Kpi actionIcon={arrow} icon={icon(CalendarCheck)} title={t('mgr.kpi.toSchedule')} value={d.pending.ordersToSchedule} to="/staff/schedule"
            badge={d.pending.ordersToSchedule ? t('mgr.kpi.waiting') : undefined} badgeTone="ac" />
          <Kpi actionIcon={arrow} icon={icon(Clock)} title={t('mgr.kpi.jobsToday')} value={d.jobsToday.length} to="/staff/schedule"
            note={t('mgr.kpi.next7', { n: d.jobsNext7Days })} />
        </div>
      )}

      <div className="staff-insights">
        <section className="panel staff-performance" aria-labelledby="m1">
          <div className="ph">
            <h2 id="m1">{t('wk.chart.received')}</h2>
            <Period options={PERIODS} value={period} onChange={setPeriod} label={t('staff.ui.period')} text={(n) => t('staff.ui.days', { n })} />
          </div>
          <div className="staff-chart-total"><b>{receivedTotal}</b><span>{t('wk.chart.orders')}</span></div>
          {orders.loading && !orders.data
            ? <p className="sub" role="status">{t('co.loading')}</p>
            : <LineChart
                key={period}
                locale={locale}
                caption={t('staff.ui.received', { n: receivedTotal, days: period })}
                column={t('wk.chart.orders')}
                points={days.map((iso, i) => ({
                  label: dayOf(iso).toLocaleDateString(locale, { day: 'numeric', month: 'numeric' }),
                  long: dayOf(iso).toLocaleDateString(locale),
                  value: received[i],
                  readout: String(received[i]),
                }))}
              />}
        </section>
        <section className="panel staff-distribution" aria-labelledby="m2">
          <div className="ph"><h2 id="m2">{t('mgr.chart.byStatus')}</h2></div>
          {d && (slices.length
            ? <Donut centerLabel={t('mgr.chart.openCenter')} caption={t('mgr.chart.byStatus')} slices={slices} />
            : <p className="sub">{t('mgr.none.open')}</p>)}
        </section>
      </div>

      <div className="mgr-grid2">
        <Panel title={t('adm.at.title')}>
          {d && !todo.length && <p className="sub">{t('mgr.banner.good')}</p>}
          <nav className="mgr-todo" aria-label={t('adm.at.title')}>
            {todo.map((a) => (
              <Link key={a.title} to={a.to}>
                <span className={`mgr-dot ${a.tone}`} aria-hidden />
                <span className="t"><b>{a.title}</b>{a.body && <span>{a.body}</span>}</span>
                <span className="staff-sr">{t(a.tone === 'bad' ? 'mgr.urgent' : 'mgr.waitingTag')}</span>
                <CaretRight size={16} aria-hidden />
              </Link>
            ))}
          </nav>
        </Panel>

        <Panel title={t('mgr.today.title')} aside={<Link to="/staff/schedule" className="link">{t('rail.schedule')}</Link>}>
          {d && !d.jobsToday.length && <p className="sub">{t('mgr.today.none', { n: d.jobsNext7Days })}</p>}
          <div className="list">
            {(d?.jobsToday ?? []).map((j) => (
              <Link key={j.jobId} to={`/staff/robots?job=${j.jobId}`} className="item">
                <div className="t">
                  <b>{t('mgr.slot', { from: time(j.slotStart), to: time(j.slotEnd) })}</b>
                  <span>{j.orderCode} · {j.robotCode}{j.isRewrite ? ` · ${t('mgr.rewrite')}` : ''}</span>
                </div>
                <Chip tone={j.status === 'FAILED' ? 'bad' : j.status === 'WRITING' ? 'navy' : 'mute'}>{t(`js.${j.status}`)}</Chip>
              </Link>
            ))}
          </div>
        </Panel>
      </div>

      <div className="mgr-grid2">
        <Panel title={t('mgr.late.title')}>
          {d && !d.lateOrders.length && !d.dueIn2Days.length && <p className="sub">{t('mgr.late.none')}</p>}
          <div className="list">
            {(d?.lateOrders ?? []).slice(0, 8).map((o) => (
              <Link key={`l${o.orderId}`} to={`/staff/review/${o.orderId}`} className="item">
                <div className="t"><b>{o.code}</b><span>{t(`os.${o.status}`)} · {t('mgr.eta', { date: day(o.eta) })}</span></div>
                <Chip tone="bad">{t('mgr.daysLate', { n: o.daysLate ?? 0 })}</Chip>
              </Link>
            ))}
            {(d?.dueIn2Days ?? []).slice(0, 5).map((o) => (
              <Link key={`s${o.orderId}`} to={`/staff/review/${o.orderId}`} className="item">
                <div className="t"><b>{o.code}</b><span>{t(`os.${o.status}`)} · {t('mgr.eta', { date: day(o.eta) })}</span></div>
                <Chip tone="warn">{t('mgr.dueSoon')}</Chip>
              </Link>
            ))}
          </div>
          {d && d.lateOrders.length > 8 && <p className="sub">{t('mgr.late.more', { n: d.lateOrders.length - 8 })}</p>}
        </Panel>

        <Panel title={t('mgr.robots.title')} aside={<Link to="/staff/robots" className="link">{t('mgr.nav.robots')}</Link>}>
          {robots.loading && !robots.data && <p className="sub" role="status">{t('co.loading')}</p>}
          {robots.data && !robots.data.length && <p className="sub">{t('wk.noRobots')}</p>}
          <div className="list">
            {(robots.data ?? []).map((r) => (
              <Link key={r.robotId} to="/staff/robots" className="item">
                <div className="t"><b>{r.robotCode}</b><span>{r.alerts.length ? t('mgr.robots.alerts', { n: r.alerts.length }) : t('rb.noAlerts')}</span></div>
                <StateChip state={r.state} />
              </Link>
            ))}
          </div>
        </Panel>
      </div>

      <div className="mgr-grid2">
        <Panel title={t('wk.stockWatch')} aside={<Link to="/staff/catalog" className="link">{t('wk.seeCatalog')}</Link>}>
          {d && !d.lowStock.length && <p className="sub">{t('wk.stockOk')}</p>}
          <div className="list">
            {(d?.lowStock ?? []).map((s) => (
              <div key={`${s.kind}${s.id}`} className="item">
                <div className="t"><b>{s.name}</b><span>{t(`wk.stockKind.${s.kind.toLowerCase()}`)}</span></div>
                <Chip tone={s.stock <= 0 ? 'bad' : 'warn'}>{t('wk.left', { n: s.stock })}</Chip>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title={t('wk.staffLoad')}>
          {staff.data && !staff.data.length && <p className="sub">{t('wk.noStaff')}</p>}
          <div className="list">
            {(staff.data ?? []).map((s) => (
              <div key={s.id} className="item">
                <span className={`avatar ${avatarTone(s.fullName)}`}>{initials(s.fullName)}</span>
                <div className="t"><b>{s.fullName}</b><span>{s.email}</span></div>
                <div style={{ width: 100 }}><div className="bar"><i style={{ width: `${(s.openOrders / topLoad) * 100}%` }} /></div></div>
                <b aria-label={t('mgr.staffOpen', { name: s.fullName, n: s.openOrders })}>{s.openOrders}</b>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </Shell>
  )
}
