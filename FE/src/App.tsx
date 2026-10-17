import Account, { type Section } from './pages/account/Account'
import CreateOrder from './pages/create-order/CreateOrder'
import DrawStudio from './pages/create-order/DrawStudio'
import Landing from './pages/landing/Landing'
import Login from './pages/login/Login'
import Register from './pages/login/Register'
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
import RobotPreview from './pages/tech/RobotPreview'
import RequireStaff from './pages/staff/RequireStaff'
import Deposit from './pages/order/Deposit'
import OrderReview from './pages/order/OrderReview'
import { matchOrderRoute, navigate, useInterceptLinks, usePath } from './router/router'
import { useEffect } from 'react'
import { useUser } from './store/store'

/**
 * Where a signed-in person may be. Workshop accounts live under /staff and technicians under /tech (plus /account and
 * /login), customers stay out of both. Anything else is sent home, so a trimmed address never lands on the wrong site.
 */
function homeFor(role: string | undefined, path: string): string | null {
  const own = role === 'staff' ? '/staff' : role === 'technician' ? '/tech' : null
  if (own) return path === own || path.startsWith(own + '/') || /^\/(account|login)(\/|$)/.test(path) ? null : own
  if (role === 'customer' && /^\/(staff|tech)(\/|$)/.test(path)) return '/'
  return null
}

function Routes() {
  const path = usePath()
  const user = useUser()
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
  if (path === '/login') return <Login />
  if (path === '/register') return <Register />
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

  if (path === '/tech') return <RequireStaff role="technician"><TechDashboard /></RequireStaff>
  if (path === '/tech/preview') return <RequireStaff role="technician"><PreviewOrders mode="preview" /></RequireStaff>
  if (path === '/tech/qc') return <RequireStaff role="technician"><PreviewOrders mode="qc" /></RequireStaff>
  const qc = /^\/tech\/qc\/([^/]+)\/?$/.exec(path)
  if (qc) {
    return (
      <RequireStaff role="technician">
        <QualityCheck key={qc[1]} id={decodeURIComponent(qc[1])} />
      </RequireStaff>
    )
  }
  const preview = /^\/tech\/preview\/([^/]+)\/?$/.exec(path)
  if (preview) {
    return (
      <RequireStaff role="technician">
        <RobotPreview key={preview[1]} id={decodeURIComponent(preview[1])} />
      </RequireStaff>
    )
  }
  const review = matchOrderRoute(path, 'review')
  if (review) return <OrderReview key={review} id={review} />
  const deposit = matchOrderRoute(path, 'deposit')
  if (deposit) return <Deposit key={deposit} id={deposit} />

  return <Landing />
}

export default function App() {
  useInterceptLinks()
  return <Routes />
}
