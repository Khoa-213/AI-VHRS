import { svgProps } from '../../constants'
import { useT } from '../../i18n'
import { Link, navigate } from '../../router/router'
import { signOut, useDrafts, useUser } from '../../store/store'
import OrderHistoryMenu from './OrderHistoryMenu'
import ThemeToggle from '../ui/ThemeToggle'
import LanguageToggle from '../ui/LanguageToggle'

export default function SiteHeader() {
  const t = useT()
  const user = useUser()
  const drafts = useDrafts()

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
          {user && (
            <Link to="/drafts" className="vh-nav-tab">
              {t('nav.drafts')}
              {drafts.length > 0 && <span className="vh-nav-count">{drafts.length}</span>}
            </Link>
          )}
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
          <OrderHistoryMenu buttonClassName="vh-icon-btn" />
          <button
            className="vh-icon-btn"
            aria-label={t(user ? 'nav.signOut' : 'nav.signIn')}
            title={user ? t('nav.signedInAs', { name: user.name }) : t('nav.signIn')}
            onClick={user ? signOut : () => navigate('/login')}
          >
            {user ? (
              <span className="vh-avatar">{user.name.trim().charAt(0).toUpperCase()}</span>
            ) : (
              <svg width="20" height="20" viewBox="0 0 24 24" strokeWidth="2" {...svgProps}>
                <circle cx="12" cy="12" r="10" />
                <circle cx="12" cy="10" r="3" />
                <path d="M7 20.662V19a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v1.662" />
              </svg>
            )}
          </button>
        </div>
      </div>
    </header>
  )
}
