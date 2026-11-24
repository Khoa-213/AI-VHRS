import { useEffect, useRef, useState } from 'react'
import { Clock, Info, Sparkle, X } from '@phosphor-icons/react'
import { useLocale, useT } from '../../../i18n'
import { ApiError } from '../../../services/api'
import { acceptAiPolicy, aiChatPolicy, type AiPolicy } from '../../../services/orderAi'
import { errText, orderErrorKey } from '../../../services/orders'

const BULLET = '- '

/** Plain policy text: real line breaks, blank lines between paragraphs, `- ` bullets (guide 7s.1). */
function Text({ body }: { body: string }) {
  const blocks = body.split(/\n\s*\n/).map((b) => b.split('\n').map((l) => l.trim()).filter(Boolean)).filter((b) => b.length)
  const isList = (lines: string[]) => lines.every((l) => l.startsWith(BULLET))
  return (
    <>
      {blocks.map((lines, i) =>
        isList(lines)
          ? <ul key={i}>{lines.map((l, j) => <li key={j}>{l.slice(BULLET.length)}</li>)}</ul>
          : <p key={i}>{lines.join('\n')}</p>,
      )}
    </>
  )
}

interface Props {
  /** The customer ticked the box and the backend recorded it. */
  onAccepted: () => void
  /** Closed without agreeing: Create Order stays on "By myself". */
  onDecline: () => void
}

/**
 * Asked every time the customer turns the assistant on. The policy comes from `GET /privacy-policy/ai-chat`; ticking the box
 * records the consent (`POST /me/assistant/consent`) and closes the dialog. There is no other way into the assistant.
 */
export default function AiPolicyDialog({ onAccepted, onDecline }: Props) {
  const t = useT()
  const locale = useLocale()
  const dialog = useRef<HTMLDialogElement>(null)
  const [policy, setPolicy] = useState<AiPolicy | null>(null)
  const [loadErr, setLoadErr] = useState(false)
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState('')

  const load = () => {
    setLoadErr(false)
    setPolicy(null)
    aiChatPolicy().then(setPolicy).catch(() => setLoadErr(true))
  }

  useEffect(() => {
    const el = dialog.current!
    const before = document.body.style.overflow
    el.showModal()
    document.body.style.overflow = 'hidden'
    load()
    return () => {
      el.close()
      document.body.style.overflow = before
    }
  }, [])

  const agree = async () => {
    if (!policy || saving) return
    setSaving(true)
    setErr('')
    try {
      await acceptAiPolicy(policy.version)
      onAccepted()
    } catch (e) {
      setSaving(false)
      if (e instanceof ApiError && e.code === 'POLICY_VERSION_CHANGED') {
        setErr(t('oa.policy.changed'))
        load()
      } else setErr(errText(t, orderErrorKey(e)))
    }
  }

  const close = () => {
    if (!saving) onDecline()
  }

  return (
    <dialog ref={dialog} className="oap" aria-labelledby="oap-title" aria-describedby="oap-lede" aria-busy={!policy && !loadErr}
      onCancel={(e) => { e.preventDefault(); close() }}
      onClick={(e) => { if (e.target === e.currentTarget) close() }}>
      <div className="oap-card">
        <header className="oap-head">
          <span className="oa-avatar" aria-hidden="true"><Sparkle weight="fill" /></span>
          <div className="oap-titles">
            <span className="oap-eyebrow">{t('oa.title')}</span>
            <h2 id="oap-title">{policy?.title ?? t('oa.policy.title')}</h2>
            {policy && <span className="oap-ver">{t('oa.policy.version', { v: policy.version })}</span>}
          </div>
          <button type="button" className="oa-tool" aria-label={t('oa.policy.close')} title={t('oa.policy.close')} disabled={saving} onClick={close}>
            <X aria-hidden="true" weight="bold" />
          </button>
        </header>

        <p id="oap-lede" className="oap-lede">{t('oa.policy.lede')}</p>

        {policy && (policy.providers.length > 0 || policy.retentionDays) && (
          <ul className="oap-facts">
            {policy.providers.length > 0 && (
              <li><Sparkle aria-hidden="true" /><span><b>{t('oa.policy.providers')}</b> {policy.providers.join(', ')}</span></li>
            )}
            {!!policy.retentionDays && (
              <li><Clock aria-hidden="true" /><span>{t('oa.policy.retention', { n: policy.retentionDays })}</span></li>
            )}
          </ul>
        )}

        <div className="oap-body" tabIndex={0} autoFocus aria-label={t('oa.policy.title')}>
          {loadErr ? (
            <div className="oap-state" role="alert">
              <p>{t('oa.policy.loadErr')}</p>
              <button type="button" className="oa-btn oa-btn--line" onClick={load}>{t('oa.policy.retry')}</button>
            </div>
          ) : !policy ? (
            <div className="oap-state" role="status">
              <span className="oap-skel" /><span className="oap-skel" /><span className="oap-skel oap-skel--short" />
              <span className="oa-sr">{t('oa.policy.loading')}</span>
            </div>
          ) : (
            <>
              {!locale.startsWith('vi') && (
                <p className="oap-lang"><Info aria-hidden="true" />{t('oa.policy.onlyVi')}</p>
              )}
              {policy.sections.length ? (
                policy.sections.map((s, i) => (
                  <section key={i} className="oap-sec">
                    <h3>{s.title}</h3>
                    <Text body={s.body} />
                  </section>
                ))
              ) : (
                <Text body={policy.body} />
              )}
            </>
          )}
        </div>

        <footer className="oap-foot">
          <label className={`oap-agree${saving ? ' busy' : ''}`}>
            <input type="checkbox" checked={saving} disabled={!policy || saving} onChange={(e) => { if (e.target.checked) void agree() }} />
            <span>{t('oa.policy.agree')}</span>
          </label>
          <div className="oap-row">
            <p className={`oap-hint${err ? ' oap-hint--err' : ''}`} role={err ? 'alert' : 'status'}>
              {err || t(saving ? 'oa.policy.saving' : 'oa.policy.hint')}
            </p>
            <button type="button" className="oa-btn oa-btn--line" disabled={saving} onClick={close}>{t('oa.policy.decline')}</button>
          </div>
        </footer>
      </div>
    </dialog>
  )
}
