import { useEffect, useState } from 'react'
import AdminFrame from '../../components/admin/AdminFrame'
import { Card, Chip } from '../../components/admin/AdminViz'
import { useAsync } from '../../hooks/useAsync'
import { useT } from '../../i18n'
import type { Job } from '../../services/async'
import {
  listIntegrations, listSettings, saveSetting, toggleIntegration,
  type Integration, type SettingValue, type SystemSetting,
} from '../../services/admin'
import { errText, orderErrorKey } from '../../services/orders'

/** Whole-number settings and the range the backend accepts (it checks again and answers `422 INVALID_SETTING`). */
const INT_RANGE: Record<string, [number, number]> = {
  quotation_valid_days: [1, 60],
  deposit_deadline_days: [1, 30],
  accept_reminder_days: [1, 30],
  auto_accept_days: [2, 60],
  eta_cancel_threshold_days: [1, 60],
  max_upload_mb: [1, 20],
  max_pages_per_order: [1, 50],
  image_retention_days: [30, 3650],
}
const ORDER_TYPES = ['OT1_COPY_RESTORE', 'OT3_TEMPLATE'] as const
const FEES = ['FLAT_BOX_A5', 'FLAT_BOX_A4', 'TUBE'] as const

/** The parameters in the order a person thinks about them; the group title is one short word above each run of rows. */
const GROUPS: { id: string; keys: string[] }[] = [
  { id: 'quote', keys: ['quotation_valid_days', 'deposit_deadline_days'] },
  { id: 'delivery', keys: ['accept_reminder_days', 'auto_accept_days', 'eta_cancel_threshold_days', 'fallback_shipping_fees'] },
  { id: 'orders', keys: ['order_types_enabled', 'max_upload_mb', 'max_pages_per_order'] },
  { id: 'photos', keys: ['image_retention_days', 'photo_purge_enabled'] },
]

const same = (a: SettingValue, b: SettingValue) => JSON.stringify(a) === JSON.stringify(b)

/** One line: what it is and what it does on the left, the value on the right, and a Save button once the value changed. */
function SettingRow({ setting, onSaved }: { setting: SystemSetting; onSaved: Job }) {
  const t = useT()
  const [value, setValue] = useState<SettingValue>(setting.value)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const k = setting.key
  const changed = !same(value, setting.value)
  const range = INT_RANGE[k]
  const edit = (v: SettingValue) => { setValue(v); setErr('') }

  const save = async () => {
    // Turning purge on deletes customer photos for good: ask first.
    if (k === 'photo_purge_enabled' && value === true && !window.confirm(t('st.purgeConfirm'))) return
    setBusy(true); setErr('')
    try {
      await saveSetting(k, value)
      await onSaved()
    } catch (e) {
      setErr(orderErrorKey(e))
    } finally {
      setBusy(false)
    }
  }

  let editor
  if (range) {
    editor = (
      <input
        className="adm-input adm-num"
        type="number"
        inputMode="numeric"
        min={range[0]}
        max={range[1]}
        value={typeof value === 'number' ? value : ''}
        disabled={busy}
        aria-label={t(`st.${k}`)}
        title={t('st.range', { min: range[0], max: range[1] })}
        onChange={(e) => edit(e.target.value === '' ? 0 : Number(e.target.value))}
      />
    )
  } else if (k === 'photo_purge_enabled') {
    editor = (
      <label className="adm-switch">
        <input type="checkbox" checked={value === true} disabled={busy} onChange={(e) => edit(e.target.checked)} />
        <i aria-hidden />
        <span>{t(value === true ? 'st.on' : 'st.off')}</span>
      </label>
    )
  } else if (k === 'order_types_enabled' && Array.isArray(value)) {
    const list = value
    editor = (
      <div className="adm-checks">
        {ORDER_TYPES.map((code) => (
          <label key={code} className="adm-check">
            <input type="checkbox" checked={list.includes(code)} disabled={busy} onChange={(e) => edit(e.target.checked ? [...list, code].sort() : list.filter((x) => x !== code))} />
            <span>{t(`ot.${code}`)}</span>
          </label>
        ))}
      </div>
    )
  } else if (k === 'fallback_shipping_fees' && typeof value === 'object' && !Array.isArray(value)) {
    const fees = value as Record<string, number>
    editor = (
      <div className="adm-fees">
        {FEES.map((code) => (
          <label key={code} className="adm-field">
            {t(`st.fee.${code}`)}
            <input type="number" inputMode="numeric" min={0} max={1000000} value={fees[code] ?? 0} disabled={busy} onChange={(e) => edit({ ...fees, [code]: e.target.value === '' ? 0 : Number(e.target.value) })} />
          </label>
        ))}
      </div>
    )
  } else {
    editor = <pre className="adm-json">{JSON.stringify(value, null, 2)}</pre>
  }

  return (
    <div className="adm-srow">
      <div className="adm-srow-text">
        <b>{t(`st.${k}`)}</b>
        <span>{t(`st.help.${k}`)}</span>
      </div>
      <div className="adm-srow-edit">
        {editor}
        {changed && (
          <>
            <button type="button" className="adm-btn adm-btn--solid adm-btn--sm" disabled={busy} onClick={() => void save()}>{t('ad.acc.save')}</button>
            <button type="button" className="adm-btn adm-btn--line adm-btn--sm" disabled={busy} onClick={() => { setValue(setting.value); setErr('') }}>{t('st.undo')}</button>
          </>
        )}
      </div>
      {err && <p className="adm-error" role="alert" style={{ gridColumn: '1 / -1' }}>{errText(t, err)}</p>}
    </div>
  )
}

