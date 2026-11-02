import { useEffect, useState } from 'react'
import { fetchStyledPreview, templatePreviewUrl, type Alignment } from '../services/orders'

/**
 * Preview image of the customer's words in a template, with the chosen alignment and letter height.
 * Falls back to the plain preview when the styled one fails, so the picture never disappears.
 */
export function useStyledPreview(templateId: number | null, text: string, alignment: Alignment | null, fontSizeMm: number | null) {
  const [src, setSrc] = useState<string | null>(null)

  useEffect(() => {
    if (templateId === null || !text.trim()) {
      setSrc(null)
      return
    }
    const ctl = new AbortController()
    let made: string | null = null
    fetchStyledPreview(templateId, text, alignment, fontSizeMm, ctl.signal)
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
  }, [templateId, text, alignment, fontSizeMm])

  return src
}
