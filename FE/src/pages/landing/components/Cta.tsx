import { ORDER_HREF } from '../../../constants'
import Reveal from '../../../components/ui/Reveal'

export default function Cta() {
  return (
    <section id="queue" className="lp-cta-section">
      <Reveal className="lp-cta-card" dur=".8s">
        <div className="lp-cta-copy">
          <h2>Ready to put ink on paper?</h2>
          <p>Submit a request and follow it live in your order queue, from trajectory check to final stroke.</p>
        </div>
        <a href={ORDER_HREF} className="lp-cta-btn">Start Writing</a>
      </Reveal>
    </section>
  )
}
