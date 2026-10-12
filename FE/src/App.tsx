import PrototypeBar from './components/prototype/PrototypeBar'
import Cart from './pages/cart/Cart'
import CreateOrder from './pages/create-order/CreateOrder'
import DrawStudio from './pages/create-order/DrawStudio'
import CreateOrderV2 from './pages/create-order/CreateOrderV2'
import Landing from './pages/landing/Landing'
import Login from './pages/login/Login'
import AssignTechnician from './pages/staff/AssignTechnician'
import StaffConsole from './pages/staff/StaffConsole'
import StaffDashboard from './pages/staff/StaffDashboard'
import TechDashboard from './pages/tech/TechDashboard'
import PreviewOrders from './pages/tech/PreviewOrders'
import QualityCheck from './pages/tech/QualityCheck'
import RobotPreview from './pages/tech/RobotPreview'
import RequireStaff from './pages/staff/RequireStaff'
import Deposit from './pages/order/Deposit'
import FinalPayment from './pages/order/FinalPayment'
import OrderResult from './pages/order/OrderResult'
import OrderReview from './pages/order/OrderReview'
import { matchOrderRoute, useInterceptLinks, usePath } from './router/router'

function Routes() {
  const path = usePath()

  if (path === '/create-order/draw') return <DrawStudio />
  if (path === '/create-order') return <CreateOrder />
  if (path === '/create-order-v2') return <CreateOrderV2 />
  if (path === '/cart') return <Cart />
  if (path === '/login') return <Login />
  if (path === '/staff') return <RequireStaff><StaffDashboard /></RequireStaff>
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

  return <Landing />
}

export default function App() {
  useInterceptLinks()
  return (
    <>
      <Routes />
      <PrototypeBar />
    </>
  )
}
