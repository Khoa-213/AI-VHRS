import { useEffect, useState } from 'react'
import { fetchStyledPreview, templatePreviewUrl, type Alignment, type SheetSize, type TextLayout } from '../services/orders'

/**
 * Preview image of the customer's words in a template: the first page as the robot would write it, with the chosen
 * alignment, letter height, placement on the sheet (`layoutJson`: the layout as JSON, so an equal layout does not ask
 * again) and sheet size. Falls back to the plain preview when the styled one fails, so the picture never disappears.
 */
export function useStyledPreview(
  templateId: number | null, text: string, alignment: Alignment | null, fontSizeMm: number | null,
  layoutJson: string | null = null, paperSize: SheetSize = 'A5',
) {
  const [src, setSrc] = useState<string | null>(null)

  useEffect(() => {
    if (templateId === null || !text.trim()) {
      setSrc(null)
      return
    }
    const ctl = new AbortController()
    let made: string | null = null
    const layout = layoutJson ? (JSON.parse(layoutJson) as TextLayout) : null
    fetchStyledPreview(templateId, text, alignment, fontSizeMm, ctl.signal, layout, paperSize)
      .then((blob) => {
        made = URL.createObjectURL(blob)
        setSrc(made)
      })
      .catch(() => {
        if (!ctl.signal.aborted) setSrc(templatePreviewUrl(templateId, text))
      })
    return () => {
      ctl.abort()
      if (made) URL.revokeObjectURL(made)
    }
  }, [templateId, text, alignment, fontSizeMm, layoutJson, paperSize])

  return src
}
