import { CalendarCheck, ClipboardText, SealCheck } from '@phosphor-icons/react'
import { WeekBars } from '../../components/ws/charts'
import { Kpi, avatarTone, initials } from '../../components/ws/parts'
import Shell from '../../components/ws/Shell'
import { useAsync } from '../../hooks/useAsync'
import { useLocale, useT } from '../../i18n'
import { Link } from '../../router/router'
import { adminInks, adminPapers, adminPens } from '../../services/manage'
import { errText, orderErrorKey } from '../../services/orders'
import { getStaffDirectory, listRobots, listWork, pendingApprovals, scheduleQueue } from '../../services/workshop'
import { useUser } from '../../store/store'
import { OPEN, lastSevenDays } from './StaffDashboard'

/** Stock at or below this is shown as running low. */
const LOW_STOCK = 20
const PAID = ['CONFIRMED', 'AWAITING_ACCEPTANCE', 'AWAITING_FINAL_PAYMENT', 'READY_TO_DELIVER', 'DELIVERING', 'COMPLETED']
const ROBOT_CHIP = { AVAILABLE: 'good', BUSY: 'orange', MAINTENANCE: 'warn', BROKEN: 'bad' } as const

/** What needs a decision across the workshop. The Manager sees every order, the approvals and schedule waiting, staff load, robots and low stock. */
export default function ManagerDashboard() {
  const t = useT()
  const locale = useLocale()
  const user = useUser()
  const orders = useAsync(() => listWork({ pageSize: 100 }), [], 30000)
  const approvals = useAsync(async () => (await pendingApprovals()).total, [], 30000)
  const queue = useAsync(async () => (await scheduleQueue()).total, [], 30000)
  const staff = useAsync(getStaffDirectory, [], 60000)
  const robots = useAsync(listRobots, [], 60000)
  const stock = useAsync(async () => {
    const [papers, pens, inks] = await Promise.all([adminPapers(), adminPens(), adminInks()])
    return [
      ...inks.filter((i) => i.active).map((i) => ({ key: `i${i.id}`, name: i.name, kind: 'ink', stock: i.stock, hex: i.hex })),
      ...papers.filter((p) => p.active).map((p) => ({ key: `p${p.id}`, name: p.name, kind: 'paper', stock: p.stock, hex: null })),
      ...pens.filter((p) => p.active).map((p) => ({ key: `n${p.id}`, name: p.name, kind: 'pen', stock: p.stock, hex: null })),
    ].filter((x) => LOW_STOCK >= x.stock).sort((a, b) => a.stock - b.stock).slice(0, 5)
  }, [], 120000)

  const all = orders.data?.items ?? []
  const week = lastSevenDays(all, locale)
  const paidWeek = lastSevenDays(all.filter((o) => PAID.includes(o.status)), locale).counts
  const open = all.filter((o) => OPEN.includes(o.status)).length
  const top = Math.max(1, ...staff.data?.map((s) => s.openOrders) ?? [])
  const err = [orders.error, approvals.error, queue.error].find(Boolean)

  return (
    <Shell area="manager" active="dashboard" title={t('wk.hello', { name: user?.name ?? t('wk.roleManager') })} lede={t('wk.managerLede')}>
      {!!err && <p className="lg-error" role="alert">{errText(t, orderErrorKey(err))}</p>}

      <div className="row3">
        <Kpi icon={<SealCheck size={20} aria-hidden />} tone="a" title={t('rail.approvals')} value={approvals.data ?? 0} badge={t('wk.needsYou')} badgeTone="ac" to="/staff/approvals" />
        <Kpi icon={<CalendarCheck size={20} aria-hidden />} tone="p" title={t('wk.kpi.slot')} value={queue.data ?? 0} note={t('wk.kpi.slotHint')} to="/staff/schedule" />
        <Kpi icon={<ClipboardText size={20} aria-hidden />} title={t('wk.kpi.open')} value={open} note={t('wk.kpi.openHint')} to="/staff/review" />
      </div>

      <div className="flex">
        <section className="panel" style={{ flex: '2 1 560px' }} aria-labelledby="m1">
          <div className="ph">
            <h2 id="m1">{t('wk.chart.ordersPaid')}</h2>
            <div className="legend" style={{ flexDirection: 'row', gap: 18 }}>
              <div><i style={{ background: 'var(--acc-soft)', boxShadow: 'inset 0 0 0 1px var(--acc-mid)' }} />{t('wk.chart.received')}</div>
              <div><i style={{ background: 'var(--acc)' }} />{t('wk.chart.paid')}</div>
            </div>
          </div>
          <WeekBars values={week.counts} second={paidWeek} labels={week.labels} unit={t('wk.chart.orders')} caption={t('wk.chart.caption2', { orders: week.counts.reduce((a, b) => a + b, 0), paid: paidWeek.reduce((a, b) => a + b, 0) })} />
        </section>

        <section className="panel" style={{ flex: '1 1 340px' }} aria-labelledby="m2">
          <div className="ph"><h2 id="m2">{t('wk.staffLoad')}</h2></div>
          <div className="list">
            {(staff.data ?? []).map((s) => (
              <div key={s.id} className="item">
                <span className={`avatar ${avatarTone(s.fullName)}`}>{initials(s.fullName)}</span>
                <div className="t"><b>{s.fullName}</b><span>{s.email}</span></div>
                <div style={{ width: 100 }}><div className="bar"><i style={{ width: `${(s.openOrders / top) * 100}%` }} /></div></div>
                <b>{s.openOrders}</b>
              </div>
            ))}
            {staff.data && !staff.data.length && <p className="sub">{t('wk.noStaff')}</p>}
          </div>
        </section>
      </div>

      <div className="flex">
        <section className="panel" style={{ flex: '1 1 440px' }} aria-labelledby="m3">
          <div className="ph"><h2 id="m3">{t('mg.tab.robots')}</h2><Link to="/staff/schedule" className="link">{t('wk.seeSchedule')}</Link></div>
          <div className="list">
            {(robots.data ?? []).map((r) => (
              <div key={r.id} className="item">
                <div className="t"><b>{r.code}</b><span>{r.station ?? ''}{r.isSimulated ? ` · ${t('wk.simulated')}` : ''}</span></div>
                <span className={`chip ${ROBOT_CHIP[r.status]}`}>{t(`rs.${r.status}`)}</span>
              </div>
            ))}
            {robots.data && !robots.data.length && <p className="sub">{t('wk.noRobots')}</p>}
          </div>
        </section>

        <section className="panel" style={{ flex: '1 1 440px' }} aria-labelledby="m4">
          <div className="ph"><h2 id="m4">{t('wk.stockWatch')}</h2><Link to="/staff/catalog" className="link">{t('wk.seeCatalog')}</Link></div>
          <div className="list">
            {(stock.data ?? []).map((x) => {
              const tone = x.stock <= 5 ? 'bad' : 'warn'
              return (
              <div key={x.key} className="item">
                {x.hex ? <span className="swatch" style={{ background: x.hex, width: 34, height: 34 }} /> : <span className="ci b" />}
                <div className="t"><b>{x.name}</b><span>{t(`wk.stockKind.${x.kind}`)}</span></div>
                <span className={`chip ${tone}`}>{t('wk.left', { n: x.stock })}</span>
              </div>
              )
            })}
            {stock.data && !stock.data.length && <p className="sub">{t('wk.stockOk')}</p>}
          </div>
        </section>
      </div>
    </Shell>
  )
}
