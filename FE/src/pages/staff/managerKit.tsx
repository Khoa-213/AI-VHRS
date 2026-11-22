import { CheckCircle, Info, PauseCircle, PencilLine, Warning, WarningOctagon, WifiSlash } from '@phosphor-icons/react'
import { useId, useState, type ReactNode } from 'react'
import { useT } from '../../i18n'
import type { RobotStatus } from '../../services/robot'

/**
 * Building blocks of the Manager screens in the Staff frame (`staff-ui.css`, `staff-theme.css`, `manager-ui.css`): panels,
 * workshop chips, the Staff period switch and the Staff line chart with its data table. Colours come from theme tokens only.
 */

/** Workshop chip tones (`ws.css`, re-coloured for dark mode by `staff-theme.css`), plus `navy` for the Staff accent. */
export type Tone = 'good' | 'warn' | 'bad' | 'info' | 'mute' | 'navy'

/** A panel with a heading, an optional one-line explanation and something on the right. */
export function Panel({ title, sub, aside, children, className }: { title: string; sub?: string; aside?: ReactNode; children: ReactNode; className?: string }) {
  const id = useId()
  return (
    <section className={`panel${className ? ` ${className}` : ''}`} aria-labelledby={id}>
      <div className="ph">
        <div className="mgr-ph-text"><h2 id={id}>{title}</h2>{sub && <p className="sub">{sub}</p>}</div>
        {aside}
      </div>
      {children}
    </section>
  )
}

/** A chip; with an icon the icon replaces the dot, so state is never colour alone. */
export function Chip({ tone = 'mute', icon, children }: { tone?: Tone; icon?: ReactNode; children: ReactNode }) {
  return <span className={`chip mgr-chip ${tone}${icon ? ' ico' : ''}`}>{icon}{children}</span>
}

const STATE_TONE: Record<RobotStatus['state'], Tone> = {
  OFFLINE: 'mute', IDLE: 'good', PREPARING: 'info', WRITING: 'navy', PAUSED_SAFE: 'warn', DANGER: 'bad',
}

/** Robot state with an icon and the word. */
export function StateChip({ state }: { state: RobotStatus['state'] }) {
  const t = useT()
  const icon = state === 'DANGER' ? <WarningOctagon size={14} weight="fill" aria-hidden />
    : state === 'OFFLINE' ? <WifiSlash size={14} aria-hidden />
      : state === 'PAUSED_SAFE' ? <PauseCircle size={14} aria-hidden />
        : state === 'WRITING' ? <PencilLine size={14} aria-hidden />
          : <CheckCircle size={14} aria-hidden />
  return <Chip tone={STATE_TONE[state]} icon={icon}>{t(`rb.state.${state}`)}</Chip>
}

const LEVEL_TONE: Tone[] = ['mute', 'mute', 'info', 'warn', 'bad']

/** Alert level 1 to 4 with an icon and the word. Level 4 is red: press the physical E-Stop. */
export function LevelChip({ level }: { level: number }) {
  const t = useT()
  const n = Math.min(4, Math.max(1, Math.round(level)))
  const icon = n >= 4 ? <WarningOctagon size={14} weight="fill" aria-hidden /> : n >= 2 ? <Warning size={14} aria-hidden /> : <Info size={14} aria-hidden />
  return <Chip tone={LEVEL_TONE[n]} icon={icon}>{t(`mgr.level.${n}`)}</Chip>
}

/** The Staff period switch (`.staff-period`). */
export function Period<T extends string | number | boolean>({ options, value, onChange, label, text }: {
  options: readonly T[]; value: T; onChange: (v: T) => void; label: string; text: (v: T) => string
}) {
  return (
    <div className="staff-period" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={String(o)} type="button" className={value === o ? 'on' : ''} aria-pressed={value === o} onClick={() => onChange(o)}>{text(o)}</button>
      ))}
    </div>
  )
}

export interface Point { label: string; long: string; value: number; readout: string }

/**
 * The Staff dashboard's line chart (ink line over the accent area). Each point takes focus and shows its value above the
 * chart; `Show table` opens the same numbers, so the chart is never the only way to read them.
 */
export function LineChart({ points, caption, column, locale }: { points: Point[]; caption: string; column: string; locale: string }) {
  const t = useT()
  const [hi, setHi] = useState<number | null>(null)
  const n = points.length
  const max = Math.max(...points.map((p) => p.value), 0)
  const min = Math.min(...points.map((p) => p.value), 0)
  const top = max <= 0 ? 2 : max
  const span = top - min || 1
  const x = (i: number) => (n === 1 ? 360 : 40 + (i * 640) / (n - 1))
  const y = (v: number) => 194 - ((v - min) / span) * 148
  const line = `M${points.map((p, i) => `${x(i)},${y(p.value)}`).join(' L')}`
  const every = Math.max(1, Math.ceil(n / 7))
  const shown = hi === null ? null : points[hi]
  const scale = (k: number) => top - (span * k) / 2
  return (
    <div className="mgr-chart">
      <p className="readout" aria-live="polite">{shown ? `${shown.long}: ${shown.readout}` : ' '}</p>
      <svg viewBox="0 0 720 240" role="group" aria-label={caption}>
        {[0, 1, 2].map((k) => (
          <g key={k}>
            <path d={`M40 ${46 + k * 74}H680`} stroke="var(--line)" />
            <text x="0" y={50 + k * 74} fill="var(--ink3)" fontSize="11">{Math.round(scale(k)).toLocaleString(locale, { notation: 'compact' })}</text>
          </g>
        ))}
        {n > 1 && <path d={`${line} L${x(n - 1)},${y(min)} L${x(0)},${y(min)} Z`} fill="var(--acc-soft)" />}
        {n > 1 && <path d={line} fill="none" stroke="var(--ink)" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />}
        {points.map((p, i) => (i % every === 0 || i === n - 1
          ? <text key={`l${i}`} x={x(i)} y="226" textAnchor="middle" fontSize="11" fill="var(--ink3)">{p.label}</text>
          : null))}
        {points.map((p, i) => (
          <circle
            key={i}
            cx={x(i)} cy={y(p.value)} r={hi === i ? 6 : 4}
            className={hi === i ? 'on' : undefined}
            fill="var(--ink)"
            tabIndex={0}
            aria-label={`${p.long}: ${p.readout}`}
            onMouseEnter={() => setHi(i)} onMouseLeave={() => setHi(null)}
            onFocus={() => setHi(i)} onBlur={() => setHi(null)}
          />
        ))}
      </svg>
      <details className="staff-chart-data">
        <summary>{t('adm.viz.table')}</summary>
        <table>
          <caption className="staff-sr">{caption}</caption>
          <thead><tr><th scope="col">{t('mgr.rp.period')}</th><th scope="col">{column}</th></tr></thead>
          <tbody>{points.map((p, i) => <tr key={i}><th scope="row">{p.long}</th><td>{p.readout}</td></tr>)}</tbody>
        </table>
      </details>
    </div>
  )
}
