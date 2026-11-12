import { ArrowDown, ArrowRight, ArrowUp, CheckCircle, Minus, WarningCircle, XCircle } from '@phosphor-icons/react'
import { useId, useState, type CSSProperties, type ReactNode } from 'react'
import { useT } from '../../i18n'
import { Link } from '../../router/router'

/**
 * Charts and tiles for the Admin screens. They are drawn with HTML and CSS from the app's theme tokens (`admin-ui.css`), so
 * dark and light follow the theme toggle. Marks are thin, data ends are rounded, fills are separated by a gap, the grid is
 * quiet, text never wears a series colour, and every chart has a table view and a hover or focus readout.
 */

export type Tone = 'good' | 'warn' | 'bad' | 'mute' | 'accent'

/** State is never colour alone: each tone carries an icon and a word next to it. */
export function StateMark({ tone, label }: { tone: Tone; label: string }) {
  const icon = tone === 'good' ? <CheckCircle size={16} weight="fill" aria-hidden />
    : tone === 'bad' ? <XCircle size={16} weight="fill" aria-hidden />
      : tone === 'warn' ? <WarningCircle size={16} weight="fill" aria-hidden />
        : <span className="adm-dot" aria-hidden />
  return <span className={`adm-state adm-${tone}`}>{icon}{label}</span>
}

export function Chip({ tone = 'mute', children }: { tone?: Tone; children: ReactNode }) {
  return <span className={`adm-chip adm-${tone}`}>{children}</span>
}

/** The change a tile reports: direction, one short phrase, and whether it is good, bad or neutral news. */
export interface Delta { dir: 'up' | 'down' | 'flat'; text: string; tone: Tone }

function DeltaArrow({ dir }: { dir: Delta['dir'] }) {
  if (dir === 'up') return <ArrowUp size={12} weight="bold" aria-hidden />
  if (dir === 'down') return <ArrowDown size={12} weight="bold" aria-hidden />
  return <Minus size={12} weight="bold" aria-hidden />
}

/** One number with its name and, when there is something to compare with, how it changed. Can link to where it is managed. */
export function Kpi({ icon, label, value, hint, to, delta }: { icon: ReactNode; label: string; value: ReactNode; hint?: string; to?: string; delta?: Delta }) {
  const arrow = delta ? <DeltaArrow dir={delta.dir} /> : null
  const body = (
    <>
      <div className="adm-kpi-top">
        <span className="adm-kpi-ico" aria-hidden>{icon}</span>
        {delta && <span className={`adm-delta adm-${delta.tone}`}>{arrow}{delta.text}</span>}
      </div>
      <b className="adm-kpi-value">{value}</b>
      <span className="adm-kpi-label">{label}</span>
      {hint && <span className="adm-kpi-hint">{hint}</span>}
    </>
  )
  return to ? <Link to={to} className="adm-kpi adm-kpi--link">{body}</Link> : <div className="adm-kpi">{body}</div>
}

/** A card with a title and an optional one-line explanation, so each block says what it shows. */
export function Card({ title, sub, aside, children, id }: { title: string; sub?: string; aside?: ReactNode; children: ReactNode; id?: string }) {
  const hid = useId()
  return (
    <section className="adm-card" aria-labelledby={id ?? hid}>
      <div className="adm-card-head">
        <div><h2 id={id ?? hid}>{title}</h2>{sub && <p>{sub}</p>}</div>
        {aside}
      </div>
      {children}
    </section>
  )
}

export interface Segment { key: string; label: string; value: number; tone: Tone }

/**
 * Horizontal stacked bars, one row per group (here: one per role, split by account status). Segments are separated by a gap
 * and drawn in the status colours; the legend is always shown, and the total is written at the end of each row.
 */
export function StackedRows({ rows, legend, caption }: { rows: { key: string; label: string; segments: Segment[] }[]; legend: { label: string; tone: Tone }[]; caption: string }) {
  const t = useT()
  const [tip, setTip] = useState<string | null>(null)
  const max = Math.max(1, ...rows.map((r) => r.segments.reduce((a, s) => a + s.value, 0)))
  const [table, setTable] = useState(false)
  return (
    <div className="adm-viz">
      <div className="adm-legend" aria-hidden={false}>
        {legend.map((l) => <span key={l.label}><i className={`adm-swatch adm-${l.tone}`} />{l.label}</span>)}
        <button type="button" className="adm-link" onClick={() => setTable(!table)} aria-pressed={table}>{t(table ? 'adm.viz.chart' : 'adm.viz.table')}</button>
      </div>
      {table ? (
        <table className="adm-table-view">
          <caption className="adm-sr">{caption}</caption>
          <thead><tr><th scope="col" />{legend.map((l) => <th key={l.label} scope="col">{l.label}</th>)}</tr></thead>
          <tbody>{rows.map((r) => <tr key={r.key}><th scope="row">{r.label}</th>{r.segments.map((s) => <td key={s.key}>{s.value}</td>)}</tr>)}</tbody>
        </table>
      ) : (
        <div className="adm-rows" role="img" aria-label={caption}>
          {rows.map((r) => {
            const total = r.segments.reduce((a, s) => a + s.value, 0)
            return (
              <div key={r.key} className="adm-row">
                <span className="adm-row-label">{r.label}</span>
                <div className="adm-row-bar" style={{ width: `${(total / max) * 100}%` }}>
                  {r.segments.filter((s) => s.value > 0).map((s) => (
                    <button
                      key={s.key}
                      type="button"
                      className={`adm-seg adm-${s.tone}`}
                      style={{ flexGrow: s.value }}
                      aria-label={`${r.label}, ${s.label}: ${s.value}`}
                      onMouseEnter={() => setTip(`${r.label} · ${s.label}: ${s.value}`)}
                      onFocus={() => setTip(`${r.label} · ${s.label}: ${s.value}`)}
                      onMouseLeave={() => setTip(null)}
                      onBlur={() => setTip(null)}
                    />
                  ))}
                </div>
                <b className="adm-row-total">{total}</b>
              </div>
            )
          })}
          <div className="adm-tip" role="status" aria-live="polite">{tip ?? t('adm.viz.hover')}</div>
        </div>
      )}
    </div>
  )
}

