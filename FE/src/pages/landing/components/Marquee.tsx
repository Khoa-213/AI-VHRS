import { PAPERS, PRODUCTS } from '../../../constants/catalog'
import { useT, useTn } from '../../../i18n'

/** Continuous row of finished pieces. Moves left, pauses on hover, stands still for reduced motion. */
const ITEMS = [...PRODUCTS, ...PRODUCTS].map((p, i) => ({ ...p, key: `${p.id}-${i}`, paper: PAPERS[i % PAPERS.length].color }))

export default function Marquee() {
  const t = useT()
  const tn = useTn()
  const row = (hidden: boolean) => (
    <ul className="lp-mq-set" aria-hidden={hidden || undefined}>
      {ITEMS.map((p) => (
        <li key={p.key} className="lp-mq-item">
          <div className="lp-mq-paper" style={{ aspectRatio: p.aspect, background: p.paper }}>
            <span style={{ fontFamily: p.font, color: p.ink }}>{p.text}</span>
          </div>
          <span className="lp-mq-name">{tn(p.name)}</span>
        </li>
      ))}
    </ul>
  )
  return (
    <div className="lp-mq" role="group" aria-label={t('lp.marquee')}>
      <div className="lp-mq-track">
        {row(false)}
        {row(true)}
      </div>
    </div>
  )
}
