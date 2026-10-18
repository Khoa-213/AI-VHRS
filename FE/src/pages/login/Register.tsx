import { useT } from '../../i18n'
import SkipLink from '../../components/ui/SkipLink'
import { navigate } from '../../router/router'
import Header from '../landing/components/Header'
import RegisterForm from './RegisterForm'
import '../landing/landing.css'
import '../landing/landing-redesign.css'
import '../create-order/sign-in-dialog.css'

/** The standalone page shares the same registration form and styling as the popup. */
export default function Register() {
  const t = useT()
  return <div className="lp-root entry-register-page">
    <SkipLink />
    <Header />
    <main id="main" className="entry-register-main">
      <section className="entry-login entry-register-card" aria-labelledby="register-title">
        <div className="entry-login-panel">
          <span className="entry-login-brand">AI-VHRS</span>
          <h1 id="register-title">{t('reg.title')}</h1>
          <p className="entry-login-description">{t('reg.lede')}</p>
          <RegisterForm onSuccess={() => navigate('/')} onSignIn={() => navigate('/login')} />
        </div>
      </section>
    </main>
  </div>
}
