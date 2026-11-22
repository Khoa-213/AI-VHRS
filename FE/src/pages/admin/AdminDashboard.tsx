import AdminSelect from '../../components/admin/AdminSelect'
import {
  CalendarCheck, CheckCircle, Clock, Gear, Lock, PlugsConnected, Plus, Pulse, Robot, ShieldCheck, Users, WarningCircle, EnvelopeSimple,
} from '@phosphor-icons/react'
import { useState } from 'react'
import AdminFrame from '../../components/admin/AdminFrame'
import {
  Attention, Card, Chip, DayColumns, Donut, Kpi, Ring, StateMark, type Delta, type Slice, type Tone,
} from '../../components/admin/AdminViz'
import { useAsync } from '../../hooks/useAsync'
import { useLocale, useT } from '../../i18n'
import { Link } from '../../router/router'
import {
  BACKGROUND_JOBS, ROLES, auditActivity, listAudit, runBackgroundJobs, systemDashboard, type BackgroundJob,
} from '../../services/admin'
import { errText, orderErrorKey } from '../../services/orders'
import { auditKind, auditLabel } from '../../utils/audit'

const STATUSES = ['ACTIVE', 'LOCKED', 'DISABLED'] as const
// The first five slots of the validated eight-hue palette, in their fixed order (blue, orange, aqua, yellow, magenta), stepped for
// dark and light in admin-shell.css. Every slice is also named with its number in the legend and in the table view.
const ROBOT_STATUS = ['AVAILABLE', 'BUSY', 'MAINTENANCE', 'BROKEN']
const ROBOT_TONE: Record<string, Tone> = { AVAILABLE: 'good', BUSY: 'accent', MAINTENANCE: 'warn', BROKEN: 'bad' }
const ROBOT_COLOR: Record<string, string> = { AVAILABLE: 'var(--good)', BUSY: 'var(--series-1)', MAINTENANCE: 'var(--warn)', BROKEN: 'var(--danger)' }
const ROLE_COLORS = ['var(--series-1)', 'var(--series-2)', 'var(--series-3)', 'var(--series-4)', 'var(--series-5)']
const RANGES = [7, 14, 30] as const

/**
 * Admin home. The two actions an Admin takes most; system status and key numbers;
 * activity and accounts by role; then what needs action, background jobs, robots, integrations and the latest log.
 */
