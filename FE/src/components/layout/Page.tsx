import type { ReactNode } from 'react'
import CustomerFrame from './CustomerFrame'

interface PageProps {
  /** Max content width in px. */
  width?: number
  label: string
  children: ReactNode
}

/** Customer frame shared by review, delivery, payment and account recovery. */
export default function Page({ width = 1320, label, children }: PageProps) {
  return (
    <CustomerFrame label={label} className="customer-order-frame">
      <div className="vh-wrap" style={{ maxWidth: width }}>{children}</div>
    </CustomerFrame>
  )
}
