import { useT } from '../../i18n'
import { ApiError } from '../../services/api'
import type { Job } from '../../services/async'
import { errText, orderErrorKey } from '../../services/orders'

/** Shared loading and retry feedback without reporting an API failure as an empty job queue. */
export default function JobFeedback({ loading, error, retry }: { loading: boolean; error: unknown; retry: Job }) {
  const t = useT()
  if (error) return <div className="wk-block tech-feedback" role="alert">
    <p className="lg-error">{error instanceof ApiError && error.status === 404 ? t('td.api.notFound') : errText(t, orderErrorKey(error))}</p>
    <button type="button" className="sd-btn" onClick={() => void retry()}>{t('td.api.reload')}</button>
  </div>
  return loading ? <p className="sub" role="status">{t('co.loading')}</p> : null
}
