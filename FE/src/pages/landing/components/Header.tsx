import { ORDER_HREF, svgProps } from '../../../constants'
import { useT } from '../../../i18n'
import ThemeToggle from '../../../components/ui/ThemeToggle'
import LanguageToggle from '../../../components/ui/LanguageToggle'
import OrderHistoryMenu from '../../../components/layout/OrderHistoryMenu'
import { useDrafts, useUser } from '../../../store/store'

export default function Header() {
  const t = useT()
  const user = useUser()
  const drafts = useDrafts()
  return (
    <header className="lp-header">
      <div className="lp-header-inner">
        <a href="#top" className="lp-logo">AI-VHRS</a>
        <nav className="lp-nav">
          <a href="#showcase">{t('nav.features')}</a>
          <a href="#showcase">{t('nav.robotSpecs')}</a>
          <a href="#modes">{t('nav.penmanship')}</a>
          <a href="#queue">{t('nav.orderQueue')}</a>
          {user && (
            <a href="/drafts">
              {t('nav.drafts')}
              {drafts.length > 0 && <span className="vh-nav-count">{drafts.length}</span>}
            </a>
          )}
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
          <OrderHistoryMenu buttonClassName="lp-icon-btn" />
          <a href="/login" className="lp-icon-btn" aria-label={t('nav.signIn')}>
            <svg width="20" height="20" viewBox="0 0 24 24" strokeWidth="2" {...svgProps}>
              <circle cx="12" cy="12" r="10" />
              <circle cx="12" cy="10" r="3" />
              <path d="M7 20.662V19a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v1.662" />
            </svg>
          </a>
          <a href={ORDER_HREF} className="lp-start-btn">{t('nav.startWriting')}</a>
        </div>
      </div>
    </header>
  )
}
