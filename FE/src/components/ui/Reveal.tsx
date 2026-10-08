import type { CSSProperties, ReactNode } from 'react'
import { useReveal } from '../../hooks/useReveal'

interface RevealProps {
  className?: string
  style?: CSSProperties
  as?: 'div' | 'a'
  href?: string
  delay?: number
  dur: string
  children: ReactNode
}

export default function Reveal({
  className,
  style,
  as: Tag = 'div',
  href,
  delay = 0,
  dur,
  children,
}: RevealProps) {
  const { ref, seen } = useReveal<HTMLDivElement & HTMLAnchorElement>()
  const merged = {
    opacity: seen ? 1 : 0,
    transform: seen ? 'translateY(0px)' : 'translateY(40px)',
    '--d': `${delay}s`,
    '--dur': dur,
    ...style,
  } as CSSProperties
  return (
    <Tag ref={ref} href={href} className={className} style={merged}>
      {children}
    </Tag>
  )
}
