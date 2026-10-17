import AssistiveTouch from './components/prototype/AssistiveTouch'
import Account, { type Section } from './pages/account/Account'
import CreateOrder from './pages/create-order/CreateOrder'
import DrawStudio from './pages/create-order/DrawStudio'
import Landing from './pages/landing/Landing'
import Login from './pages/login/Login'
import Register from './pages/login/Register'
import AssignTechnician from './pages/staff/AssignTechnician'
import StaffConsole from './pages/staff/StaffConsole'
import StaffDashboard from './pages/staff/StaffDashboard'
import TechDashboard from './pages/tech/TechDashboard'
import PreviewOrders from './pages/tech/PreviewOrders'
import QualityCheck from './pages/tech/QualityCheck'
import RobotPreview from './pages/tech/RobotPreview'
import RequireStaff from './pages/staff/RequireStaff'
import ShippingBoard from './pages/staff/ShippingBoard'
import ShippingDetail from './pages/staff/ShippingDetail'
import Tracking from './pages/tracking/Tracking'
import Deposit from './pages/order/Deposit'
import FinalPayment from './pages/order/FinalPayment'
import OrderResult from './pages/order/OrderResult'
import OrderReview from './pages/order/OrderReview'
import { matchOrderRoute, useInterceptLinks, usePath } from './router/router'

function Routes() {
  const path = usePath()

  if (path === '/create-order/draw') return <DrawStudio key="new" />
  const draw = /^\/create-order\/draw\/([^/]+)\/?$/.exec(path)
  if (draw) return <DrawStudio key={draw[1]} draftId={decodeURIComponent(draw[1])} />
  const draft = /^\/create-order\/draft\/([^/]+)\/?$/.exec(path)
  if (draft) return <CreateOrder key={draft[1]} draftId={decodeURIComponent(draft[1])} />
  if (path === '/create-order') return <CreateOrder key="new" />
  const account = /^\/account(?:\/([^/]+))?\/?$/.exec(path)
  if (account) {
    const known: Section[] = ['orders', 'drafts', 'payment', 'preferences']
    const section = known.find((s) => s === account[1]) ?? 'profile'
    return <Account section={section} />
  }
  if (path === '/login') return <Login />
  if (path === '/register') return <Register />
  if (path === '/staff') return <RequireStaff><StaffDashboard /></RequireStaff>
  if (path === '/staff/shipping') return <RequireStaff><ShippingBoard /></RequireStaff>
  const shipping = /^\/staff\/shipping\/([^/]+)\/?$/.exec(path)
  if (shipping) {
    return (
      <RequireStaff>
        <ShippingDetail key={shipping[1]} id={decodeURIComponent(shipping[1])} />
      </RequireStaff>
    )
  }
  const staffReview = /^\/staff\/review(?:\/([^/]+))?\/?$/.exec(path)
  if (staffReview) {
    return (
      <RequireStaff>
        <StaffConsole id={staffReview[1] ? decodeURIComponent(staffReview[1]) : undefined} />
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
  const assign = /^\/staff\/assign\/([^/]+)\/?$/.exec(path)
  if (assign) {
    return (
      <RequireStaff>
        <AssignTechnician key={assign[1]} id={decodeURIComponent(assign[1])} />
      </RequireStaff>
    )
  }

  const review = matchOrderRoute(path, 'review')
  if (review) return <OrderReview key={review} id={review} />
  const deposit = matchOrderRoute(path, 'deposit')
  if (deposit) return <Deposit key={deposit} id={deposit} />
  const result = matchOrderRoute(path, 'result')
  if (result) return <OrderResult key={result} id={result} />
  const final = matchOrderRoute(path, 'final-payment')
  if (final) return <FinalPayment key={final} id={final} />
  const tracking = matchOrderRoute(path, 'tracking')
  if (tracking) return <Tracking key={tracking} id={tracking} />

  return <Landing />
}

export default function App() {
  useInterceptLinks()
  return (
    <>
      <Routes />
      <AssistiveTouch />
    </>
  )
}
