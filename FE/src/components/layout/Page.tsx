import type { ReactNode } from 'react'
import SiteFooter from './SiteFooter'
import SiteHeader from './SiteHeader'

interface PageProps {
  /** Max content width in px. */
  width?: number
  label: string
  children: ReactNode
}

/** Header, gradient shell and footer shared by every order page. */
export default function Page({ width = 1320, label, children }: PageProps) {
  return (
    <>
      <SiteHeader />
      <main className="vh-main" data-screen-label={label}>
        <div className="vh-wrap" style={{ maxWidth: width }}>{children}</div>
      </main>
      <SiteFooter />
    </>
  )
}
