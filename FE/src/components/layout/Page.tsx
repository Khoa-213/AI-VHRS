import type { ReactNode } from 'react'
import CustomerFrame from './CustomerFrame'

interface PageProps {
  /** Max content width in px. */
  width?: number
  label: string
  children: ReactNode
  /** Off by default: review, deposit, delivery and payment are the order flow. */
  footer?: boolean
}

/** Customer frame shared by review, delivery, payment and account recovery. */
export default function Page({ width = 1320, label, children, footer = false }: PageProps) {
  return (
    <CustomerFrame label={label} className="customer-order-frame" footer={footer}>
      <div className="vh-wrap" style={{ maxWidth: width }}>{children}</div>
    </CustomerFrame>
  )
}
