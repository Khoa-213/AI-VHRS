import { useMemo, useState } from 'react'
import { useT, useTn } from '../../i18n'
import SkipLink from '../../components/ui/SkipLink'
import ThemeToggle from '../../components/ui/ThemeToggle'
import LanguageToggle from '../../components/ui/LanguageToggle'
import { Link } from '../../router/router'
import { saveStaffOrder, useAllStaffOrders } from '../../store/store'
import { depositOf, fmt } from '../../utils/format'
import { MODE_LABEL } from './evaluate'
import { STATE_LABEL, freeRobots, loadOf, recommend, roster, type Technician } from './technicians'
import StaffRail from './StaffRail'
import './dashboard.css'
import './staff.css'
import './assign.css'
import './polish.css'

export default function AssignTechnician({ id }: { id: string }) {
  const t = useT()
  const tn = useTn()
  const orders = useAllStaffOrders()
  const order = orders.find((o) => o.id === id)
  const techs = useMemo(() => roster(), [])
  const best = recommend(techs, orders)

  const [techId, setTechId] = useState<string>(order?.assignment?.techId ?? best?.id ?? techs[0].id)
  const tech = techs.find((t) => t.id === techId) ?? techs[0]
  const [robotId, setRobotId] = useState<string | undefined>(order?.assignment?.robotId)
  const robot = tech.robots.find((r) => r.id === robotId && r.state !== 'offline') ?? freeRobots(tech)[0]
  const [justSaved, setJustSaved] = useState(false)

  const header = (
    <header className="vh-header sc-header">
      <div className="vh-header-inner">
        <div className="sc-brand">
          <Link to="/" className="vh-logo">AI-VHRS</Link>
          <span className="sc-badge">{t('sc.badge')}</span>
        </div>
        <span className="sc-nav" />
        <div className="sc-head-right">
          <ThemeToggle className="vh-icon-btn" />
          <LanguageToggle className="vh-icon-btn" />
          <span className="sc-staff"><span className="vh-avatar">M</span>{t('sc.staffName')}</span>
        </div>
      </div>
    </header>
  )

  if (!order || order.status !== 'Accepted') {
    return (
      <div className="sd sd--sc">
      <StaffRail active="review" />
      <div className="sc">
        <SkipLink />
        {header}
        <main className="sc-main" id="main">
          <div className="sc-detail">
            <div className="sc-done bad">
              <h2>{t(order ? 'as.notReady' : 'as.notFound')}</h2>
              <p>
                {order
                  ? t('as.notReadyBody', { id: order.id, status: t(`status.${order.status}`) })
                  : t('as.notFoundBody', { id })}
              </p>
              <Link to="/staff" className="vh-btn vh-btn--ghost vh-btn--md sc-self-start">
                {t('as.backDash')}
              </Link>
            </div>
          </div>
        </main>
      </div>
      </div>
    )
  }

  const sp = order.spec
  const pieces = sp.qty || 1
  const minutes = Math.max(1, (sp.mins || 4) * pieces)
  const assigned = order.assignment
  const dirty = !assigned || assigned.techId !== tech.id || assigned.robotId !== robot?.id

  const assign = () => {
    if (!robot) return
    saveStaffOrder({
      ...order,
      assignment: { techId: tech.id, techName: tech.name, robotId: robot.id, at: new Date().toISOString() },
    })
    setJustSaved(true)
  }

  const nextReview = orders.find((o) => o.status === 'Pending')
  const pickTech = (t: Technician) => {
    setTechId(t.id)
    setRobotId(undefined)
    setJustSaved(false)
  }

  return (
    <div className="sd sd--sc">
      <StaffRail active="review" />
      <div className="sc">
      <SkipLink />
      {header}
      <div className="sc-layout">
        <aside className="sc-rail as-rail" aria-label={t('as.accepted')}>
          <span className="sc-eyebrow">{t('as.accepted')}</span>
          <h1 className="as-order-title">{tn(order.title)}</h1>
          <span className="vh-mono as-order-id">{order.id} · {order.name || t('common.customer')}</span>
          <ul className="as-facts">
            {[
              [t('as.f.input'), tn(MODE_LABEL[sp.mode])],
              [t('as.f.format'), tn(sp.type)],
              [t('as.f.pen'), tn(sp.pen)],
              [t('as.f.ink'), tn(sp.ink)],
              [t('as.f.paper'), tn(sp.paper)],
              [t('as.f.pieces'), String(pieces)],
              [t('as.f.time'), t('as.f.timeVal', { n: minutes })],
              [t('as.f.score'), order.evalScore !== undefined ? `${order.evalScore} / 100` : t('sc.na')],
              [t('as.f.deposit'), fmt(depositOf(order.total))],
            ].map(([k, v]) => (
              <li key={k}><span>{k}</span><b>{v}</b></li>
            ))}
          </ul>
          <p className="as-note">
            {t('as.sideNote')}
          </p>
        </aside>

        <main className="sc-main" id="main">
          <div className="sc-detail">
            <div className="sc-title">
              <span className="sc-eyebrow">{t('as.step')}</span>
              <h1>{t('as.title')}</h1>
              <p className="as-lede">{t('as.lede')}</p>
            </div>

            {assigned && (
              <div className="as-current" role="status">
                <span className="as-current-mark" aria-hidden="true" />
                <span>
                  <b>{t('as.already')}</b> {t('as.alreadyBody', { name: assigned.techName, robot: assigned.robotId })}
                </span>
              </div>
            )}

            <ul className="as-techs" aria-label={t('as.techs')}>
              {techs.map((tc) => {
                const free = freeRobots(tc).length
                const load = loadOf(tc.id, orders)
                const on = tc.id === tech.id
                return (
                  <li key={tc.id}>
                    <button className={`as-tech${on ? ' on' : ''}${assigned?.techId === tc.id ? ' current' : ''}`} aria-pressed={on} onClick={() => pickTech(tc)}>
                      <span className="as-tech-top">
                        <span className="vh-avatar">{tc.initials}</span>
                        <span className="as-tech-name">
                          {tc.name}
                          {assigned?.techId === tc.id
                            ? <em className="as-rec as-rec--current">{t('as.thisOrder')}</em>
                            : best?.id === tc.id && !assigned && <em className="as-rec">{t('as.recommended')}</em>}
                        </span>
                        <span className="vh-mono as-tech-id">{tc.id}</span>
                      </span>
                      <span className="as-tech-shift">{tn(tc.shift)}</span>
                      <span className="as-tech-skills">{tc.skills.map((k) => tn(k)).join(' · ')}</span>
                      <span className="as-tech-stats">
                        <span><b className="vh-mono">{tc.robots.length}</b> {t('as.robots')}</span>
                        <span className={free ? 'ok' : 'none'}><b className="vh-mono">{free}</b> {t('as.idle')}</span>
                        <span><b className="vh-mono">{load}</b> {t('as.inQueue')}</span>
                      </span>
                      <span className="as-dots" aria-hidden="true">
                        {tc.robots.map((r) => <i key={r.id} className={`as-dot as-dot--${r.state}`} title={`${r.id} ${tn(STATE_LABEL[r.state])}`} />)}
                      </span>
                    </button>
                  </li>
                )
              })}
            </ul>

            <section className="sc-block as-robots" aria-label={t('as.robotsOf', { name: tech.name })}>
              <div className="sc-block-head">
                <h2>{t('as.robotsOf', { name: tech.name })}</h2>
                <span className="sc-hint">{t(freeRobots(tech).length ? 'as.pickIdle' : 'as.noIdle')}</span>
              </div>
              <ul className="as-robot-list">
                {tech.robots.map((r) => {
                  const usable = r.state === 'idle'
                  const on = robot?.id === r.id
                  return (
                    <li key={r.id}>
                      <button
                        className={`as-robot${on ? ' on' : ''}${assigned?.robotId === r.id ? ' current' : ''}`}
                        disabled={!usable}
                        aria-pressed={on}
                        onClick={() => { setRobotId(r.id); setJustSaved(false) }}
                      >
                        <span className="vh-mono as-robot-id">{r.id}{assigned?.robotId === r.id && <em className="as-rec as-rec--current"> · {t('as.thisOrderShort')}</em>}</span>
                        <span className={`as-state as-state--${r.state}`}>{tn(STATE_LABEL[r.state])}</span>
                        <span className="as-ink" title={t('as.ink', { n: r.ink })}>
                          <i><b style={{ width: `${r.ink}%` }} /></i>
                          <span className="vh-mono">{r.ink}%</span>
                        </span>
                      </button>
                    </li>
                  )
                })}
              </ul>
            </section>

            {justSaved && assigned ? (
              <section className="sc-done ok" role="status">
                <h2>{t('as.savedTitle', { name: assigned.techName })}</h2>
                <p>{t('as.savedBody', { id: order.id, robot: assigned.robotId, name: assigned.techName })}</p>
                <div className="sc-row">
                  <Link to="/staff" className="vh-btn vh-btn--primary vh-btn--md">{t('as.backDash')}</Link>
                  {nextReview && (
                    <Link to={`/staff/review/${encodeURIComponent(nextReview.id)}`} className="vh-btn vh-btn--ghost vh-btn--md">
                      {t('as.nextReview')}
                    </Link>
                  )}
                </div>
              </section>
            ) : (
              <div className="as-confirm">
                <p>
                  {robot
                    ? t('as.confirmAssign', { id: order.id, name: tech.name, robot: robot.id })
                    : t('as.noIdleTech', { name: tech.name })}
                </p>
                <div className="sc-row">
                  <button className={`vh-btn vh-btn--md ${assigned && !dirty ? 'vh-btn--ghost' : 'vh-btn--primary'}`} disabled={!robot || !dirty} onClick={assign}>
                    {assigned ? t(dirty ? 'as.reassign' : 'as.alreadyBtn') : t('as.assignBtn')}
                  </button>
                  <Link to="/staff" className="vh-btn vh-btn--ghost vh-btn--md">{t('as.later')}</Link>
                </div>
              </div>
            )}
          </div>
        </main>
      </div>
      </div>
    </div>
  )
}
