import fr3Arm from '../../../assets/fr3-arm.png'
import { ORDER_HREF } from '../../../constants'
import { useScrollProgress } from '../../../hooks/useScrollProgress'
import { ease, seg } from '../../../utils/math'

const SPECS = [
  { value: '±0.02 mm', label: 'Trajectory repeatability' },
  { value: '6-DoF', label: 'Joint freedom & spline smoothing' },
  { value: '100% Ink', label: 'Fountain & calligraphy pens' },
  { value: 'VNPay / MoMo', label: 'Instant checkout' },
]

export default function Showcase() {
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
          <img src={fr3Arm} alt="Fairino FR3 collaborative robotic arm" />
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
              A 6-axis collaborative arm, retuned for penmanship. Your strokes become smooth splines, then real ink on real paper.
            </p>
            <div className="lp-spec-grid">
              {SPECS.map((s, i) => {
                const t = ease(seg(p, 0.6 + i * 0.07, 0.72 + i * 0.07))
                return (
                  <div
                    key={s.value}
                    className="lp-spec"
                    style={{ opacity: t, transform: `translateY(${((1 - t) * 20).toFixed(1)}px)` }}
                  >
                    <span className="lp-spec-value">{s.value}</span>
                    <span className="lp-spec-label">{s.label}</span>
                  </div>
                )
              })}
            </div>
            <a href={ORDER_HREF} className="lp-cta-btn">Start Writing</a>
          </div>
        </div>

        <div className="lp-progress" aria-hidden="true">
          <div className="lp-progress-fill" style={{ width: `${(p * 100).toFixed(1)}%` }} />
        </div>
      </div>
    </section>
  )
}
