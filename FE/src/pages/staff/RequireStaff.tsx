import { useEffect, type ReactNode } from 'react'
import { navigate } from '../../router/router'
import { useUser } from '../../store/store'
import type { Role } from '../../types'

/** Role gate: only signed-in users with this role see the children, everyone else is sent to the login page. */
export default function RequireStaff({ children, role = 'staff' }: { children: ReactNode; role?: Role }) {
  const user = useUser()
  const allowed = user?.role === role

  useEffect(() => {
    if (!allowed) {
      const next = window.location.pathname
      navigate(`/login?next=${encodeURIComponent(next)}`)
    }
  }, [allowed])

  return allowed ? <>{children}</> : null
}
