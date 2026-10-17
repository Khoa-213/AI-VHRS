import { ORDER_HREF, svgProps } from '../../../constants'
import { useT } from '../../../i18n'
import ThemeToggle from '../../../components/ui/ThemeToggle'
import LanguageToggle from '../../../components/ui/LanguageToggle'
import AccountButton from '../../../components/layout/AccountButton'

export default function Header() {
  const t = useT()
  return (
    <header className="lp-header">
      <div className="lp-header-inner">
        <a href="#top" className="lp-logo">AI-VHRS</a>
        <nav className="lp-nav">
          <a href="#showcase">{t('nav.features')}</a>
          <a href="#showcase">{t('nav.robotSpecs')}</a>
          <a href="#modes">{t('nav.penmanship')}</a>
          <a href="#queue">{t('nav.orderQueue')}</a>
        </nav>
        <div className="lp-actions">
          <button className="lp-icon-btn" aria-label={t('nav.search')}>
            <svg width="19" height="19" viewBox="0 0 24 24" strokeWidth="2" {...svgProps}>
              <circle cx="11" cy="11" r="8" />
              <path d="m21 21-4.3-4.3" />
            </svg>
          </button>
          <ThemeToggle className="lp-icon-btn" />
          <LanguageToggle className="lp-icon-btn" />
          <AccountButton buttonClassName="lp-icon-btn" avatarClassName="vh-avatar" />
          <a href={ORDER_HREF} className="lp-start-btn">{t('nav.startWriting')}</a>
        </div>
      </div>
    </header>
  )
}
