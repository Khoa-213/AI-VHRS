import { useT } from '../../i18n'
import { templatePreviewUrl, type Template } from '../../services/orders'

/**
 * One writing style with a preview of the customer's own words. The preview is the top of a drawn A5 page, so the frame
 * shows just that part. When the backend cannot draw the style (an unsupported font) it cannot sketch it either, so the
 * card is disabled instead of showing a broken picture.
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
  return (
    <button className={`co-opt co-font${on ? ' on' : ''}${broken ? ' off' : ''}`} disabled={broken} onClick={onPick}>
      <span className="co-font-frame">
        {broken ? (
          <span className="co-font-none">{t('co.templateNoPreview')}</span>
        ) : (
          <img src={templatePreviewUrl(template.id, text)} alt={t('co.templateAlt', { name: template.name })} loading="lazy" onError={onBroken} />
        )}
      </span>
      <span className="co-font-name">{template.name}</span>
      <span className="co-opt-sub">{t(`tpl.${template.kind}`)}</span>
    </button>
  )
}
