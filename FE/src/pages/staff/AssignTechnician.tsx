import { useMemo, useState } from 'react'
import SkipLink from '../../components/ui/SkipLink'
import ThemeToggle from '../../components/ui/ThemeToggle'
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
          <span className="sc-badge">STUDIO</span>
        </div>
        <span className="sc-nav" />
        <div className="sc-head-right">
          <ThemeToggle className="vh-icon-btn" />
          <span className="sc-staff"><span className="vh-avatar">M</span>Minh · Staff</span>
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
              <h2>{order ? 'This order is not ready to assign' : 'Order not found'}</h2>
              <p>
                {order
                  ? `${order.id} is ${order.status}. Only accepted orders can be given to a technician.`
                  : `There is no order ${id}.`}
              </p>
              <Link to="/staff" className="vh-btn vh-btn--ghost vh-btn--md sc-self-start">
                Back to dashboard
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
        <aside className="sc-rail as-rail" aria-label="Order summary">
          <span className="sc-eyebrow">ACCEPTED ORDER</span>
          <h1 className="as-order-title">{order.title}</h1>
          <span className="vh-mono as-order-id">{order.id} · {order.name || 'Customer'}</span>
          <ul className="as-facts">
            {[
              ['Input', MODE_LABEL[sp.mode]],
              ['Format', sp.type],
              ['Pen', sp.pen],
              ['Ink', sp.ink],
              ['Paper', sp.paper],
              ['Pieces', String(pieces)],
              ['Writing time', `about ${minutes} min`],
              ['AI score', order.evalScore !== undefined ? `${order.evalScore} / 100` : 'n/a'],
              ['Deposit', fmt(depositOf(order.total))],
            ].map(([k, v]) => (
              <li key={k}><span>{k}</span><b>{v}</b></li>
            ))}
          </ul>
          <p className="as-note">
            The customer pays the deposit separately. You can assign now, and the robot starts once the deposit arrives.
          </p>
        </aside>

        <main className="sc-main" id="main">
          <div className="sc-detail">
            <div className="sc-title">
              <span className="sc-eyebrow">STEP 2 OF 2 · ASSIGN</span>
              <h1>Choose a technician</h1>
              <p className="as-lede">
                Each technician looks after several robots. Pick who takes this order, then confirm which of their robots writes it.
              </p>
            </div>

            {assigned && (
              <div className="as-current" role="status">
                <span className="as-current-mark" aria-hidden="true" />
                <span>
                  <b>Already assigned</b> to {assigned.techName} on <span className="vh-mono">{assigned.robotId}</span>.
                  Pick someone else only to reassign.
                </span>
              </div>
            )}

            <ul className="as-techs" aria-label="Technicians">
              {techs.map((t) => {
                const free = freeRobots(t).length
                const load = loadOf(t.id, orders)
                const on = t.id === tech.id
                return (
                  <li key={t.id}>
                    <button className={`as-tech${on ? ' on' : ''}${assigned?.techId === t.id ? ' current' : ''}`} aria-pressed={on} onClick={() => pickTech(t)}>
                      <span className="as-tech-top">
                        <span className="vh-avatar">{t.initials}</span>
                        <span className="as-tech-name">
                          {t.name}
                          {assigned?.techId === t.id
                            ? <em className="as-rec as-rec--current">Assigned to this order</em>
                            : best?.id === t.id && !assigned && <em className="as-rec">Recommended</em>}
                        </span>
                        <span className="vh-mono as-tech-id">{t.id}</span>
                      </span>
                      <span className="as-tech-shift">{t.shift}</span>
                      <span className="as-tech-skills">{t.skills.join(' · ')}</span>
                      <span className="as-tech-stats">
                        <span><b className="vh-mono">{t.robots.length}</b> robots</span>
                        <span className={free ? 'ok' : 'none'}><b className="vh-mono">{free}</b> idle</span>
                        <span><b className="vh-mono">{load}</b> in queue</span>
                      </span>
                      <span className="as-dots" aria-hidden="true">
                        {t.robots.map((r) => <i key={r.id} className={`as-dot as-dot--${r.state}`} title={`${r.id} ${STATE_LABEL[r.state]}`} />)}
                      </span>
                    </button>
                  </li>
                )
              })}
            </ul>

            <section className="sc-block as-robots" aria-label={`${tech.name}'s robots`}>
              <div className="sc-block-head">
                <h2>{tech.name}'s robots</h2>
                <span className="sc-hint">{freeRobots(tech).length ? 'Pick one that is idle' : 'No idle robot right now'}</span>
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
                        <span className="vh-mono as-robot-id">{r.id}{assigned?.robotId === r.id && <em className="as-rec as-rec--current"> · this order</em>}</span>
                        <span className={`as-state as-state--${r.state}`}>{STATE_LABEL[r.state]}</span>
                        <span className="as-ink" title={`Ink ${r.ink}%`}>
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
                <h2>Assigned to {assigned.techName}</h2>
                <p>
                  {order.id} will be written on {assigned.robotId}. {assigned.techName} sees it in their queue as soon as the deposit is paid.
                </p>
                <div className="sc-row">
                  <Link to="/staff" className="vh-btn vh-btn--primary vh-btn--md">Back to dashboard</Link>
                  {nextReview && (
                    <Link to={`/staff/review/${encodeURIComponent(nextReview.id)}`} className="vh-btn vh-btn--ghost vh-btn--md">
                      Review next order
                    </Link>
                  )}
                </div>
              </section>
            ) : (
              <div className="as-confirm">
                <p>
                  {robot
                    ? <>Assign <b>{order.id}</b> to <b>{tech.name}</b> on <b className="vh-mono">{robot.id}</b></>
                    : <>{tech.name} has no idle robot. Pick another technician.</>}
                </p>
                <div className="sc-row">
                  <button className={`vh-btn vh-btn--md ${assigned && !dirty ? 'vh-btn--ghost' : 'vh-btn--primary'}`} disabled={!robot || !dirty} onClick={assign}>
                    {assigned ? (dirty ? 'Reassign order' : 'Already assigned') : 'Assign technician'}
                  </button>
                  <Link to="/staff" className="vh-btn vh-btn--ghost vh-btn--md">Decide later</Link>
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
