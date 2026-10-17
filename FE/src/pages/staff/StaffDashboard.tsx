import { useAsync } from '../../hooks/useAsync'
import { useLocale, useT } from '../../i18n'
import SkipLink from '../../components/ui/SkipLink'
import ThemeToggle from '../../components/ui/ThemeToggle'
import LanguageToggle from '../../components/ui/LanguageToggle'
import { STATUS_COLOR } from '../../constants/orderStatus'
import { Link } from '../../router/router'
import { orderErrorKey, type OrderStatus, errText } from '../../services/orders'
import { listWork, type WorkOrder } from '../../services/workshop'
import { useUser } from '../../store/store'
import { fmt } from '../../utils/format'
import { isManagerRole } from './RequireStaff'
import StaffRail from './StaffRail'
import './dashboard.css'
import './polish.css'
import './workshop.css'

/** Orders grouped by what the workshop has to do next. */
export const GROUPS: { id: string; statuses: OrderStatus[]; open?: boolean }[] = [
  { id: 'intake', statuses: ['SUBMITTED'], open: true },
  { id: 'sketch', statuses: ['ACCEPTED'], open: true },
  { id: 'customer', statuses: ['NEED_INFO', 'AWAITING_PRIVACY', 'QUOTED', 'AWAITING_DEPOSIT'] },
  { id: 'production', statuses: ['CONFIRMED', 'AWAITING_ACCEPTANCE', 'AWAITING_FINAL_PAYMENT', 'READY_TO_DELIVER', 'DELIVERING'] },
  { id: 'closed', statuses: ['COMPLETED', 'REJECTED', 'CANCELLED'] },
]

export default function StaffDashboard() {
  const t = useT()
  const locale = useLocale()
  const user = useUser()
  const manager = isManagerRole(user?.apiRole)
  const list = useAsync(() => listWork({ pageSize: 100 }), [], 30000)
  const orders = list.data?.items ?? []
  const h = new Date().getHours()
  const greeting = t(h < 12 ? 'sd.morning' : h < 18 ? 'sd.afternoon' : 'sd.evening')
  const today = new Date().toLocaleDateString(locale, { weekday: 'long', day: 'numeric', month: 'long' })
  const count = (...s: OrderStatus[]) => orders.filter((o) => s.includes(o.status)).length
  const pipeline = orders.filter((o) => ['SUBMITTED', 'ACCEPTED', 'AWAITING_PRIVACY', 'QUOTED', 'AWAITING_DEPOSIT'].includes(o.status))
    .reduce((a, o) => a + (o.total ?? o.estMax ?? 0), 0)

  return (
    <div className="sd">
      <SkipLink />
      <StaffRail active="dashboard" />
      <main className="sd-body" id="main">
        <header className="sd-top">
          <div>
            <h1>{greeting}, {user?.name ?? t('sd.staff')}</h1>
            <p>{today} · {t(manager ? 'wk.roleManager' : 'wk.roleStaff')}</p>
          </div>
          <div className="sd-top-right">
            <ThemeToggle className="vh-icon-btn" />
            <LanguageToggle className="vh-icon-btn" />
          </div>
        </header>

        <div className="sd-grid">
          <section className="sd-card sd-orders" aria-labelledby="sd-orders-h">
            <div className="sd-card-head">
              <h2 id="sd-orders-h">{t('sd.orders')}</h2>
              <Link to="/staff/review" className="sd-btn">{t('sd.openReview')}</Link>
            </div>
            <div className="sd-total">
              <span>{t('sd.pipeline')}</span>
              <b className="vh-mono">{fmt(pipeline)}</b>
            </div>
            {!!list.error && <p className="lg-error" role="alert">{errText(t, orderErrorKey(list.error))}</p>}
            {list.loading && !list.data && <p className="sd-sub" role="status">{t('co.loading')}</p>}
            <div className="sd-groups">
              {GROUPS.map((g) => {
                const rows = orders.filter((o) => g.statuses.includes(o.status))
                return (
                  <details key={g.id} className="sd-group" open={g.open}>
                    <summary>
                      <span className="sd-group-name">{t(`wk.group.${g.id}`)}</span>
                      <span className="sd-group-note">{t(`wk.group.${g.id}.note`)}</span>
                      <span className="sd-group-count vh-mono">{rows.length}</span>
                    </summary>
                    <ul>
                      {rows.map((o) => <OrderRow key={o.id} order={o} mine={o.assignedStaffId === user?.id} />)}
                      {!rows.length && <li className="sd-none">{t('sd.nothing')}</li>}
                    </ul>
                  </details>
                )
              })}
            </div>
          </section>

          <div className="sd-stats">
            <div className="sd-kpis">
              <Kpi label={t('wk.kpi.intake')} value={count('SUBMITTED')} hint={t('wk.kpi.intakeHint')} tone="accent" />
              <Kpi label={t('wk.kpi.sketch')} value={count('ACCEPTED')} hint={t('wk.kpi.sketchHint')} />
              <Kpi label={t('wk.kpi.customer')} value={count('NEED_INFO', 'AWAITING_PRIVACY', 'QUOTED', 'AWAITING_DEPOSIT')} hint={t('wk.kpi.customerHint')} />
              <Kpi label={t('wk.kpi.production')} value={count('CONFIRMED')} hint={t('wk.kpi.productionHint')} />
            </div>
            <p className="sd-note">{t('wk.dashNote')}</p>
          </div>
        </div>
      </main>
    </div>
  )
}

function Kpi({ label, value, hint, tone }: { label: string; value: number; hint: string; tone?: 'accent' }) {
  return (
    <div className={`sd-kpi${tone ? ' ' + tone : ''}`}>
      <span className="sd-label">{label}</span>
      <b className="vh-mono">{value}</b>
      <span className="sd-sub">{hint}</span>
    </div>
  )
}

function OrderRow({ order: o, mine }: { order: WorkOrder; mine: boolean }) {
  const t = useT()
  return (
    <li>
      <Link to={`/staff/review/${o.id}`} className="sd-row">
        <span className="sd-row-main">
          <span className="sd-row-title">{t(`ot.${o.type}`)} × {o.quantity}</span>
          <span className="sd-row-meta">
            {o.code} · {o.customerName}
            {o.assignedStaffId === null && o.status === 'SUBMITTED' ? ` · ${t('wk.unclaimed')}` : mine ? ` · ${t('wk.mine')}` : ''}
          </span>
        </span>
        <span className="sd-row-side">
          <span className="vh-chip" style={{ color: STATUS_COLOR[o.status] }}>{t(`os.${o.status}`)}</span>
          <span className="vh-mono sd-row-total">{o.total !== null ? fmt(o.total) : o.estMax !== null ? fmt(o.estMax) : ''}</span>
        </span>
      </Link>
    </li>
  )
}
