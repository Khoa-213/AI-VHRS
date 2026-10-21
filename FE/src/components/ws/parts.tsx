import { DotsThree } from '@phosphor-icons/react'
import type { ReactNode } from 'react'

/** Summary card: a round icon, a title, a big number and a small note. */
export function Kpi({
  icon, tone, title, value, badge, badgeTone, note, to,
}: {
  icon: ReactNode
  tone?: 'a' | 'b' | 'p' | 't'
  title: string
  value: string | number
  badge?: string
  badgeTone?: 'up' | 'dn' | 'ac'
  note?: string
  to?: string
}) {
  return (
    <section className="k" aria-label={title}>
      <div className="top">
        <span className={`ico${tone ? ' ' + tone : ''}`}>{icon}</span>
        <h3>{title}</h3>
        {to ? <a className="more" href={to} aria-label={title}><DotsThree size={18} weight="bold" aria-hidden /></a> : null}
      </div>
      <div className="num">
        <b>{value}</b>
        {badge && <span className={`badge${badgeTone === 'dn' ? ' dn' : badgeTone === 'ac' ? ' ac' : ''}`}>{badge}</span>}
        {note && <span>{note}</span>}
      </div>
    </section>
  )
}

/** Name initials for an avatar. */
export const initials = (name: string) => name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join('').toUpperCase() || '?'

const AVATAR_TONES = ['', 'g', 'b', 't']
/** A stable avatar colour per name. */
export const avatarTone = (name: string) => AVATAR_TONES[[...name].reduce((a, c) => a + c.charCodeAt(0), 0) % AVATAR_TONES.length]
