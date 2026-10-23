import Account, { type Section } from './pages/account/Account'
import CreateOrder from './pages/create-order/CreateOrder'
import DrawStudio from './pages/create-order/DrawStudio'
import Landing from './pages/landing/Landing'
import SignInDialog from './pages/create-order/SignInDialog'
import { closeAuth, openAuth, useAuthDialog } from './store/authDialog'
import AdminDashboard from './pages/admin/AdminDashboard'
import Accounts from './pages/admin/Accounts'
import AuditLog from './pages/admin/AuditLog'
import Approvals from './pages/staff/Approvals'
import Catalog from './pages/staff/Catalog'
import Pricing from './pages/staff/Pricing'
import Schedule from './pages/staff/Schedule'
import Workbench from './pages/staff/Workbench'
import ManagerDashboard from './pages/staff/ManagerDashboard'
import StaffDashboard from './pages/staff/StaffDashboard'
import TechDashboard from './pages/tech/TechDashboard'
import PreviewOrders from './pages/tech/PreviewOrders'
import QualityCheck from './pages/tech/QualityCheck'
import JobRun from './pages/tech/JobRun'
import RequireStaff from './pages/staff/RequireStaff'
import ChatDock from './components/ui/ChatDock'
import Deposit from './pages/order/Deposit'
import OrderReview from './pages/order/OrderReview'
import PrivacyPreview from './pages/order/PrivacyPreview'
import { matchOrderRoute, navigate, useInterceptLinks, usePath } from './router/router'
import { useEffect } from 'react'
import { useUser } from './store/store'

/**
 * Where a signed-in person may be. Workshop accounts live under /staff and technicians under /tech (plus /account and
 * /login), customers stay out of both. Anything else is sent home, so a trimmed address never lands on the wrong site.
 */
function homeFor(role: string | undefined, path: string): string | null {
  const own = role === 'staff' ? '/staff' : role === 'technician' ? '/tech' : role === 'admin' ? '/admin' : null
  if (own) return path === own || path.startsWith(own + '/') || /^\/(account|login)(\/|$)/.test(path) ? null : own
  if (role === 'customer' && /^\/(staff|tech|admin)(\/|$)/.test(path)) return '/'
  return null
}

function Routes() {
  const path = usePath()
  const user = useUser()
  const legacyAuth = path === '/login' || path === '/register'
  useEffect(() => {
    if (legacyAuth) {
      const next = new URLSearchParams(window.location.search).get('next') ?? undefined
      navigate('/', { replace: true })
      openAuth(path === '/register' ? 'register' : 'login', next)
    }
  }, [legacyAuth, path])
  const redirect = homeFor(user?.role, path)
  useEffect(() => {
    if (redirect) navigate(redirect, { replace: true })
  }, [redirect])
  if (redirect) return null

  const draw = /^\/create-order\/draw\/(\d+)\/?$/.exec(path)
  if (draw) return <DrawStudio key={draw[1]} orderId={Number(draw[1])} />
  // One instance for the whole flow: the draft is created on the server mid-form and the address follows.
  const draft = /^\/create-order\/draft\/(\d+)\/?$/.exec(path)
  if (draft) return <CreateOrder key="create" orderId={Number(draft[1])} />
  if (path === '/create-order' || path === '/create-order/draw') return <CreateOrder key="create" />
  const account = /^\/account(?:\/([^/]+))?\/?$/.exec(path)
  if (account) {
    const known: Section[] = ['orders', 'drafts', 'payment', 'preferences']
    const section = known.find((s) => s === account[1]) ?? 'profile'
    return <Account section={section} />
  }

  if (path === '/staff') return <RequireStaff>{user?.apiRole === 'MANAGER' ? <ManagerDashboard /> : <StaffDashboard />}</RequireStaff>
  const staffReview = /^\/staff\/review(?:\/(\d+))?\/?$/.exec(path)
  if (staffReview) {
    return (
      <RequireStaff>
        <Workbench id={staffReview[1] ? Number(staffReview[1]) : undefined} />
      </RequireStaff>
    )
  }
  if (path === '/staff/catalog') return <RequireStaff manager><Catalog /></RequireStaff>
  if (path === '/staff/pricing') return <RequireStaff manager><Pricing /></RequireStaff>
  if (path === '/staff/approvals') return <RequireStaff manager><Approvals /></RequireStaff>
  const schedule = /^\/staff\/schedule(?:\/(\d+))?\/?$/.exec(path)
  if (schedule) {
    return (
      <RequireStaff manager>
        <Schedule id={schedule[1] ? Number(schedule[1]) : undefined} />
      </RequireStaff>
    )
  }

  if (path === '/admin') return <RequireStaff role="admin"><AdminDashboard /></RequireStaff>
  if (path === '/admin/accounts') return <RequireStaff role="admin"><Accounts /></RequireStaff>
  if (path === '/admin/audit') return <RequireStaff role="admin"><AuditLog /></RequireStaff>

  if (path === '/tech') return <RequireStaff role="technician"><TechDashboard /></RequireStaff>
  if (path === '/tech/preview') return <RequireStaff role="technician"><PreviewOrders mode="preview" /></RequireStaff>
  if (path === '/tech/qc') return <RequireStaff role="technician"><PreviewOrders mode="qc" /></RequireStaff>
  const qc = /^\/tech\/qc\/(\d+)\/?$/.exec(path)
  if (qc) {
    return (
      <RequireStaff role="technician">
        <QualityCheck key={qc[1]} id={Number(qc[1])} />
      </RequireStaff>
    )
  }
  const preview = /^\/tech\/preview\/(\d+)\/?$/.exec(path)
  if (preview) {
    return (
      <RequireStaff role="technician">
        <JobRun key={preview[1]} id={Number(preview[1])} />
      </RequireStaff>
    )
  }
  if (import.meta.env.DEV && path === '/dev/privacy') return <PrivacyPreview />
  const review = matchOrderRoute(path, 'review')
  if (review) return <OrderReview key={review} id={review} />
  const deposit = matchOrderRoute(path, 'deposit')
  if (deposit) return <Deposit key={deposit} id={deposit} />

  return <Landing />
}

export default function App() {
  useInterceptLinks()
  const auth = useAuthDialog()
  return <><Routes /><ChatDock />{auth && <SignInDialog initialMode={auth.mode} next={auth.next} onClose={closeAuth} />}</>
}
