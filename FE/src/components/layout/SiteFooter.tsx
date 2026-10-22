import { ArrowUpRight } from '@phosphor-icons/react'
import robotArm from '../../assets/fr3-arm.png'
import { ORDER_HREF } from '../../constants'
import { LANGS, setLang, useLang, useT } from '../../i18n'
import { Link } from '../../router/router'
import './site-footer.css'

const CONTACT_EMAIL = 'Seventeengfa97@gmail.com'
const CONTACT_PHONE = '0900 000 000'
const YEAR = new Date().getFullYear()

/** Shared customer footer with a large wordmark and robot illustration. */
export default function SiteFooter({ framed = false }: { framed?: boolean }) {
  const t = useT()
  const lang = useLang()
  return <footer className={framed ? 'sf sf--framed' : 'sf'}>
    <div className="sf-inner">
      <div className="sf-top">
        <section className="sf-block sf-contact-block" aria-label={t('ft.contact')}>
          <h2>{t('ft.contact')}</h2>
          <div className="sf-contact-item"><span>{t('login.email')}</span><a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a></div>
          <div className="sf-contact-item"><span>{t('ft.phone')}</span><p>{CONTACT_PHONE}</p><small>{t('ft.samplePhone')}</small></div>
          <div className="sf-contact-item"><span>{t('ft.location')}</span><address>{t('ft.campusAddress')}</address></div>
        </section>
        <nav className="sf-block" aria-label={t('ft.explore')}>
          <h2>{t('ft.explore')}</h2>
          <Link to="/#showcase">{t('ft.howItWorks')}</Link>
          <Link to="/#specs">{t('ft.robot')}</Link>
          <Link to="/#modes">{t('ft.inputModes')}</Link>
          <Link to={ORDER_HREF}>{t('nav.startWriting')}<ArrowUpRight size={12} aria-hidden /></Link>
        </nav>
        <nav className="sf-block" aria-label={t('ft.create')}>
          <h2>{t('ft.create')}</h2>
          <Link to={`${ORDER_HREF}#mode=text`}>{t('ft.fromText')}<ArrowUpRight size={12} aria-hidden /></Link>
          <Link to={`${ORDER_HREF}#mode=upload`}>{t('ft.fromImage')}<ArrowUpRight size={12} aria-hidden /></Link>
          <Link to={`${ORDER_HREF}#mode=draw`}>{t('ft.fromDrawing')}<ArrowUpRight size={12} aria-hidden /></Link>
          <p className="sf-service-note">{t('ft.materials')}</p>
        </nav>
        <nav className="sf-block sf-support" aria-label={t('ft.support')}>
          <h2>{t('ft.support')}</h2>
          <a href={`mailto:${CONTACT_EMAIL}`}>{t('ft.emailUs')}<ArrowUpRight size={12} aria-hidden /></a>
          <Link to="/account/orders">{t('ft.myOrders')}</Link>
          <Link to="/account/drafts">{t('ft.myDrafts')}</Link>
          <p className="sf-support-note">{t('ft.supportBody')}</p>
          <div className="sf-langs" role="group" aria-label={t('lang.label')}>
            {LANGS.map((l) => <button key={l.id} type="button" lang={l.id} className={l.id === lang ? 'on' : undefined}
              aria-label={l.name} aria-pressed={l.id === lang} onClick={() => setLang(l.id)}>{l.code}</button>)}
          </div>
        </nav>
        <div className="sf-intro">
          <span className="sf-kicker"><span /><span>AI-VHRS</span> / <span>FR3</span></span>
          <h2>{t('ft.projectTitle')}</h2>
          <p>{t('ft.projectBody')}</p>
          <Link className="sf-create" to={ORDER_HREF}>{t('nav.startWriting')}<ArrowUpRight size={18} aria-hidden /></Link>
        </div>
      </div>
      <div className="sf-stage" aria-hidden="true">

        <span className="sf-wordmark">AI-VHRS</span>
        <img className="sf-robot" src={robotArm} alt="" loading="lazy" />
        <span className="sf-stage-caption"><span>AI-VHRS</span> / <span>FR3</span></span>
      </div>
      <div className="sf-copy"><span>{t('ft.copyright', { year: YEAR })}. {t('ft.rights')}.</span><a href="#top" onClick={(event) => { event.preventDefault(); window.scrollTo({ top: 0, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' }) }}>{t('ft.backTop')}<ArrowUpRight size={14} aria-hidden /></a></div>
    </div>
  </footer>
}
