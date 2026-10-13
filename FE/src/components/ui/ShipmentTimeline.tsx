import { useLocale, useT } from '../../i18n'
import { GHN_STATUS, toneColor, type Tone } from '../../services/ghn'
import type { Shipment } from '../../types'
import './shipment.css'

interface Event {
  key: string
  at: string
  title: string
  place?: string
  code?: string
  tone: Tone
}

const dayOf = (iso: string, locale: string) =>
  new Date(iso).toLocaleDateString(locale, { weekday: 'short', day: '2-digit', month: 'short' })
const timeOf = (iso: string, locale: string) =>
  new Date(iso).toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' })

/** Packing marks and GHN scans in one list, newest first, grouped by day. */
export default function ShipmentTimeline({ shipment, audience }: { shipment: Shipment; audience: 'customer' | 'staff' }) {
  const staff = audience === 'staff'
  const t = useT()
  const locale = useLocale()
  const events: Event[] = [
    ...shipment.pack.map((m) => ({
      key: 'pack-' + m.id,
      at: m.at,
      title: t(`pack.${m.id}`),
      tone: 'neutral' as Tone,
    })),
    ...shipment.logs.map((l, i) => ({
      key: `log-${i}-${l.status}`,
      at: l.at,
      title: t(`ghn.${l.status}.${staff ? 'staff' : 'customer'}`),
      place: l.place,
      code: staff ? l.status : undefined,
      tone: GHN_STATUS[l.status].tone,
    })),
  ].sort((a, b) => b.at.localeCompare(a.at))

  if (!events.length) {
    return (
      <div className="tl-empty">
        <b>{t('tl.emptyTitle')}</b>
        <span>{t(staff ? 'tl.emptyStaff' : 'tl.emptyCustomer')}</span>
      </div>
    )
  }

  const days: { day: string; items: Event[] }[] = []
  for (const e of events) {
    const d = dayOf(e.at, locale)
    const g = days[days.length - 1]
    if (g?.day === d) g.items.push(e)
    else days.push({ day: d, items: [e] })
  }

  return (
    <div className="tl" role="list" aria-label={t('tl.aria')}>
      {days.map((g, gi) => (
        <section key={g.day} className="tl-day" role="listitem">
          <h3>{g.day}</h3>
          <ol>
            {g.items.map((e, i) => (
              <li key={e.key} className={gi === 0 && i === 0 ? 'on' : ''} style={{ ['--tone' as string]: toneColor[e.tone] }}>
                <time className="vh-mono" dateTime={e.at}>{timeOf(e.at, locale)}</time>
                <div>
                  <b>{e.title}</b>
                  {e.place && <span>{e.place}</span>}
                  {e.code && <code className="vh-mono">{e.code}</code>}
                </div>
              </li>
            ))}
          </ol>
        </section>
      ))}
    </div>
  )
}
