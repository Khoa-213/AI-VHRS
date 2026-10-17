import { useT } from '../../i18n'
import SkipLink from '../../components/ui/SkipLink'
import ThemeToggle from '../../components/ui/ThemeToggle'
import LanguageToggle from '../../components/ui/LanguageToggle'
import { GHN_LIVE, lastLog, shipmentOf, stageChip, stageOf, type Stage } from '../../services/ghn'
import { Link } from '../../router/router'
import { useAllStaffOrders } from '../../store/store'
import type { Order } from '../../types'
import StaffRail from './StaffRail'
import './dashboard.css'
import './polish.css'
import './shipping.css'

const GROUPS: { id: 'problem' | 'pack' | 'courier' | 'done'; stages: Stage[] }[] = [
  { id: 'problem', stages: ['problem'] },
  { id: 'pack', stages: ['pack', 'book'] },
  { id: 'courier', stages: ['courier'] },
  { id: 'done', stages: ['done'] },
]

export default function ShippingBoard() {
  const t = useT()
  const orders = useAllStaffOrders().filter((o) => o.status === 'Shipped' || o.status === 'Delivered')
  const withStage = orders.map((o) => ({ o, stage: stageOf(o) }))
  const count = (...s: Stage[]) => withStage.filter((x) => s.includes(x.stage)).length
  const outForDelivery = orders.filter((o) => lastLog(shipmentOf(o))?.status === 'delivering').length

  return (
    <div className="sd">
      <SkipLink />
      <StaffRail active="shipping" />
      <main className="sd-body" id="main">
        <header className="sd-top">
          <div>
            <h1>{t('sp.title')}</h1>
            <p>{t('sp.lede')}</p>
          </div>
          <div className="sd-top-right">
            <span className="sd-state">{t(GHN_LIVE ? 'sp.live' : 'sp.notConnected')}</span>
            <ThemeToggle className="vh-icon-btn" />
            <LanguageToggle className="vh-icon-btn" />
          </div>
        </header>

        <div className="sp-body">
          <div className="sd-kpis">
            <Kpi label={t('sp.kpi.pack')} value={count('pack', 'book')} tone="accent" />
            <Kpi label={t('sp.kpi.courier')} value={count('courier')} />
            <Kpi label={t('sp.kpi.out')} value={outForDelivery} />
            <Kpi label={t('sp.kpi.problem')} value={count('problem')} />
          </div>

          {GROUPS.map((g) => {
            const rows = withStage.filter((x) => g.stages.includes(x.stage))
            if (g.id === 'problem' && !rows.length) return null
            return (
              <section key={g.id} className="sd-card" aria-labelledby={`sp-${g.id}`}>
                <div className="sd-card-head">
                  <h2 id={`sp-${g.id}`}>{t(`sp.g.${g.id}`)}</h2>
                  <span className="sd-tag">{t(`sp.g.${g.id}Note`)}</span>
                </div>
                {rows.length ? (
                  <ul className="sp-list">
                    {rows.map(({ o }) => <Row key={o.id} order={o} />)}
                  </ul>
                ) : (
                  <div className="sd-empty">
                    <b>{t('sp.emptyTitle')}</b>
                    <span>{t(g.id === 'pack' ? 'sp.emptyPack' : g.id === 'courier' ? 'sp.emptyCourier' : 'sp.emptyDone')}</span>
                  </div>
                )}
              </section>
            )
          })}
        </div>
      </main>
    </div>
  )
}

function Kpi({ label, value, tone }: { label: string; value: number; tone?: 'accent' }) {
  return (
    <div className={`sd-kpi${tone ? ' ' + tone : ''}`}>
      <span className="sd-label">{label}</span>
      <b className="vh-mono">{value}</b>
    </div>
  )
}

function Row({ order: o }: { order: Order }) {
  const t = useT()
  const chip = stageChip(o)
  const s = shipmentOf(o)
  return (
    <li>
      <Link to={`/staff/shipping/${encodeURIComponent(o.id)}`} className="sd-row">
        <span className="sd-row-main">
          <span className="sd-row-title">{o.title}</span>
          <span className="sd-row-meta">{o.id} · {o.shipTo?.name || o.name || t('sp.customer')}{s.ghnCode ? ` · ${s.ghnCode}` : ''}</span>
        </span>
        <span className="sd-row-side">
          <span className="vh-chip" style={{ color: chip.color }}>{t(chip.key)}</span>
          {o.shipTo?.city && <span className="sd-row-meta">{o.shipTo.city}</span>}
        </span>
      </Link>
    </li>
  )
}
