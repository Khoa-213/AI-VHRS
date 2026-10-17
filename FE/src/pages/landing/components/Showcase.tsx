import fr3Arm from '../../../assets/fr3-arm.png'
import { ORDER_HREF } from '../../../constants'
import { useT } from '../../../i18n'
import { useScrollProgress } from '../../../hooks/useScrollProgress'
import { ease, seg } from '../../../utils/math'

const SPECS = [
  { value: '±0.02 mm', key: 'lp.spec.repeat' },
  { value: '6-DoF', key: 'lp.spec.dof' },
  { value: '100% Ink', key: 'lp.spec.ink' },
  { value: 'VNPay / MoMo', key: 'lp.spec.checkout' },
]

export default function Showcase() {
  const t = useT()
  const { ref, p } = useScrollProgress<HTMLElement>()
  const e1 = ease(seg(p, 0, 0.35))
  const e2 = ease(seg(p, 0.38, 0.62))

  return (
    <section id="showcase" ref={ref} className="lp-showcase">
      <div className="lp-sticky">
        <div
          className="lp-bigtext"
          style={{ opacity: 1 - e2, transform: `translate(-50%,-50%) scale(${(0.96 + e1 * 0.06).toFixed(3)})` }}
        >
          FR3
        </div>

        <div
          className="lp-robot"
          style={{
            transform: `translate(-50%,-50%) translate(${(e2 * 22).toFixed(2)}vw,${((1 - e1) * 62).toFixed(2)}vh) scale(${(1 - e2 * 0.1).toFixed(3)})`,
          }}
        >
          <div className="lp-robot-shadow" />
          <img src={fr3Arm} alt={t('lp.robotAlt')} />
        </div>

        <div id="specs" className="lp-specs-wrap">
          <div
            className="lp-specs"
            style={{
              opacity: e2,
              transform: `translateX(${((1 - e2) * -40).toFixed(1)}px)`,
              pointerEvents: e2 > 0.5 ? 'auto' : 'none',
            }}
          >
            <h2 className="lp-h2-spec">
              AI-VHRS<span style={{ color: 'var(--accent)' }}>·FR3</span>
            </h2>
            <p className="lp-spec-copy">
              {t('lp.spec.copy')}
            </p>
            <div className="lp-spec-grid">
              {SPECS.map((s, i) => {
                const k = ease(seg(p, 0.6 + i * 0.07, 0.72 + i * 0.07))
                return (
                  <div
                    key={s.value}
                    className="lp-spec"
                    style={{ opacity: k, transform: `translateY(${((1 - k) * 20).toFixed(1)}px)` }}
                  >
                    <span className="lp-spec-value">{s.value}</span>
                    <span className="lp-spec-label">{t(s.key)}</span>
                  </div>
                )
              })}
            </div>
            <a href={ORDER_HREF} className="lp-cta-btn">{t('nav.startWriting')}</a>
          </div>
        </div>

        <div className="lp-progress" aria-hidden="true">
          <div className="lp-progress-fill" style={{ width: `${(p * 100).toFixed(1)}%` }} />
        </div>
      </div>
    </section>
  )
}
