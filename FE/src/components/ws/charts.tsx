/** Bars per weekday. The tallest bar is drawn with the accent hatch and carries the tooltip. Colours come from the screen's accent. */
export function WeekBars({ values, second, labels, caption, unit }: { values: number[]; second?: number[]; labels: string[]; caption: string; unit: string }) {
  const max = Math.max(1, ...values, ...(second ?? []))
  const top = Math.max(...values)
  const hi = values.indexOf(top)
  const step = Math.max(1, Math.ceil(max / 3 / 5) * 5)
  const ceil = step * 3
  const y = (v: number) => 180 - (v / ceil) * 150
  const W = 620
  const slot = (W - 56) / values.length
  return (
    <svg viewBox="0 0 620 270" role="img" aria-label={caption} style={{ width: '100%', height: 'auto', color: 'var(--acc)' }}>
      <defs>
        <pattern id="ws-hatch" width="9" height="9" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width="9" height="9" fill="currentColor" />
          <path d="M0 0V9" stroke="#fff" strokeOpacity=".35" strokeWidth="2.2" />
        </pattern>
      </defs>
      <g stroke="#e6e4de" strokeDasharray="4 5">{[0, 1, 2, 3].map((i) => <path key={i} d={`M56 ${30 + i * 50}H610`} />)}</g>
      <g fill="#596269" fontSize="12" fontWeight="500">
        {[0, 1, 2, 3].map((i) => <text key={i} x="0" y={34 + i * 50}>{ceil - i * step}</text>)}
        {labels.map((l, i) => <text key={l + i} x={56 + slot * i + slot / 2 - 12} y="222">{l}</text>)}
      </g>
      {values.map((v, i) => {
        const w = second ? 26 : 48
        const x = 56 + slot * i + (slot - (second ? 56 : 48)) / 2
        const h = Math.max(4, 180 - y(v))
        const hatch = !second && i === hi && top > 0
        return <rect key={i} x={x} y={180 - h} width={w} height={h} rx={second ? 7 : 8} fill={hatch ? 'url(#ws-hatch)' : undefined} style={hatch ? undefined : { fill: 'var(--acc-soft)' }} />
      })}
      {second?.map((v, i) => {
        const x = 56 + slot * i + (slot - 56) / 2 + 30
        const h = Math.max(4, 180 - y(v))
        return <rect key={`s${i}`} x={x} y={180 - h} width="26" height={h} rx="7" fill="currentColor" />
      })}
      {!second && top > 0 && (() => {
        const cx = 56 + slot * hi + slot / 2
        const tx = Math.min(Math.max(cx, 80), W - 80)
        return (
          <g>
            <rect x={tx - 62} y="-6" width="124" height="46" rx="10" fill="#e8e6e0" />
            <circle cx={tx - 44} cy="16" r="6" fill="currentColor" />
            <text x={tx - 30} y="14" fill="#201f23" fontSize="12" fontWeight="700">{top} {unit}</text>
            <text x={tx - 30} y="30" fill="#596269" fontSize="11">{labels[hi]}</text>
          </g>
        )
      })()}
    </svg>
  )
}

export interface Slice {
  label: string
  value: number
  color: string
}

/** Donut with the total in the middle and a legend beside it. */
export function Donut({ slices, caption, centerLabel }: { slices: Slice[]; caption: string; centerLabel: string }) {
  const total = slices.reduce((a, s) => a + s.value, 0)
  const R = 68
  const C = 2 * Math.PI * R
  let off = 0
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 20 }}>
      <svg width="190" height="190" viewBox="0 0 190 190" role="img" aria-label={caption} style={{ color: 'var(--acc)' }}>
        <circle cx="95" cy="95" r={R} fill="none" stroke="#f0eeea" strokeWidth="30" />
        {total > 0 && slices.map((s) => {
          const len = (s.value / total) * C
          const el = (
            <circle key={s.label} cx="95" cy="95" r={R} fill="none" stroke={s.color} strokeWidth="30" strokeDasharray={`${len} ${C - len}`} strokeDashoffset={-off} transform="rotate(-90 95 95)" />
          )
          off += len
          return el
        })}
        <text x="95" y="98" textAnchor="middle" fontSize="30" fontWeight="700" fill="#201f23">{total}</text>
        <text x="95" y="118" textAnchor="middle" fontSize="12" fill="#596269">{centerLabel}</text>
      </svg>
      <div className="legend" style={{ flex: 1, minWidth: 140 }}>
        {slices.map((s) => <div key={s.label}><i style={{ background: s.color }} />{s.label}<b>{s.value}</b></div>)}
      </div>
    </div>
  )
}
