import { useEffect, useState } from 'react'
import { useT } from '../../i18n'
import { getInputFileUrl, templatePreviewUrl, type CanvasData, type Order, type OrderInput } from '../../services/orders'
import './preview.css'

/** The drawn strokes as a vector sheet. Coordinates are millimetres, so the viewBox is the sheet. */
export function StrokeSheet({ canvas, color = '#1b2440', label }: { canvas: CanvasData; color?: string; label: string }) {
  const pts = canvas.strokes.flatMap((s) => s.points)
  const w = canvas.width_mm ?? Math.max(105, Math.ceil(Math.max(0, ...pts.map((p) => p.x)) + 10))
  const h = canvas.height_mm ?? Math.max(148, Math.ceil(Math.max(0, ...pts.map((p) => p.y)) + 10))
  return (
    <svg className="opv-svg" viewBox={`0 0 ${w} ${h}`} role="img" aria-label={label} style={{ aspectRatio: `${w} / ${h}` }}>
      {canvas.strokes.map((s, i) =>
        s.points.length > 1 ? (
          <polyline
            key={i}
            points={s.points.map((p) => `${p.x},${p.y}`).join(' ')}
            fill="none"
            stroke={color}
            strokeWidth={0.6}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        ) : null,
      )}
    </svg>
  )
}

/** A photo or PDF the customer uploaded, through a temporary link. PDFs have no thumbnail. */
function Original({ orderId, input }: { orderId: number; input: OrderInput }) {
  const t = useT()
  const [url, setUrl] = useState<string | null>(null)
  const pdf = input.mime === 'application/pdf'
  useEffect(() => {
    if (pdf) return
    let live = true
    getInputFileUrl(orderId, input.id).then((u) => live && setUrl(u)).catch(() => undefined)
    return () => {
      live = false
    }
  }, [orderId, input.id, pdf])
  if (pdf) return <span className="opv-note">{t('opv.pdf')}</span>
  return url ? <img className="opv-img" src={url} alt={t('opv.original')} /> : <span className="opv-note">{t('opv.loading')}</span>
}

interface Props {
  order: Order
  /** Sketch pages from the workshop. When present they replace the customer's own input. */
  sketchUrls?: string[]
  inkColor?: string | null
}

/** What the order will be written from: the workshop's sketch once there is one, else the customer's own input. */
export default function OrderPreview({ order, sketchUrls, inkColor }: Props) {
  const t = useT()
  const text = order.inputs.find((i) => i.kind === 'TEXT_CONTENT')
  const canvas = order.inputs.find((i) => i.kind === 'CANVAS')
  const originals = order.inputs.filter((i) => i.kind === 'ORIGINAL_IMAGE')

  let body
  if (sketchUrls?.length) {
    body = sketchUrls.map((u, i) => <img key={u} className="opv-img" src={u} alt={t('opv.sketch', { n: i + 1 })} />)
  } else {
    const typed = text?.templateId && text.text
      ? <img key="t" className="opv-img" src={templatePreviewUrl(text.templateId, text.text)} alt={t('opv.template')} />
      : text?.text ? <p key="t" className="opv-text">{text.text}</p> : null
    const drawn = canvas?.canvas ? <StrokeSheet key="c" canvas={canvas.canvas} color={inkColor ?? undefined} label={t('opv.drawing')} /> : null
    const photos = originals.map((o) => <Original key={o.id} orderId={order.id} input={o} />)
    const parts = [typed, drawn, ...photos].filter(Boolean)
    body = parts.length ? parts : <span className="opv-note">{t('opv.empty')}</span>
  }
  return <div className="opv">{body}</div>
}
