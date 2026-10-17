import { ORDER_HREF } from '../../../constants'
import Reveal from '../../../components/ui/Reveal'
import { useT } from '../../../i18n'

export default function Hero() {
  const t = useT()
  return (
    <section id="top" className="lp-hero">
      <Reveal className="lp-hero-inner" dur=".9s">
        <span className="lp-eyebrow">{t('lp.eyebrow')}</span>
        <h1 className="lp-h1">make your own style</h1>
        <p className="lp-hero-sub">
          {t('lp.sub')}
        </p>
        <div className="lp-hero-actions">
          <a href={ORDER_HREF} className="lp-cta-btn">{t('nav.startWriting')}</a>
          <a href="#showcase" className="lp-ghost-btn">{t('lp.explore')}</a>
        </div>
      </Reveal>
    </section>
  )
}
