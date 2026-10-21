import { Lock, Scroll, UserCircle, Users } from '@phosphor-icons/react'
import { Donut } from '../../components/ws/charts'
import { Kpi, avatarTone, initials } from '../../components/ws/parts'
import Shell from '../../components/ws/Shell'
import { useAsync } from '../../hooks/useAsync'
import { useLocale, useT } from '../../i18n'
import { Link } from '../../router/router'
import { ROLES, listAccounts, listAudit } from '../../services/admin'
import { errText, orderErrorKey } from '../../services/orders'
import { useUser } from '../../store/store'
import './admin.css'

const ROLE_COLORS = ['var(--beige2)', 'var(--acc)', 'var(--tosca2)', 'var(--purple2)', 'var(--ink)']

/** Admin home: how many accounts there are per role, who is locked, and the latest entries of the audit trail. */
export default function AdminDashboard() {
  const t = useT()
  const locale = useLocale()
  const user = useUser()
  const stats = useAsync(async () => {
    const [byRole, locked, disabled] = await Promise.all([
      Promise.all(ROLES.map(async (r) => (await listAccounts({ role: r, pageSize: 1 })).total)),
      listAccounts({ status: 'LOCKED', pageSize: 1 }),
      listAccounts({ status: 'DISABLED', pageSize: 1 }),
    ])
    return { byRole, locked: locked.total, disabled: disabled.total }
  }, [], 60000)
  const recent = useAsync(() => listAudit({ pageSize: 8 }), [], 30000)
  const recentAccounts = useAsync(() => listAccounts({ pageSize: 5 }), [], 60000)

  const byRole = stats.data?.byRole ?? ROLES.map(() => 0)
  const total = byRole.reduce((a, b) => a + b, 0)
  const internal = total - byRole[0]
  const err = [stats.error, recent.error].find(Boolean)

  return (
    <Shell area="admin" active="dashboard" title={t('wk.hello', { name: user?.name ?? t('role.admin') })} lede={t('ad.lede')}>
      {!!err && <p className="lg-error" role="alert">{errText(t, orderErrorKey(err))}</p>}

      <div className="row4">
        <Kpi icon={<Users size={20} aria-hidden />} tone="a" title={t('ad.kpi.total')} value={total} to="/admin/accounts" />
        <Kpi icon={<UserCircle size={20} aria-hidden />} tone="p" title={t('ad.kpi.internal')} value={internal} note={t('ad.kpi.internalHint')} to="/admin/accounts" />
        <Kpi icon={<Lock size={20} aria-hidden />} tone="b" title={t('ad.kpi.locked')} value={stats.data?.locked ?? 0} badge={stats.data?.locked ? t('ad.kpi.check') : undefined} badgeTone="ac" to="/admin/accounts" />
        <Kpi icon={<Scroll size={20} aria-hidden />} tone="t" title={t('ad.kpi.events')} value={recent.data?.total ?? 0} note={t('ad.kpi.eventsHint')} to="/admin/audit" />
      </div>

      <div className="flex">
        <section className="panel" style={{ flex: '1 1 380px' }} aria-labelledby="a1">
          <div className="ph"><h2 id="a1">{t('ad.chart.roles')}</h2></div>
          <Donut
            centerLabel={t('ad.chart.center')}
            caption={t('ad.chart.caption', { n: total })}
            slices={ROLES.map((r, i) => ({ label: t(`ad.role.${r}`), value: byRole[i], color: ROLE_COLORS[i] }))}
          />
        </section>

        <section className="panel" style={{ flex: '1 1 420px' }} aria-labelledby="a2">
          <div className="ph"><h2 id="a2">{t('ad.newest')}</h2><Link to="/admin/accounts" className="link">{t('ad.seeAccounts')}</Link></div>
          <div className="list">
            {(recentAccounts.data?.items ?? []).map((a) => (
              <div key={a.id} className="item">
                <span className={`avatar ${avatarTone(a.name)}`}>{initials(a.name)}</span>
                <div className="t"><b>{a.name}</b><span>{a.email}</span></div>
                <span className="chip mute">{t(`ad.role.${a.role}`)}</span>
              </div>
            ))}
            {recentAccounts.data && !recentAccounts.data.items.length && <p className="sub">{t('ad.acc.empty')}</p>}
          </div>
        </section>
      </div>

      <section className="panel" aria-labelledby="a3">
        <div className="ph"><h2 id="a3">{t('ad.recent')}</h2><Link to="/admin/audit" className="link">{t('ad.seeAudit')}</Link></div>
        <div className="list">
          {(recent.data?.items ?? []).map((e) => (
            <div key={e.id} className="item">
              <div className="t">
                <b className="mono">{e.action}</b>
                <span>{[e.entityType, e.entityId !== null ? `#${e.entityId}` : null].filter(Boolean).join(' ')}{e.reason ? ` · ${e.reason}` : ''}</span>
              </div>
              <span className="sub">{new Date(e.createdAt).toLocaleString(locale, { dateStyle: 'medium', timeStyle: 'short' })}</span>
            </div>
          ))}
          {recent.data && !recent.data.items.length && <p className="sub">{t('ad.au.empty')}</p>}
        </div>
      </section>
    </Shell>
  )
}
