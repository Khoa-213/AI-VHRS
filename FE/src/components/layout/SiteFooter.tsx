import BrandLogo from '../ui/BrandLogo'
import { ORDER_HREF } from '../../constants'
import { LANGS, setLang, useLang, useT } from '../../i18n'
import { Link } from '../../router/router'
import facebook from '../../assets/footer/facebook.svg'
import instagram from '../../assets/footer/instagram.svg'
import telegram from '../../assets/footer/telegram.svg'
import './site-footer.css'

/** Studio contact shown in the footer. Placeholders until the studio has its own line, inbox and pages. */
const CONTACT = { phone: '+84 28 0000 0000', email: 'hello@ai-vhrs.vn' }
const YEAR = new Date().getFullYear()
const SOCIAL = {
  facebook: { label: 'Facebook', href: 'https://www.facebook.com/', icon: facebook },
  instagram: { label: 'Instagram', href: 'https://www.instagram.com/', icon: instagram },
  telegram: { label: 'Telegram', href: 'https://telegram.org/', icon: telegram },
}

function Social({ id }: { id: keyof typeof SOCIAL }) {
  const s = SOCIAL[id]
  return (
    <a href={s.href} target="_blank" rel="noreferrer" aria-label={s.label} title={s.label}>
      <img src={s.icon} width={40} height={40} alt="" />
    </a>
  )
}

/**
 * Footer of the customer site (landing and order pages). Layout from the Figma "footer" frame (133:14634). It stays dark
 * in both themes, with its own `--footer-*` tokens. The language list is a real switcher.
 */
export default function SiteFooter({ framed = false }: { framed?: boolean }) {
  const t = useT()
  const lang = useLang()

  return (
    <footer className={framed ? 'sf sf--framed' : 'sf'}>
      <div className="sf-inner">
        <div className="sf-left">
          <div className="sf-about">
            <Link to="/" className="sf-logo">
              <BrandLogo theme="dark" />
            </Link>
            <div className="sf-about-body">
              <p className="sf-lede">{t('ft.lede')}</p>
              <Link to="/#showcase" className="sf-more">
                {t('ft.more')}
                <span className="sf-dot" aria-hidden />
              </Link>
            </div>
          </div>

          <div className="sf-left-foot">
            <div className="sf-social">
              <div className="sf-social-col">
                <Social id="telegram" />
                <Social id="facebook" />
              </div>
              <div className="sf-social-col">
                <Social id="instagram" />
              </div>
            </div>
            <p className="sf-copy">
              {t('ft.copyright', { year: YEAR })}
              <br />
              {t('ft.rights')}
            </p>
          </div>
        </div>

        <div className="sf-right">
          <nav className="sf-nav" aria-label={t('ft.nav')}>
            <Link to="/#showcase">{t('nav.features')}</Link>
            <Link to="/#modes">{t('nav.penmanship')}</Link>
            <Link to="/#queue">{t('nav.orderQueue')}</Link>
            <Link to={ORDER_HREF}>{t('nav.startWriting')}</Link>
          </nav>

          <div className="sf-right-foot">
            <div className="sf-blocks">
              <div className="sf-block">
                <h2>{t('ft.contact')}</h2>
                <p>
                  <a href={`tel:${CONTACT.phone.replace(/\s/g, '')}`}>{CONTACT.phone}</a>
                  <br />
                  <a href={`mailto:${CONTACT.email}`}>{CONTACT.email}</a>
                </p>
              </div>
              <div className="sf-block">
                <h2>{t('ft.location')}</h2>
                <p>
                  {t('ft.studio')}
                  <br />
                  {t('ft.city')}
                </p>
              </div>
            </div>

            <div className="sf-langs" role="group" aria-labelledby="sf-langs-title">
              <p id="sf-langs-title">{t('lang.label')}</p>
              <div>
                {LANGS.map((l) => (
                  <button
                    key={l.id}
                    type="button"
                    lang={l.id}
                    className={l.id === lang ? 'on' : undefined}
                    aria-pressed={l.id === lang}
                    aria-label={l.name}
                    title={l.name}
                    onClick={() => setLang(l.id)}
                  >
                    {l.code[0] + l.code.slice(1).toLowerCase()}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </footer>
  )
}
