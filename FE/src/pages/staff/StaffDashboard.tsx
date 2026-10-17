import { useLocale, useT, useTn } from '../../i18n'
import SkipLink from '../../components/ui/SkipLink'
import { STATUS_COLORS } from '../../constants/catalog'
import ThemeToggle from '../../components/ui/ThemeToggle'
import LanguageToggle from '../../components/ui/LanguageToggle'
import { Link } from '../../router/router'
import { useAllStaffOrders, useUser } from '../../store/store'
import type { Order } from '../../types'
import { fmt } from '../../utils/format'
import StaffRail from './StaffRail'
import { GROUPS, qualityStats, reviewTelemetry } from './telemetry'
import './dashboard.css'
import './polish.css'

export default function StaffDashboard() {
  const t = useT()
  const tn = useTn()
  const locale = useLocale()
  const h = new Date().getHours()
  const greeting = t(h < 12 ? 'sd.morning' : h < 18 ? 'sd.afternoon' : 'sd.evening')
  const user = useUser()
  const orders = useAllStaffOrders()
  const review = reviewTelemetry(orders)
  const quality = qualityStats(orders)
  const today = new Date().toLocaleDateString(locale, { weekday: 'long', day: 'numeric', month: 'long' })

  return (
    <div className="sd">
      <SkipLink />
      <StaffRail active="dashboard" />

      <main className="sd-body" id="main">
        <header className="sd-top">
          <div>
            <h1>{greeting}, {user?.name ?? t('sd.staff')}</h1>
            <p>{today}</p>
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
              <b className="vh-mono">{fmt(review.queuedValue)}</b>
            </div>

            <div className="sd-groups">
              {GROUPS.map((g) => {
                const rows = orders.filter((o) => g.statuses.includes(o.status))
                return (
                  <details key={g.id} className="sd-group" open={g.id === 'review' || g.id === 'producing'}>
                    <summary>
                      <span className="sd-group-name">{tn(g.label)}</span>
                      <span className="sd-group-note">{tn(g.note)}</span>
                      <span className="sd-group-count vh-mono">{rows.length}</span>
                    </summary>
                    <ul>
                      {rows.map((o) => <OrderRow key={o.id} order={o} link={g.reviewable} />)}
                      {!rows.length && <li className="sd-none">{t('sd.nothing')}</li>}
                    </ul>
                  </details>
                )
              })}
            </div>
          </section>

          <div className="sd-stats">
            <div className="sd-kpis">
              <Kpi label={t('sd.kpi.review')} value={String(review.pending)} hint={t('sd.kpi.reviewHint')} tone="accent" />
              <Kpi label={t('sd.kpi.deposit')} value={String(review.accepted)} hint={t('sd.kpi.depositHint')} />
              <Kpi label={t('sd.kpi.prod')} value={String(review.producing)} hint={t('sd.kpi.prodHint')} />
              <Kpi label={t('sd.kpi.rej')} value={String(review.rejected)} hint={t('sd.kpi.rejHint')} />
            </div>

            <div className="sd-two">
              <section className="sd-card" aria-labelledby="sd-eval-h">
                <div className="sd-card-head">
                  <h2 id="sd-eval-h">{t('sd.quality')}</h2>
                </div>
                <div className="sd-eval">
                  <div>
                    <b className="sd-big vh-mono">{quality.avg ?? '–'}</b>
                    <span className="sd-sub">{t('sd.avg')}</span>
                  </div>
                  <div>
                    <b className="sd-big vh-mono">{quality.pass === null ? '–' : `${quality.pass}%`}</b>
                    <span className="sd-sub">{t('sd.pass')}</span>
                  </div>
                </div>
                <p className="sd-note">
                  {quality.scoredCount
                    ? t(quality.scoredCount > 1 ? 'sd.basedOnMany' : 'sd.basedOn', { n: quality.scoredCount })
                    : t('sd.noEval')}
                </p>
              </section>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}

function Kpi({ label, value, hint, tone }: { label: string; value: string; hint: string; tone?: 'accent' }) {
  return (
    <div className={`sd-kpi${tone ? ' ' + tone : ''}`}>
      <span className="sd-label">{label}</span>
      <b className="vh-mono">{value}</b>
      <span className="sd-sub">{hint}</span>
    </div>
  )
}

function OrderRow({ order: o, link }: { order: Order; link: boolean }) {
  const t = useT()
  const tn = useTn()
  const [baseColor] = STATUS_COLORS[o.status]
  // Accepted orders: green once a technician has them, amber until then.
  const needsTech = o.status === 'Accepted' && !o.assignment
  const assigned = o.status === 'Accepted' && !!o.assignment
  const color = assigned ? 'var(--good)' : needsTech ? 'var(--warn)' : baseColor
  const label = assigned ? t('sd.assigned') : needsTech ? t('sd.needsTech') : t(`status.${o.status}`)
  const body = (
    <>
      <span className="sd-row-main">
        <span className="sd-row-title">{tn(o.title)}</span>
        <span className="sd-row-meta">
          {o.id} · {o.name || t('common.customer')}
          {assigned && ` · ${t('sd.onRobot', { tech: o.assignment!.techName, robot: o.assignment!.robotId })}`}
        </span>
      </span>
      <span className="sd-row-side">
        <span className="vh-chip" style={{ color }}>{label}</span>
        <span className="vh-mono sd-row-total">{fmt(o.total)}</span>
      </span>
    </>
  )
  return (
    <li>
      {link ? <Link to={`/staff/${o.status === 'Accepted' ? 'assign' : 'review'}/${encodeURIComponent(o.id)}`} className={`sd-row${assigned ? ' assigned' : needsTech ? ' needs' : ''}`}>{body}</Link> : <div className="sd-row static">{body}</div>}
    </li>
  )
}
