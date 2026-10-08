import { svgProps } from '../../../constants'
import Reveal from '../../../components/ui/Reveal'

export default function Hero() {
  return (
    <section id="top" className="lp-hero">
      <div className="lp-hero-grid" />
      <Reveal className="lp-hero-inner" dur=".9s">
        <span className="lp-pill">
          <span className="lp-pill-dot" />
          Collaborative robotics · Vietnamese calligraphy
        </span>
        <h1 className="lp-h1">make your own style.</h1>
        <p className="lp-hero-sub">
          AI-powered trajectory reconstruction executed by Fairino 6-DoF collaborative robotic arms on physical paper.
        </p>
        <a href="#showcase" className="lp-cta-btn">
          Explore Robot Demo
          <svg width="18" height="18" viewBox="0 0 24 24" strokeWidth="2.4" {...svgProps}>
            <path d="M5 12h14" />
            <path d="m12 5 7 7-7 7" />
          </svg>
        </a>
      </Reveal>
    </section>
  )
}
