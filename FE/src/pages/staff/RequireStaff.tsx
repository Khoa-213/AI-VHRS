import { useEffect, type ReactNode } from 'react'
import { useT } from '../../i18n'
import { Link, navigate } from '../../router/router'
import { useUser } from '../../store/store'
import type { Role } from '../../types'

/** Backend roles allowed into the workshop screens. Admin has no access to orders, it has its own area under /admin. */
export const isWorkshop = (apiRole?: string) => apiRole === 'STAFF' || apiRole === 'MANAGER'
export const isManagerRole = (apiRole?: string) => apiRole === 'MANAGER'

/**
 * Role gate. With `role="admin"` it needs an Admin account. With `role="technician"` it lets technicians in (the technician screens are not wired to the API yet).
 * For the workshop it needs a Staff or Manager account, plus a Manager one when `manager` is set.
 */
export default function RequireStaff({ children, role = 'staff', manager = false }: { children: ReactNode; role?: Role; manager?: boolean }) {
  const user = useUser()
  const allowed = role === 'technician'
    ? user?.role === 'technician'
    : role === 'admin'
      ? user?.apiRole === 'ADMIN'
      : isWorkshop(user?.apiRole) && (!manager || isManagerRole(user?.apiRole))

  useEffect(() => {
    // StrictMode runs effects twice: only redirect from the guarded page itself. Someone signed in without access sees a notice instead.
    if (!allowed && !user && window.location.pathname !== '/login') {
      navigate(`/login?next=${encodeURIComponent(window.location.pathname)}`)
    }
  }, [allowed, user])

  if (allowed) return <>{children}</>
  return user ? <NoAccess /> : null
}

function NoAccess() {
  const t = useT()
  return (
    <main className="vh-panel" style={{ alignItems: 'flex-start', maxWidth: 640, margin: '12vh auto', padding: 24 }}>
      <h1 className="vh-h1">{t('wk.noAccessTitle')}</h1>
      <p className="vh-lede">{t('wk.noAccessBody')}</p>
      <Link to="/" className="vh-btn vh-btn--primary">{t('dp.home')}</Link>
    </main>
  )
}
