import { ORDER_HREF, svgProps } from '../../constants'
import { useT } from '../../i18n'
import { Link } from '../../router/router'
import { useUser } from '../../store/store'
import LanguageToggle from '../ui/LanguageToggle'
import ThemeToggle from '../ui/ThemeToggle'
import AccountButton from './AccountButton'

export default function SiteHeader() {
  const t = useT()
  const user = useUser()

  return (
    <header className="vh-header">
      <div className="vh-header-inner">
        <Link to="/" className="vh-logo">AI-VHRS</Link>
        <nav className="vh-nav">
          <Link to="/#showcase">{t('nav.features')}</Link>
          <Link to="/#showcase">{t('nav.robotSpecs')}</Link>
          <Link to="/#modes">{t('nav.penmanship')}</Link>
          <Link to="/#queue">{t('nav.orderQueue')}</Link>
          {user?.role === 'staff' && <Link to="/staff">{t('nav.staffDash')}</Link>}
          {user?.role === 'technician' && <Link to="/tech">{t('nav.techDesk')}</Link>}
        </nav>
        <div className="vh-actions">
          <button className="vh-icon-btn" aria-label={t('nav.search')}>
            <svg width="19" height="19" viewBox="0 0 24 24" strokeWidth="2" {...svgProps}>
              <circle cx="11" cy="11" r="8" />
              <path d="m21 21-4.3-4.3" />
            </svg>
          </button>
          <ThemeToggle className="vh-icon-btn" />
          <LanguageToggle className="vh-icon-btn" />
          <AccountButton buttonClassName="vh-icon-btn" avatarClassName="vh-avatar" />
          <Link to={ORDER_HREF} className="vh-btn vh-btn--primary vh-btn--sm vh-start">{t('nav.startWriting')}</Link>
        </div>
      </div>
    </header>
  )
}
