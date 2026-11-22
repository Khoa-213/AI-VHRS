import { CheckCircle, Hourglass, ShieldCheck, XCircle } from '@phosphor-icons/react'
import { useEffect, useState } from 'react'
import CustomerFrame from '../../components/layout/CustomerFrame'
import { useLocale, useT } from '../../i18n'
import { navigate } from '../../router/router'
import { errText, orderErrorKey } from '../../services/orders'
import { verifyCode, type Verification } from '../../services/studio'
import '../studio/studio.css'

const ICON = { VALID: CheckCircle, NOT_PRODUCED: Hourglass, REVOKED: XCircle } as const

/**
 * Public page behind the QR code on the certificate card (`/verify/:code`). No sign-in. The backend shows only the product
 * type, paper, pages, copies and dates: never the customer or what was written.
 */
export default function Verify({ code }: { code?: string }) {
  const t = useT()
  const locale = useLocale()
  const [value, setValue] = useState(code ?? '')
  const [result, setResult] = useState<Verification | null>(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const run = async (c: string) => {
    const clean = c.trim()
    if (!clean) return
    setBusy(true)
    setErr('')
    setResult(null)
    try {
      setResult(await verifyCode(clean))
    } catch (e) {
      setErr(orderErrorKey(e))
    } finally {
      setBusy(false)
    }
  }

  // A code in the address (the QR link) is checked once when the page opens or the code changes.
  useEffect(() => {
    if (!code) return
    setValue(code)
    void run(code)
  }, [code])

  const date = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString(locale) : null)
  const Icon = result ? ICON[result.status] : ShieldCheck
  const rows: [string, string | number | null][] = result ? [
    ['vf.mark', result.watermarkText],
    ['vf.type', result.orderTypeLabel],
    ['vf.paper', result.paperSize],
    ['vf.pages', result.pages],
    ['vf.qty', result.quantity],
    ['vf.issued', date(result.issuedAt)],
    ['vf.locked', date(result.productionLockedAt)],
    ['vf.written', date(result.writtenAt)],
  ] : []

  return (
    <CustomerFrame label="Verify" narrow>
      <div className="stu vf">
        <header className="co-head">
          <span className="co-eyebrow">AI-VHRS</span>
          <h1 className="co-h1">{t('vf.title')}</h1>
          <p className="co-lede">{t('vf.lede')}</p>
        </header>

        <form className="vf-form" onSubmit={(e) => { e.preventDefault(); const c = value.trim(); if (c) { if (c === code) void run(c); else navigate(`/verify/${encodeURIComponent(c)}`) } }}>
          <label className="co-group-label" htmlFor="vf-code">{t('vf.label')}</label>
          <div className="vf-row">
            <input id="vf-code" className="stu-input vf-input vh-mono" value={value} maxLength={32} autoComplete="off" autoCapitalize="characters" spellCheck={false} placeholder={t('vf.ph')} onChange={(e) => setValue(e.target.value)} />
            <button type="submit" className="co-btn co-btn--solid" disabled={busy || !value.trim()}>{t(busy ? 'vf.checking' : 'vf.check')}</button>
          </div>
        </form>

        {!!err && <p className="stu-error" role="alert">{errText(t, err)}</p>}

        {result && (
          <section className={`vf-result vf-${result.status}`} aria-live="polite">
            <div className="vf-status">
              <Icon size={28} weight="fill" aria-hidden />
              <div>
                <h2 className="stu-h2">{t(`vf.status.${result.status}`)}</h2>
                <span className="vh-mono vf-code">{result.code}</span>
              </div>
            </div>
            <p className="vf-statement">{result.statement}</p>
            <dl className="vf-facts">
              {rows.filter(([, v]) => v !== null && v !== '').map(([k, v]) => (
                <div key={k}><dt>{t(k)}</dt><dd>{v}</dd></div>
              ))}
            </dl>
            <p className="stu-hint">{t('vf.privacy')}</p>
          </section>
        )}
      </div>
    </CustomerFrame>
  )
}