/** One line per integration: its name, whether the server has it set up, and (for GHN only) a switch. */
function IntegrationRow({ item, onChanged }: { item: Integration; onChanged: Job }) {
  const t = useT()
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const flip = async (next: boolean) => {
    if (!window.confirm(t(next ? 'ig.confirmOn' : 'ig.confirmOff', { name: item.name }))) return
    setBusy(true); setErr('')
    try {
      await toggleIntegration(item.name, next)
      await onChanged()
    } catch (e) {
      setErr(orderErrorKey(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="adm-srow">
      <div className="adm-srow-text">
        <b>{item.name}</b>
        <span>{t(`ig.kind.${item.kind}`)} · <span className="adm-mono">{item.mode}</span></span>
      </div>
      <div className="adm-srow-edit">
        <Chip tone={item.configured ? 'good' : 'warn'}>{t(item.configured ? 'ig.configured' : 'ig.notConfigured')}</Chip>
        {item.toggleable ? (
          <label className="adm-switch">
            <input type="checkbox" checked={item.enabled} disabled={busy} onChange={(e) => void flip(e.target.checked)} />
            <i aria-hidden />
            <span>{t(item.enabled ? 'st.on' : 'st.off')}</span>
          </label>
        ) : <span className="adm-fine">{t('ig.serverOnly')}</span>}
      </div>
      {err && <p className="adm-error" role="alert" style={{ gridColumn: '1 / -1' }}>{errText(t, err)}</p>}
    </div>
  )
}

/** Admin only: the business rules the system follows (UC-50) and the state of each integration (UC-49). Secrets never reach the browser. */
export default function Settings() {
  const t = useT()
  const settings = useAsync(listSettings, [])
  const integrations = useAsync(listIntegrations, [])
  const byKey = new Map((settings.data ?? []).map((s) => [s.key, s]))
  const known = new Set(GROUPS.flatMap((g) => g.keys))
  const extra = (settings.data ?? []).filter((s) => !known.has(s.key))

  // Links from the dashboard land on #integrations.
  const ready = !!integrations.data
  useEffect(() => {
    if (ready && window.location.hash === '#integrations') document.getElementById('integrations')?.scrollIntoView({ behavior: 'smooth' })
  }, [ready])

  return (
    <AdminFrame active="settings" title={t('st.title')}>
      {!!settings.error && <p className="adm-error" role="alert">{errText(t, orderErrorKey(settings.error))}</p>}
      {settings.loading && !settings.data && <p className="adm-fine" role="status">{t('co.loading')}</p>}

      <Card title={t('st.paramsTitle')}>
        {GROUPS.map((g) => {
          const rows = g.keys.map((k) => byKey.get(k)).filter((s): s is SystemSetting => !!s)
          if (!rows.length) return null
          return (
            <div key={g.id} className="adm-sgroup">
              <h3>{t(`adm.st.group.${g.id}`)}</h3>
              {rows.map((s) => (
                // The row restarts from the saved value whenever the server value changes.
                <SettingRow key={`${s.key}-${JSON.stringify(s.value)}`} setting={s} onSaved={async () => { await settings.reload() }} />
              ))}
            </div>
          )
        })}
        {extra.length > 0 && (
          <div className="adm-sgroup">
            <h3>{t('adm.st.group.other')}</h3>
            {extra.map((s) => <SettingRow key={`${s.key}-${JSON.stringify(s.value)}`} setting={s} onSaved={async () => { await settings.reload() }} />)}
          </div>
        )}
      </Card>

      <div id="integrations">
        <Card title={t('ig.title')}>
          {!!integrations.error && <p className="adm-error" role="alert">{errText(t, orderErrorKey(integrations.error))}</p>}
          {integrations.loading && !integrations.data && <p className="adm-fine" role="status">{t('co.loading')}</p>}
          <div className="adm-sgroup">
            {(integrations.data ?? []).map((i) => <IntegrationRow key={i.name} item={i} onChanged={async () => { await integrations.reload() }} />)}
          </div>
        </Card>
      </div>
    </AdminFrame>
  )
}
