import { useState } from 'react'
import { useT } from '../../i18n'
import { templateCardUrl, type Template } from '../../services/orders'

/** What the card shows: the customer's words drawn now, the template's stored sample, or nothing. */
type Stage = 'live' | 'stored' | 'none'

/**
 * One writing style with a picture of the customer's own words (their first line), cut to the words. Every picture is
 * drawn by the backend from the strokes the robot follows; the browser never draws letters with a font of its own.
 * When the live picture fails (the server is waking up, a character the style lacks) the template's stored sample is
 * shown and the style can still be picked. Only when that fails too is the card disabled: a style the backend cannot
 * draw at all cannot be sketched either.
 */
export default function TemplateCard({
  template, text, on, broken, onPick, onBroken,
}: {
  template: Template
  text: string
  on: boolean
  broken: boolean
  onPick: () => void
  onBroken: () => void
}) {
  const t = useT()
  const live = templateCardUrl(template.id, text)
  // What failed, and for which words: new words get a new try at the live picture.
  const [fallen, setFallen] = useState<{ url: string; stage: Stage } | null>(null)
  const stage: Stage = fallen?.url === live ? fallen.stage : 'live'

  const failed = () => {
    if (stage === 'live' && template.previewUrl) return setFallen({ url: live, stage: 'stored' })
    setFallen({ url: live, stage: 'none' })
    onBroken()
  }
  const src = stage === 'live' ? live : stage === 'stored' ? template.previewUrl : null

  return (
    <button className={`co-opt co-font${on ? ' on' : ''}${broken ? ' off' : ''}`} disabled={broken} onClick={onPick}>
      <span className="co-font-frame">
        {broken || !src ? (
          <span className="co-font-none">{t('co.templateNoPreview')}</span>
        ) : (
          <img key={src} src={src} alt={t('co.templateAlt', { name: template.name })} loading="lazy" onError={failed} />
        )}
      </span>
      <span className="co-font-name">{template.name}</span>
      <span className="co-opt-sub">{t(`tpl.${template.kind}`)}</span>
    </button>
  )
}
