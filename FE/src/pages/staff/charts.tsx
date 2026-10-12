/** Small SVG charts for the staff dashboard. Colours come from CSS variables (--s1, --s2, --s3). */

export interface Slice {
  label: string
  value: number
  color: string
}

interface DonutProps {
  slices: Slice[]
  size?: number
  center: string
  caption: string
}

/** Donut with a 2px surface gap between segments. The title names the chart for screen readers. */
export function Donut({ slices, size = 168, center, caption }: DonutProps) {
  const total = slices.reduce((a, s) => a + s.value, 0) || 1
  const r = size / 2 - 14
  const c = 2 * Math.PI * r
  let offset = 0
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`${caption}: ${slices.map((s) => `${s.label} ${s.value}`).join(', ')}`}>
      <g transform={`rotate(-90 ${size / 2} ${size / 2})`}>
        {slices.map((s) => {
          const len = (s.value / total) * c
          const el = (
            <circle
              key={s.label}
              cx={size / 2}
              cy={size / 2}
              r={r}
              fill="none"
              stroke={s.color}
              strokeWidth={18}
              strokeDasharray={`${Math.max(0, len - 2)} ${c - Math.max(0, len - 2)}`}
              strokeDashoffset={-offset}
            >
              <title>{`${s.label}: ${s.value}`}</title>
            </circle>
          )
          offset += len
          return el
        })}
      </g>
      <text x="50%" y="48%" textAnchor="middle" className="sd-donut-num">{center}</text>
      <text x="50%" y="48%" dy="20" textAnchor="middle" className="sd-donut-cap">{caption}</text>
    </svg>
  )
}

interface SparkProps {
  values: number[]
  labels: string[]
  height?: number
}

/** One-series area line with an emphasised last point. */
export function Spark({ values, labels, height = 72 }: SparkProps) {
  const w = 280
  const pad = 6
  const max = Math.max(...values) * 1.1
  const min = 0
  const x = (i: number) => pad + (i * (w - pad * 2)) / (values.length - 1)
  const y = (v: number) => height - pad - ((v - min) / (max - min)) * (height - pad * 2)
  const line = values.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(' ')
  const area = `${line} L${x(values.length - 1)} ${height} L${x(0)} ${height} Z`
  const last = values.length - 1
  return (
    <svg viewBox={`0 0 ${w} ${height}`} className="sd-spark" role="img" aria-label={`Last 7 days: ${values.map((v, i) => `${labels[i]} ${v}`).join(', ')}`}>
      <path d={area} fill="var(--s1)" opacity="0.14" />
      <path d={line} fill="none" stroke="var(--s1)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
      {values.map((v, i) => (
        <circle key={i} cx={x(i)} cy={y(v)} r={i === last ? 4 : 8} fill={i === last ? 'var(--s1)' : 'transparent'} stroke={i === last ? 'var(--card)' : 'none'} strokeWidth="2">
          <title>{`${labels[i]}: ${v}`}</title>
        </circle>
      ))}
    </svg>
  )
}
