import type { CSSProperties, ReactNode } from 'react'
import { layoutById } from '../../constants/catalog'
import type { Layout, LayoutId, OrderSpec } from '../../types'
import { fontScale } from '../../utils/format'

interface PaperSheetProps {
  spec: Pick<OrderSpec, 'aspect' | 'paperColor' | 'inkColor' | 'font' | 'text' | 'img'>
  /** Height as a percentage of the parent (the parent needs a definite height). */
  height: string
  maxWidth?: string
  layout?: Layout | LayoutId
  /** Font size in cqw. Defaults to a size picked from the text length. */
  fs?: number
  shadow?: string
  /** Reveals the sheet from the left, 0 to 1 (used while the AI sketch renders). */
  reveal?: number
  style?: CSSProperties
  children?: ReactNode
}

/** A sheet of paper with the order's text or image on it, scaled with container query units. */
export default function PaperSheet({
  spec, height, maxWidth = '88%', layout, fs, shadow, reveal, style, children,
}: PaperSheetProps) {
  const L = typeof layout === 'object' ? layout : layoutById(layout)
  const size = fs ?? fontScale(spec.text.length || 12)
  return (
    <div
      className="vh-sheet"
      style={{ height, aspectRatio: spec.aspect, maxWidth, background: spec.paperColor, boxShadow: shadow, ...style }}
    >
      {L.frame && (
        <div className="vh-sheet-frame" style={{ inset: '5cqw', border: `3px double ${spec.inkColor}` }} />
      )}
      <div
        className="vh-sheet-body"
        style={{
          padding: L.pad,
          alignItems: L.alignItems,
          justifyContent: L.justify,
          clipPath: reveal !== undefined && reveal < 1 ? `inset(0 ${((1 - reveal) * 100).toFixed(1)}% 0 0)` : undefined,
        }}
      >
        {spec.img ? (
          <div className="vh-sheet-img" style={{ backgroundImage: `url("${spec.img}")` }} />
        ) : (
          <span
            className="vh-sheet-text"
            style={{ fontFamily: spec.font, fontSize: `${size}cqw`, textAlign: L.textAlign, color: spec.inkColor }}
          >
            {spec.text || '—'}
          </span>
        )}
      </div>
      {children}
    </div>
  )
}
