import { ORDER_HREF } from '../../../constants'
import Reveal from '../../../components/ui/Reveal'

export default function Hero() {
  return (
    <section id="top" className="lp-hero">
      <Reveal className="lp-hero-inner" dur=".9s">
        <span className="lp-eyebrow">Robot-written Vietnamese calligraphy</span>
        <h1 className="lp-h1">make your own style.</h1>
        <p className="lp-hero-sub">
          Your words, traced by AI and written in real ink on real paper by a Fairino 6-axis robotic arm.
        </p>
        <div className="lp-hero-actions">
          <a href={ORDER_HREF} className="lp-cta-btn">Start Writing</a>
          <a href="#showcase" className="lp-ghost-btn">Explore Robot Demo</a>
        </div>
      </Reveal>
    </section>
  )
}
