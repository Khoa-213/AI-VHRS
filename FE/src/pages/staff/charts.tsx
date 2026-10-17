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
