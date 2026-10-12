import SkipLink from '../../components/ui/SkipLink'
import ThemeToggle from '../../components/ui/ThemeToggle'
import { Link } from '../../router/router'
import { useAllStaffOrders, useUser } from '../../store/store'
import { MODE_LABEL } from '../staff/evaluate'
import { roster } from '../staff/technicians'
import { phaseOf, useNow, type Phase } from './phase'
import TechRail from './TechRail'
import '../staff/dashboard.css'
import './tech.css'
import '../staff/polish.css'

type Mode = 'preview' | 'qc'

const PHASE = {
  qc: { label: 'Needs QC', note: 'The robot finished. Check the sheets and send photos.', cta: 'Open QC', color: 'var(--accent-text)' },
  live: { label: 'Writing now', note: 'The robot is running. Open it to follow live.', cta: 'Follow live', color: 'var(--accent-text)' },
  ready: { label: 'Ready to operate', note: 'Deposit paid. Preview, then start the robot.', cta: 'Open simulator', color: 'var(--good)' },
  wait: { label: 'Waiting for deposit', note: 'You can preview now. The robot starts after payment.', cta: 'Preview only', color: 'var(--warn)' },
} satisfies Partial<Record<Phase, { label: string; note: string; cta: string; color: string }>>

const ORDER: Record<Mode, (keyof typeof PHASE)[]> = {
  preview: ['live', 'ready', 'wait'],
  qc: ['qc', 'live'],
}

/** First step of the Preview tab: pick which assigned order to operate, then open its simulator. */
export default function PreviewOrders({ mode = 'preview' }: { mode?: Mode }) {
  const user = useUser()
  const orders = useAllStaffOrders()
  const tech = roster().find((t) => t.id === user?.techId)
  const mine = orders.filter((o) => o.assignment?.techId === user?.techId)
  const now = useNow(1000)
  const open = ORDER[mode].flatMap((p) => mine.filter((o) => phaseOf(o, now) === p).map((o) => ({ o, p })))
  const robotState = (id: string) => tech?.robots.find((r) => r.id === id)

  return (
    <div className="sd">
      <SkipLink />
      <TechRail active={mode} />
      <main className="sd-body" id="main">
        <header className="sd-top">
          <div>
            <h1>{mode === 'qc' ? 'Choose an order to check' : 'Choose an order'}</h1>
            <p>
              {mode === 'qc'
                ? 'Orders the robot has finished appear here. Pick one to tick the checklist and send photos to the customer.'
                : 'Pick the order you want to operate. The simulator opens next, and the real robot starts from there.'}
            </p>
          </div>
          <div className="sd-top-right">
            <ThemeToggle className="vh-icon-btn" />
          </div>
        </header>

        {open.length ? (
          <ul className="po-grid" aria-label="Orders to operate">
            {open.map(({ o, p }, i) => {
              const info = PHASE[p]
              const r = robotState(o.assignment!.robotId)
              const mins = Math.max(1, (o.spec.mins || 4) * (o.spec.qty || 1))
              return (
                <li key={o.id}>
                  <Link to={`/tech/${p === 'qc' ? 'qc' : 'preview'}/${encodeURIComponent(o.id)}`} className={`po-card po-card--${p}`}>
                    <span className="po-top">
                      <span className="vh-mono po-id">{o.id}</span>
                      <span className="vh-chip" style={{ color: info.color }}>{info.label}</span>
                    </span>
                    <span className="po-title">{o.title}</span>
                    <span className="sd-sub">{o.name || 'Customer'} · {MODE_LABEL[o.spec.mode]}</span>
                    <dl className="po-facts">
                      <div><dt>Paper</dt><dd><i className="tp-sw" style={{ background: o.spec.paperColor }} />{o.spec.paper}</dd></div>
                      <div><dt>Pen</dt><dd>{o.spec.pen}</dd></div>
                      <div><dt>Ink</dt><dd><i className="tp-sw" style={{ background: o.spec.inkColor }} />{o.spec.ink}</dd></div>
                      <div><dt>Pieces</dt><dd>{o.spec.qty || 1}</dd></div>
                      <div><dt>Writing time</dt><dd>about {mins} min</dd></div>
                      <div><dt>Robot</dt><dd>{o.assignment!.robotId}{r ? `, ${r.state}` : ''}</dd></div>
                    </dl>
                    <span className="sd-sub">{info.note}</span>
                    <span className={`vh-btn vh-btn--md ${p === 'wait' ? 'vh-btn--ghost' : 'vh-btn--primary'} po-cta`}>
                      {i === 0 && p !== 'wait' ? `${info.cta}, next up` : info.cta}
                    </span>
                  </Link>
                </li>
              )
            })}
          </ul>
        ) : (
          <section className="sd-card" aria-labelledby="po-empty-h">
            <div className="sd-empty">
              <b id="po-empty-h">{mode === 'qc' ? 'Nothing to check yet' : 'No order to operate'}</b>
              <span>
                {mode === 'qc'
                  ? 'An order lands here when its robot run finishes. Follow a run from the Preview tab.'
                  : <>Orders show up here after staff assign them to you. The <Link to="/tech" className="vh-link">dashboard</Link> keeps everything you have finished.</>}
              </span>
            </div>
          </section>
        )}
      </main>
    </div>
  )
}
