import { ORDER_HREF, svgProps } from '../../../constants'
import { useT } from '../../../i18n'
import ThemeToggle from '../../../components/ui/ThemeToggle'
import LanguageToggle from '../../../components/ui/LanguageToggle'
import AccountButton from '../../../components/layout/AccountButton'

/** Floating pill navbar: logo, a lead pill plus a pill group of links, then tools and the call to action. */
export default function Header() {
  const t = useT()
  return (
    <header className="lp-header">
      <div className="lp-header-inner">
        <a href="/#top" className="lp-logo" aria-label="AI-VHRS FR3">
          <span className="lp-logo-mark" aria-hidden="true" />
          <span>AI-VHRS</span>
        </a>
        <nav className="lp-nav" aria-label={t('nav.features')}>
          <a href="/#showcase" className="lp-nav-lead">
            <span className="lp-nav-dot" aria-hidden="true" />
            {t('nav.features')}
          </a>
          <div className="lp-nav-group">
            <a href="/#showcase">{t('nav.robotSpecs')}</a>
            <a href="/#modes">{t('nav.penmanship')}</a>
            <a href="/#queue">{t('nav.orderQueue')}</a>
          </div>
        </nav>
        <div className="lp-actions">
          <div className="lp-tools">
            <button className="lp-icon-btn" aria-label={t('nav.search')}>
              <svg width="18" height="18" viewBox="0 0 24 24" strokeWidth="2" {...svgProps}>
                <circle cx="11" cy="11" r="8" />
                <path d="m21 21-4.3-4.3" />
              </svg>
            </button>
            <ThemeToggle className="lp-icon-btn" />
            <LanguageToggle className="lp-icon-btn" />
            <AccountButton buttonClassName="lp-icon-btn" avatarClassName="vh-avatar" />
          </div>
          <a href={ORDER_HREF} className="lp-start-btn">
            <span className="lp-start-dot" aria-hidden="true">
              <svg width="12" height="12" viewBox="0 0 24 24" strokeWidth="2.4" {...svgProps}>
                <path d="M12 2 22 12 12 22 2 12Z" />
              </svg>
            </span>
            <span>{t('nav.startWriting')}</span>
          </a>
        </div>
      </div>
    </header>
  )
}
