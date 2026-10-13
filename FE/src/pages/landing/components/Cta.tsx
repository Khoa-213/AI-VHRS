import { ORDER_HREF } from '../../../constants'
import Reveal from '../../../components/ui/Reveal'
import { useT } from '../../../i18n'

export default function Cta() {
  const t = useT()
  return (
    <section id="queue" className="lp-cta-section">
      <Reveal className="lp-cta-card" dur=".8s">
        <div className="lp-cta-copy">
          <h2>{t('lp.cta.title')}</h2>
          <p>{t('lp.cta.copy')}</p>
        </div>
        <a href={ORDER_HREF} className="lp-cta-btn">{t('nav.startWriting')}</a>
      </Reveal>
    </section>
  )
}
