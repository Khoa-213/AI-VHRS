import type { ReactNode } from 'react'
import Header from '../../pages/landing/components/Header'
import SiteFooter from './SiteFooter'
import '../../pages/landing/landing.css'
import '../../pages/landing/landing-redesign.css'
import '../../pages/create-order/co-home.css'
import './customer.css'

/** Shared customer surface, including direct links into the middle of an order. */
export default function CustomerFrame({ children, label, className = '', narrow = false, footer = true }: {
  children: ReactNode
  label: string
  className?: string
  narrow?: boolean
  /** The order flow (create, review, deposit, delivery, payment) runs without the site footer. */
  footer?: boolean
}) {
  return <div className="lp-root co-root customer-root">
    <Header />
    <main className={`co-frame ${className}${narrow ? ' co-frame--narrow' : ''}`} data-screen-label={label}>
      {children}
    </main>
    {footer && <SiteFooter framed />}
  </div>
}
