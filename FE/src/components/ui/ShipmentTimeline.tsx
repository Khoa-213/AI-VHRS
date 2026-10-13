import { GHN_STATUS, PACK_STEPS, toneColor, type Tone } from '../../services/ghn'
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

const dayOf = (iso: string) =>
  new Date(iso).toLocaleDateString('en-GB', { weekday: 'short', day: '2-digit', month: 'short' })
const timeOf = (iso: string) =>
  new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })

/** Packing marks and GHN scans in one list, newest first, grouped by day. */
export default function ShipmentTimeline({ shipment, audience }: { shipment: Shipment; audience: 'customer' | 'staff' }) {
  const staff = audience === 'staff'
  const events: Event[] = [
    ...shipment.pack.map((m) => ({
      key: 'pack-' + m.id,
      at: m.at,
      title: PACK_STEPS.find((p) => p.id === m.id)?.label ?? m.id,
      tone: 'neutral' as Tone,
    })),
    ...shipment.logs.map((l, i) => ({
      key: `log-${i}-${l.status}`,
      at: l.at,
      title: staff ? GHN_STATUS[l.status].staff : GHN_STATUS[l.status].customer,
      place: l.place,
      code: staff ? l.status : undefined,
      tone: GHN_STATUS[l.status].tone,
    })),
  ].sort((a, b) => b.at.localeCompare(a.at))

  if (!events.length) {
    return (
      <div className="tl-empty">
        <b>No updates yet</b>
        <span>{staff ? 'Tick the packing steps below, then book the courier.' : 'Packing updates and courier scans will appear here.'}</span>
      </div>
    )
  }

  const days: { day: string; items: Event[] }[] = []
  for (const e of events) {
    const d = dayOf(e.at)
    const g = days[days.length - 1]
    if (g?.day === d) g.items.push(e)
    else days.push({ day: d, items: [e] })
  }

  return (
    <div className="tl" role="list" aria-label="Shipment updates">
      {days.map((g, gi) => (
        <section key={g.day} className="tl-day" role="listitem">
          <h3>{g.day}</h3>
          <ol>
            {g.items.map((e, i) => (
              <li key={e.key} className={gi === 0 && i === 0 ? 'on' : ''} style={{ ['--tone' as string]: toneColor[e.tone] }}>
                <time className="vh-mono" dateTime={e.at}>{timeOf(e.at)}</time>
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
