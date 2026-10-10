import PrototypeBar from './components/prototype/PrototypeBar'
import Cart from './pages/cart/Cart'
import CreateOrder from './pages/create-order/CreateOrder'
import Landing from './pages/landing/Landing'
import Deposit from './pages/order/Deposit'
import FinalPayment from './pages/order/FinalPayment'
import OrderResult from './pages/order/OrderResult'
import OrderReview from './pages/order/OrderReview'
import { matchOrderRoute, useInterceptLinks, usePath } from './router/router'

function Routes() {
  const path = usePath()

  if (path === '/create-order') return <CreateOrder />
  if (path === '/cart') return <Cart />

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