/**
 * Columns per day (one series, one colour). Three quiet grid lines, the busiest day is named, and hovering or focusing a
 * column shows its day and count. `Table view` lists the same numbers.
 */
export function DayColumns({ days, label, unit, locale, caption }: { days: { date: string; count: number }[]; label: string; unit: string; locale: string; caption: string }) {
  const t = useT()
  const [active, setActive] = useState<number | null>(null)
  const [table, setTable] = useState(false)
  const top = Math.max(...days.map((d) => d.count), 0)
  const step = Math.max(1, Math.ceil(top / 3))
  const ceil = step * 3
  const fmtDay = (iso: string, long = false) => new Date(`${iso}T00:00:00`).toLocaleDateString(locale, long ? { weekday: 'long', day: 'numeric', month: 'long' } : { day: 'numeric', month: 'numeric' })
  const busiest = top > 0 ? days.reduce((a, d) => (d.count > a.count ? d : a), days[0]) : null
  const shown = active != null ? days[active] : null

  return (
    <div className="adm-viz">
      <div className="adm-legend">
        <span className="adm-legend-note">{shown ? `${fmtDay(shown.date, true)}: ${shown.count} ${unit}` : busiest ? t('adm.viz.busiest', { day: fmtDay(busiest.date, true), n: busiest.count }) : t('adm.viz.quiet')}</span>
        <button type="button" className="adm-link" onClick={() => setTable(!table)} aria-pressed={table}>{t(table ? 'adm.viz.chart' : 'adm.viz.table')}</button>
      </div>
      {table ? (
        <table className="adm-table-view">
          <caption className="adm-sr">{caption}</caption>
          <thead><tr><th scope="col">{t('adm.viz.day')}</th><th scope="col">{label}</th></tr></thead>
          <tbody>{days.map((d) => <tr key={d.date}><th scope="row">{fmtDay(d.date, true)}</th><td>{d.count}</td></tr>)}</tbody>
        </table>
      ) : (
        <div className="adm-cols" role="img" aria-label={caption}>
          <div className="adm-cols-grid" aria-hidden>
            {[3, 2, 1, 0].map((i) => <div key={i} className="adm-cols-line"><span>{i * step}</span></div>)}
          </div>
          <div className="adm-cols-plot">
            {days.map((d, i) => (
              <button
                key={d.date}
                type="button"
                className={`adm-col${active === i ? ' on' : ''}${busiest && d.date === busiest.date ? ' top' : ''}`}
                aria-label={`${fmtDay(d.date, true)}: ${d.count} ${unit}`}
                onMouseEnter={() => setActive(i)}
                onFocus={() => setActive(i)}
                onMouseLeave={() => setActive(null)}
                onBlur={() => setActive(null)}
              >
                <span className="adm-col-bar" style={{ height: `${ceil ? (d.count / ceil) * 100 : 0}%`, '--i': i } as CSSProperties}>
                  {(active === i || (active === null && busiest && d.date === busiest.date)) && <span className="adm-col-val">{d.count}</span>}
                </span>
              </button>
            ))}
          </div>
          <div className="adm-cols-x" aria-hidden>
            {days.map((d, i) => <span key={d.date}>{i % 2 === days.length % 2 ? fmtDay(d.date) : ''}</span>)}
          </div>
        </div>
      )}
    </div>
  )
}