export default function AdminDashboard() {
  const t = useT()
  const locale = useLocale()
  const sys = useAsync(systemDashboard, [], 30000)
  const activity = useAsync(() => auditActivity(30), [], 60000)
  const recent = useAsync(() => listAudit({ pageSize: 6 }), [], 30000)
  const [range, setRange] = useState<(typeof RANGES)[number]>(14)
  const [only, setOnly] = useState<BackgroundJob | ''>('')
  const [running, setRunning] = useState(false)
  const [runError, setRunError] = useState('')

  const d = sys.data
  const byRole = d?.accounts.byRole ?? {}
  const count = (role: string, status: string) => byRole[role]?.[status] ?? 0
  const roleTotal = (role: string) => STATUSES.reduce((n, s) => n + count(role, s), 0)
  const total = ROLES.reduce((n, r) => n + roleTotal(r), 0)
  const locked = ROLES.reduce((n, r) => n + count(r, 'LOCKED'), 0)
  const run = d?.backgroundJobs.lastRun ?? null
  const failedJobs = run ? Object.entries(run.results).filter(([, r]) => Object.prototype.hasOwnProperty.call(r, 'error')).map(([name]) => name) : []
  const notConfigured = (d?.integrations ?? []).filter((i) => !i.configured)
  const configured = (d?.integrations.length ?? 0) - notConfigured.length
  const offline = d ? d.robots.total - d.robots.online : 0
  const ringTone = !d || d.robots.online >= d.robots.total ? 'good' : d.robots.online === 0 ? 'bad' : 'warn'
  const slowDb = !!d && d.databaseMs > 800

  // What the Admin should look at, most serious first. Each line says what it is and where to fix it.
  const attention: { tone: 'warn' | 'bad'; title: string; body?: string; to?: string; cta?: string }[] = []
  if (d) {
    if (slowDb) attention.push({ tone: 'bad', title: t('adm.at.db'), body: t('adm.at.dbBody', { ms: d.databaseMs }) })
    if (failedJobs.length) attention.push({ tone: 'bad', title: t('adm.at.jobs'), body: t('adm.at.jobsBody', { names: failedJobs.map((n) => t(`ad.jobs.${n}`)).join(', ') }) })
    if (d.emailsFailedLast24h > 0) attention.push({ tone: 'warn', title: t('adm.at.mail', { n: d.emailsFailedLast24h }), body: t('adm.at.mailBody'), to: '/admin/settings#integrations', cta: t('adm.view') })
    if (locked > 0) attention.push({ tone: 'warn', title: t('adm.at.locked', { n: locked }), body: t('adm.at.lockedBody'), to: '/admin/accounts?status=LOCKED', cta: t('adm.view') })
    if (notConfigured.length) attention.push({ tone: 'warn', title: t('adm.at.integ', { n: notConfigured.length }), body: t('adm.at.integBody', { names: notConfigured.map((i) => i.name).join(', ') }), to: '/admin/settings#integrations', cta: t('adm.view') })
    if (!d.backgroundJobs.enabled) attention.push({ tone: 'warn', title: t('adm.at.jobsOff'), body: t('adm.at.jobsOffBody') })
  }
  const level = attention.some((a) => a.tone === 'bad') ? 'bad' : attention.length ? 'warn' : 'good'

  const slices: Slice[] = ROLES.map((r, i) => ({
    key: r,
    label: t(`ad.role.${r}`),
    value: roleTotal(r),
    color: ROLE_COLORS[i],
    note: count(r, 'LOCKED') > 0 ? t('adm.donut.locked', { n: count(r, 'LOCKED') }) : undefined,
  }))

  const runNow = async () => {
    if (running) return
    setRunning(true); setRunError('')
    try {
      await runBackgroundJobs(only ? [only] : undefined)
      await sys.reload()
    } catch (e) {
      setRunError(orderErrorKey(e))
    } finally {
      setRunning(false)
    }
  }

  const when = (iso: string) => new Date(iso).toLocaleString(locale, { dateStyle: 'medium', timeStyle: 'short' })
  const all30 = activity.data?.days ?? []
  const shown = all30.slice(-range)
  const sum = (xs: { count: number }[]) => xs.reduce((n, x) => n + x.count, 0)
  const last7 = sum(all30.slice(-7))
  const prev7 = sum(all30.slice(-14, -7))
  const actDelta: Delta | undefined = all30.length >= 14
    ? prev7 === 0
      ? { dir: last7 > 0 ? 'up' : 'flat', text: last7 > 0 ? t('adm.delta.new') : '0%', tone: 'accent' }
      : { dir: last7 >= prev7 ? (last7 === prev7 ? 'flat' : 'up') : 'down', text: `${last7 >= prev7 ? '+' : ''}${Math.round(((last7 - prev7) / prev7) * 100)}%`, tone: last7 >= prev7 ? 'accent' : 'mute' }
    : undefined
  const err = [sys.error, activity.error, recent.error].find(Boolean)

  return (
    <AdminFrame
      active="overview"
      title={t('adm.nav.overview')}
      actions={<Link to="/admin/accounts?new=1" className="adm-btn adm-btn--solid"><Plus size={18} weight="bold" aria-hidden />{t('adm.short.create')}</Link>}
    >
      {!!err && <p className="adm-error" role="alert">{errText(t, orderErrorKey(err))}</p>}
      {sys.loading && !d && <p className="adm-fine" role="status">{t('co.loading')}</p>}

      {d && (
        <div className={`adm-banner adm-${level}`} role="status">
          {level === 'good' ? <CheckCircle size={28} weight="fill" aria-hidden /> : <WarningCircle size={28} weight="fill" aria-hidden />}
          <div style={{ flex: 1, minWidth: 200 }}>
            <b>{t(`adm.banner.${level}`)}</b>
            {attention.length > 0 && <span>{attention.map((item) => item.title).join('; ')}</span>}
          </div>
          {attention.length > 0 && <Link to="/admin#attention" className="adm-attn-cta">{t('adm.banner.see')}</Link>}
        </div>
      )}

      {d && (
        <div className="adm-kpi-grid">
          <Kpi icon={<Users size={22} aria-hidden />} label={t('ad.kpi.total')} value={total} to="/admin/accounts"
            delta={{ dir: d.accounts.newLast7Days > 0 ? 'up' : 'flat', text: t('adm.kpi.newWeek', { n: d.accounts.newLast7Days }), tone: d.accounts.newLast7Days > 0 ? 'good' : 'mute' }} />
          <Kpi icon={<ShieldCheck size={22} aria-hidden />} label={t('sy.sessions')} value={d.accounts.activeSessions} />
          <Kpi icon={<Robot size={22} aria-hidden />} label={t('sy.robotsOnline')} value={`${d.robots.online} / ${d.robots.total}`}
            delta={offline > 0 ? { dir: 'down', text: t('adm.kpi.offline', { n: offline }), tone: 'warn' } : { dir: 'flat', text: t('adm.kpi.allOnline'), tone: 'good' }} />
          <Kpi icon={<CalendarCheck size={22} aria-hidden />} label={t('adm.kpi.actions7')} value={last7} hint={t('adm.kpi.vsPrev')} delta={actDelta} to="/admin/audit" />
          <Kpi icon={<Pulse size={22} aria-hidden />} label={t('sy.db')} value={`${d.databaseMs} ms`}
            delta={{ dir: 'flat', text: t(slowDb ? 'adm.kpi.slow' : 'adm.kpi.fast'), tone: slowDb ? 'bad' : 'good' }} />
          <Kpi icon={<Lock size={22} aria-hidden />} label={t('adm.kpi.locked')} value={locked} to="/admin/accounts?status=LOCKED"
            delta={locked > 0 ? { dir: 'up', text: t('adm.kpi.check'), tone: 'warn' } : { dir: 'flat', text: t('adm.kpi.none'), tone: 'good' }} />
          <Kpi icon={<EnvelopeSimple size={22} aria-hidden />} label={t('sy.emailsFailed')} value={d.emailsFailedLast24h} to="/admin/settings#integrations"
            delta={d.emailsFailedLast24h > 0 ? { dir: 'up', text: t('adm.kpi.check'), tone: 'warn' } : { dir: 'flat', text: t('adm.kpi.none'), tone: 'good' }} />
          <Kpi icon={<PlugsConnected size={22} aria-hidden />} label={t('adm.kpi.integrations')} value={`${configured} / ${d.integrations.length}`} to="/admin/settings#integrations"
            delta={notConfigured.length > 0 ? { dir: 'down', text: t('adm.kpi.missing', { n: notConfigured.length }), tone: 'warn' } : { dir: 'flat', text: t('adm.kpi.complete'), tone: 'good' }} />
        </div>
      )}

      <div className="adm-charts">
        <Card
          title={t('adm.chart.activity')}
          aside={(
            <div className="adm-seg-range" role="group" aria-label={t('adm.range.aria')}>
              {RANGES.map((n) => <button key={n} type="button" className={range === n ? 'on' : ''} aria-pressed={range === n} onClick={() => setRange(n)}>{t('adm.range.days', { n })}</button>)}
            </div>
          )}
        >
          {activity.loading && !activity.data ? <p className="adm-fine" role="status">{t('co.loading')}</p> : (
            <>
              <DayColumns key={range} days={shown} label={t('adm.chart.events')} unit={t('adm.chart.eventsUnit')} locale={locale} caption={t('adm.chart.activity')} />
              {activity.data?.truncated && <p className="adm-fine">{t('adm.chart.truncated')}</p>}
            </>
          )}
        </Card>

        <Card title={t('adm.chart.roles')} aside={<Link to="/admin/accounts" className="adm-link">{t('ad.seeAccounts')}</Link>}>
          <Donut slices={slices} centerLabel={t('adm.donut.center')} caption={t('adm.chart.roles')} />
        </Card>
      </div>

      {attention.length > 0 && (
        <div id="attention">
          <Card title={t('adm.at.title')}>
            <div className="adm-attn-list">
              {attention.map((a) => <Attention key={a.title} {...a} />)}
            </div>
          </Card>
        </div>
      )}

      <div className="adm-grid2">
        <Card title={t('adm.robots.title')}>
          {d && (
            <div className="adm-split">
              <Ring value={d.robots.online} total={d.robots.total} label={t('sy.robotsOnline')} tone={ringTone} />
              <ul className="adm-robot-rows">
                {Object.keys(d.robots.byStatus).length === 0 && <li className="adm-fine">{t('adm.robots.none')}</li>}
                {Object.entries(d.robots.byStatus).map(([s, n]) => (
                  <li key={s}>
                    <Chip tone={ROBOT_TONE[s] ?? 'mute'}>{ROBOT_STATUS.includes(s) ? t(`rs.${s}`) : s}</Chip>
                    <b>{n}</b>
                    <span className="adm-donut-share" aria-hidden><span style={{ width: `${d.robots.total ? (n / d.robots.total) * 100 : 0}%`, background: ROBOT_COLOR[s] ?? 'var(--ink3)' }} /></span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Card>

        <Card title={t('ad.jobs.title')} aside={d && <StateMark tone={d.backgroundJobs.enabled ? 'good' : 'warn'} label={t(d.backgroundJobs.enabled ? 'adm.jobs.on' : 'adm.jobs.off')} />}>
          <div className="adm-actions">
            <label className="adm-field" style={{ flex: '1 1 220px' }}>
              <span>{t('ad.jobs.which')}</span>
              <AdminSelect label={t('ad.jobs.which')} value={only} disabled={running} onChange={(value) => setOnly(value as BackgroundJob | '')} options={[{ value: '', label: t('ad.jobs.all') }, ...BACKGROUND_JOBS.map((j) => ({ value: j, label: t(`ad.jobs.${j}`) }))]} />
            </label>
            <button type="button" className="adm-btn adm-btn--solid" style={{ alignSelf: 'flex-end' }} disabled={running} onClick={() => void runNow()}>{t(running ? 'ad.jobs.running' : 'ad.jobs.run')}</button>
          </div>
          {runError && <p className="adm-error" role="alert">{errText(t, runError)}</p>}
          {!run && <p className="adm-fine">{t('ad.jobs.never')}</p>}
          {run && (
            <>
              <p className="adm-fine"><Clock size={14} aria-hidden style={{ verticalAlign: '-2px' }} /> {t('ad.jobs.last', { when: when(run.startedAt), s: run.seconds.toFixed(1) })}{!run.ran ? ` · ${t('ad.jobs.busy')}` : ''}</p>
              <div className="adm-list">
                {Object.entries(run.results).map(([jobName, r]) => {
                  const failed = Object.prototype.hasOwnProperty.call(r, 'error')
                  return (
                    <div key={jobName} className="adm-item">
                      <div className="adm-item-text">
                        <b>{BACKGROUND_JOBS.includes(jobName as BackgroundJob) ? t(`ad.jobs.${jobName}`) : jobName}</b>
                        <span className="adm-mono">{failed ? String(r.error) : Object.entries(r).map(([k, v]) => `${k}: ${String(v)}`).join(' · ') || '–'}</span>
                      </div>
                      <Chip tone={failed ? 'bad' : 'good'}>{t(failed ? 'ad.jobs.failed' : 'ad.jobs.ok')}</Chip>
                    </div>
                  )
                })}
              </div>
            </>
          )}
        </Card>
      </div>

      <Card title={t('ig.title')} aside={<Link to="/admin/settings#integrations" className="adm-link"><Gear size={14} aria-hidden style={{ verticalAlign: '-2px' }} /> {t('sy.seeSettings')}</Link>}>
        <div className="adm-integrations">
          {(d?.integrations ?? []).map((i) => (
            <div key={i.name} className="adm-integ">
              <div className="adm-integ-top"><b>{i.name}</b><Chip tone={i.configured ? 'good' : 'warn'}>{t(i.configured ? 'ig.configured' : 'ig.notConfigured')}</Chip></div>
              <small>{t(`ig.kind.${i.kind}`)} · <span className="adm-mono">{i.mode}</span></small>
            </div>
          ))}
        </div>
      </Card>

      <Card title={t('ad.recent')} aside={<Link to="/admin/audit" className="adm-link">{t('ad.seeAudit')}</Link>}>
        <div className="adm-list">
          {(recent.data?.items ?? []).map((e) => (
            <div key={e.id} className="adm-item">
              <div className="adm-item-text">
                <b>{auditLabel(t, e.action)}</b>
                <span>{auditKind(t, e.entityType)}{e.entityId !== null ? ` #${e.entityId}` : ''} · {e.actorId !== null ? t('adm.au.byUser', { id: e.actorId }) : t('ad.au.system')}{e.reason ? ` · ${e.reason}` : ''}</span>
              </div>
              <span className="adm-fine">{when(e.createdAt)}</span>
            </div>
          ))}
          {recent.data && !recent.data.items.length && <p className="adm-fine">{t('ad.au.empty')}</p>}
        </div>
      </Card>
    </AdminFrame>
  )
}
