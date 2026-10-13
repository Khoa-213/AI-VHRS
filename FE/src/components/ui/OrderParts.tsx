import { ORDER_HREF } from '../../constants'
import { useT } from '../../i18n'
import { Link } from '../../router/router'
import Page from '../layout/Page'

/** Dot timeline: dots before `idx` are done, the dot at `idx` is current. */
export function OrderTimeline({ labels, idx }: { labels: string[]; idx: number }) {
  return (
    <div className="vh-timeline">
      {labels.map((label, i) => (
        <div key={label} className={i < idx ? 'done' : i === idx ? 'now' : ''}>
          <i />
          <span>{label}</span>
        </div>
      ))}
    </div>
  )
}

export function SpecRows({ rows }: { rows: { k: string; v: string }[] }) {
  return (
    <div className="vh-rows">
      {rows.map((r) => (
        <div key={r.k} className="vh-row">
          <span>{r.k}</span>
          <span>{r.v}</span>
        </div>
      ))}
    </div>
  )
}

/** Shown when the order list is empty (for example after clearing storage by hand). */
export function NoOrder({ label }: { label: string }) {
  const t = useT()
  return (
    <Page label={label} width={720}>
      <div className="vh-panel" style={{ alignItems: 'flex-start' }}>
        <span className="vh-eyebrow">{t('np.eyebrow')}</span>
        <h1 className="vh-h1">{t('np.title')}</h1>
        <p className="vh-lede">{t('np.lede')}</p>
        <Link to={ORDER_HREF} className="vh-btn vh-btn--primary">{t('np.cta')}</Link>
      </div>
    </Page>
  )
}
