import { useState } from 'react'
import { useT } from '../../i18n'
import type { Paper } from '../../services/orders'
import './paper-photo.css'

type SelectedPaper = Pick<Paper, 'name' | 'imageUrl'>

/** Catalog photos can include borders, stacks and perspective. They are references, not writing coordinates. */
export function PaperThumb({ photo, small = false }: { photo: string | null; small?: boolean }) {
  const [failed, setFailed] = useState<string | null>(null)
  const visible = !!photo && failed !== photo
  return (
    <span className={`co-paper-thumb${small ? ' co-paper-thumb--sm' : ''}${visible ? '' : ' co-paper-thumb--empty'}`} aria-hidden="true">
      {visible && <img key={photo} src={photo} alt="" loading="lazy" onError={() => setFailed(photo)} />}
    </span>
  )
}

/** Keep the full catalog photo separate from the backend's faithful drawing and watermark. */
export default function PaperPhoto({ paper }: { paper?: SelectedPaper | null }) {
  const t = useT()
  const [failed, setFailed] = useState<string | null>(null)
  if (!paper) return null
  const label = <><PaperThumb photo={paper.imageUrl} small /><span>{t('co.paperShown')} <strong>{paper.name}</strong></span></>
  if (!paper.imageUrl) return <div className="co-paper-label">{label}</div>
  return (
    <details key={paper.imageUrl} className="co-paper-photo">
      <summary>{label}</summary>
      {failed === paper.imageUrl ? (
        <p className="co-hint" role="status">{t('co.paperPhotoFailed')}</p>
      ) : (
        <img className="co-paper-photo-full" src={paper.imageUrl} alt={paper.name} loading="lazy" onError={() => setFailed(paper.imageUrl)} />
      )}
    </details>
  )
}