/** A ring that shows part of a whole (robots online of all robots), with the numbers in the middle. */
export function Ring({ value, total, label, tone = 'accent' }: { value: number; total: number; label: string; tone?: Tone }) {
  const R = 52
  const C = 2 * Math.PI * R
  const share = total > 0 ? Math.min(1, value / total) : 0
  return (
    <div className="adm-ring">
      <svg viewBox="0 0 130 130" role="img" aria-label={`${label}: ${value} / ${total}`}>
        <circle className="adm-ring-track" cx="65" cy="65" r={R} fill="none" strokeWidth="12" />
        {share > 0 && <circle className={`adm-ring-fill adm-${tone}`} style={{ '--circ': C } as CSSProperties} cx="65" cy="65" r={R} fill="none" strokeWidth="12" strokeLinecap="round" strokeDasharray={`${share * C} ${C}`} transform="rotate(-90 65 65)" />}
      </svg>
      <div className="adm-ring-mid"><b>{value}<small> / {total}</small></b><span>{label}</span></div>
    </div>
  )
}

/** A line the person should act on: what is wrong, why it matters, and the button that fixes it. */
export function Attention({ tone, title, body, to, cta }: { tone: Tone; title: string; body?: string; to?: string; cta?: string }) {
  return (
    <div className={`adm-attn adm-${tone}`}>
      <div className="adm-attn-text"><StateMark tone={tone} label={title} />{body && <p>{body}</p>}</div>
      {to && cta && <Link to={to} className="adm-attn-cta">{cta}<ArrowRight size={16} aria-hidden /></Link>}
    </div>
  )
}

/** A big, plain shortcut: icon, what it does, and in a few words why. */
export function Shortcut({ to, icon, title, body }: { to: string; icon: ReactNode; title: string; body: string }) {
  return (
    <Link to={to} className="adm-short">
      <span className="adm-short-ico" aria-hidden>{icon}</span>
      <span className="adm-short-text"><b>{title}</b><span>{body}</span></span>
      <ArrowRight size={18} aria-hidden className="adm-short-go" />
    </Link>
  )
}

export interface Slice { key: string; label: string; value: number; color: string; note?: string }

/**
 * A ring of parts of a whole (accounts by role). Slices are separated by a gap, the total is in the middle, and the legend names
 * every part with its number and share, so colour is never the only way to read it. Hovering or focusing a legend row lights its
 * slice. `Show table` lists the same numbers.
 */
export function Donut({ slices, centerLabel, caption }: { slices: Slice[]; centerLabel: string; caption: string }) {
  const t = useT()
  const [on, setOn] = useState<string | null>(null)
  const [table, setTable] = useState(false)
  const total = slices.reduce((a, x) => a + x.value, 0)
  const R = 66
  const C = 2 * Math.PI * R
  const GAP = 3
  let off = 0
  const arcs = slices.filter((x) => x.value > 0).map((x) => {
    const len = (x.value / total) * C
    const el = { ...x, len: Math.max(0, len - GAP), off }
    off += len
    return el
  })
  return (
    <div className="adm-viz">
      <div className="adm-legend"><button type="button" className="adm-link" style={{ marginLeft: 'auto' }} onClick={() => setTable(!table)} aria-pressed={table}>{t(table ? 'adm.viz.chart' : 'adm.viz.table')}</button></div>
      {table ? (
        <table className="adm-table-view">
          <caption className="adm-sr">{caption}</caption>
          <thead><tr><th scope="col" /><th scope="col">{t('adm.viz.count')}</th></tr></thead>
          <tbody>{slices.map((x) => <tr key={x.key}><th scope="row">{x.label}</th><td>{x.value}</td></tr>)}</tbody>
        </table>
      ) : (
        <div className="adm-donut">
          <div className="adm-donut-svg">
            <svg viewBox="0 0 176 176" role="img" aria-label={caption}>
              <circle cx="88" cy="88" r={R} fill="none" stroke="var(--fx-06)" strokeWidth="22" />
              {arcs.map((x) => (
                <circle
                  key={x.key}
                  cx="88"
                  cy="88"
                  r={R}
                  fill="none"
                  data-arc
                  style={{ stroke: x.color, '--circ': C } as CSSProperties}
                  strokeWidth={on === x.key ? 26 : 22}
                  strokeDasharray={`${x.len} ${C - x.len}`}
                  strokeDashoffset={-x.off}
                  transform="rotate(-90 88 88)"
                  opacity={on && on !== x.key ? 0.35 : 1}
                />
              ))}
            </svg>
            <div className="adm-donut-mid"><b>{total}</b><span>{centerLabel}</span></div>
          </div>
          <ul className="adm-donut-legend">
            {slices.map((x) => (
              <li key={x.key}>
                <button
                  type="button"
                  className={on === x.key ? 'on' : ''}
                  onMouseEnter={() => setOn(x.key)}
                  onFocus={() => setOn(x.key)}
                  onMouseLeave={() => setOn(null)}
                  onBlur={() => setOn(null)}
                >
                  <i style={{ background: x.color }} aria-hidden />
                  <span>{x.label}{x.note && <em> · {x.note}</em>}</span>
                  <b>{x.value}<em> {total ? Math.round((x.value / total) * 100) : 0}%</em></b>
                  <span className="adm-donut-share" aria-hidden><span style={{ width: `${total ? (x.value / total) * 100 : 0}%`, background: x.color }} /></span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
