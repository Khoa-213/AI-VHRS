import { useEffect, useRef } from 'react'
import { ORDER_HREF } from '../../../constants'
import { PAPERS, PRODUCTS } from '../../../constants/catalog'
import { useT } from '../../../i18n'
import fr3Arm from '../../../assets/fr3-arm.png'

const SAMPLE = PRODUCTS.find((p) => p.id === 'print') ?? PRODUCTS[0]
const PAPER = PAPERS.find((p) => p.id === 'cotton') ?? PAPERS[0]

/**
 * Hero. A calligraphy sheet (what the customer sends) slides in from the left, the FR3 arm
 * (what writes it) from the right, and they meet behind the slogan. Scrolling pulls them together.
 */
export default function Hero() {
  const t = useT()
  const ref = useRef<HTMLElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    let raf = 0
    const update = () => {
      if (raf) return
      raf = requestAnimationFrame(() => {
        raf = 0
        const r = el.getBoundingClientRect()
        const p = Math.min(1, Math.max(0, -r.top / Math.max(1, r.height)))
        el.style.setProperty('--hp', p.toFixed(3))
      })
    }
    document.addEventListener('scroll', update, { passive: true, capture: true })
    window.addEventListener('resize', update)
    update()
    return () => {
      cancelAnimationFrame(raf)
      document.removeEventListener('scroll', update, { capture: true })
      window.removeEventListener('resize', update)
    }
  }, [])

  return (
    <section id="top" ref={ref} className="lp-hero">
      <div className="lp-halo" aria-hidden="true" />

      <div className="lp-hand lp-hand--l" aria-hidden="true">
        <div className="lp-hand-in">
          <div className="lp-sheet" style={{ background: PAPER.color, aspectRatio: SAMPLE.aspect }}>
            <span style={{ fontFamily: SAMPLE.font, color: SAMPLE.ink }}>{SAMPLE.text}</span>
          </div>
        </div>
      </div>

      <div className="lp-hero-title">
        <h1 className="lp-h1">
          <span className="lp-h1-brand">AI-VHRS</span>
          <span className="lp-h1-line">
            <span className="lp-h1-dim">make your</span> own style
          </span>
        </h1>
      </div>

      <div className="lp-hand lp-hand--r" aria-hidden="true">
        <div className="lp-hand-in">
          <img src={fr3Arm} alt="" draggable={false} />
        </div>
      </div>

      <div className="lp-hero-foot">
        <div className="lp-hero-note">
          <span className="lp-eyebrow">{t('lp.eyebrow')}</span>
          <p className="lp-hero-sub">{t('lp.sub')}</p>
        </div>
        <div className="lp-chips">
          <a href="#showcase" className="lp-chip">{t('lp.explore')}</a>
          <a href={ORDER_HREF} className="lp-chip lp-chip--solid">{t('nav.startWriting')}</a>
        </div>
      </div>
    </section>
  )
}
