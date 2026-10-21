import { UserCircle } from '@phosphor-icons/react'
import { openAuth } from '../../store/authDialog'
import { useT } from '../../i18n'
import { Link } from '../../router/router'
import { useProfile, useUser } from '../../store/store'

/** Top bar avatar. Signed in it opens the account page, signed out it opens login. */
export default function AccountButton({ buttonClassName, avatarClassName }: { buttonClassName: string; avatarClassName: string }) {
  const t = useT()
  const user = useUser()
  const profile = useProfile()
  if (!user) {
    return (
      <button type="button" onClick={() => openAuth()} className={buttonClassName} aria-label={t('nav.signIn')} title={t('nav.signIn')}>
        <UserCircle size={22} aria-hidden />
      </button>
    )
  }
  const initial = (profile.fullName || user.name).trim().charAt(0).toUpperCase()
  return (
    <Link to="/account" className={buttonClassName} aria-label={t('nav.account')} title={t('nav.signedInAs', { name: user.name })}>
      {profile.avatar
        ? <img src={profile.avatar} alt="" className={`${avatarClassName} acct-avatar-img`} />
        : <span className={avatarClassName}>{initial}</span>}
    </Link>
  )
}
