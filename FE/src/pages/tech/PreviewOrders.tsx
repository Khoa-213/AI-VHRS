import { useT, useTn } from '../../i18n'
import Shell from '../../components/ws/Shell'
import { Link } from '../../router/router'
import { useAllStaffOrders, useUser } from '../../store/store'
import { MODE_LABEL } from '../staff/evaluate'
import { STATE_LABEL, roster } from '../staff/technicians'
import { phaseOf, useNow, type Phase } from './phase'
import '../staff/dashboard.css'
import '../staff/polish.css'
import './tech.css'

type Mode = 'preview' | 'qc'

const PHASE = {
  qc: { color: 'var(--accent-text)' },
  live: { color: 'var(--accent-text)' },
  ready: { color: 'var(--good)' },
  wait: { color: 'var(--warn)' },
} satisfies Partial<Record<Phase, { color: string }>>

const ORDER: Record<Mode, (keyof typeof PHASE)[]> = {
  preview: ['live', 'ready', 'wait'],
  qc: ['qc', 'live'],
}

/** First step of the Preview tab: pick which assigned order to operate, then open its simulator. */
export default function PreviewOrders({ mode = 'preview' }: { mode?: Mode }) {
  const t = useT()
  const tn = useTn()
  const user = useUser()
  const orders = useAllStaffOrders()
  const tech = roster().find((r) => r.id === user?.techId)
  const mine = orders.filter((o) => o.assignment?.techId === user?.techId)
  const now = useNow(1000)
  const open = ORDER[mode].flatMap((p) => mine.filter((o) => phaseOf(o, now) === p).map((o) => ({ o, p })))
  const robotState = (id: string) => tech?.robots.find((r) => r.id === id)

  return (
    <Shell area="tech" active={mode} title={t(mode === 'qc' ? 'po.titleQc' : 'po.title')} lede={t(mode === 'qc' ? 'po.bodyQc' : 'po.body')}>
      {open.length ? (
        <ul className="po-grid" aria-label={t('po.aria')}>
          {open.map(({ o, p }, i) => {
            const info = PHASE[p]
            const r = robotState(o.assignment!.robotId)
            const mins = Math.max(1, (o.spec.mins || 4) * (o.spec.qty || 1))
            return (
              <li key={o.id}>
                <Link to={`/tech/${p === 'qc' ? 'qc' : 'preview'}/${encodeURIComponent(o.id)}`} className={`po-card po-card--${p}`}>
                  <span className="po-top">
                    <span className="vh-mono po-id">{o.id}</span>
                    <span className="vh-chip" style={{ color: info.color }}>{t(`po.${p}.label`)}</span>
                  </span>
                  <span className="po-title">{tn(o.title)}</span>
                  <span className="sd-sub">{o.name || t('common.customer')} · {tn(MODE_LABEL[o.spec.mode])}</span>
                  <dl className="po-facts">
                    <div><dt>{t('po.paper')}</dt><dd><i className="tp-sw" style={{ background: o.spec.paperColor }} />{tn(o.spec.paper)}</dd></div>
                    <div><dt>{t('po.pen')}</dt><dd>{tn(o.spec.pen)}</dd></div>
                    <div><dt>{t('po.ink')}</dt><dd><i className="tp-sw" style={{ background: o.spec.inkColor }} />{tn(o.spec.ink)}</dd></div>
                    <div><dt>{t('po.pieces')}</dt><dd>{o.spec.qty || 1}</dd></div>
                    <div><dt>{t('po.time')}</dt><dd>{t('po.timeVal', { n: mins })}</dd></div>
                    <div><dt>{t('po.robot')}</dt><dd>{o.assignment!.robotId}{r ? `, ${tn(STATE_LABEL[r.state])}` : ''}</dd></div>
                  </dl>
                  <span className="sd-sub">{t(`po.${p}.note`)}</span>
                  <span className={`vh-btn vh-btn--md ${p === 'wait' ? 'vh-btn--ghost' : 'vh-btn--primary'} po-cta`}>
                    {i === 0 && p !== 'wait' ? t('po.nextUp', { cta: t(`po.${p}.cta`) }) : t(`po.${p}.cta`)}
                  </span>
                </Link>
              </li>
            )
          })}
        </ul>
      ) : (
        <section className="sd-card" aria-labelledby="po-empty-h">
          <div className="sd-empty">
            <b id="po-empty-h">{t(mode === 'qc' ? 'po.emptyQc' : 'po.empty')}</b>
            <span>{mode === 'qc' ? t('po.emptyQcBody') : t('po.emptyBody', { link: t('po.dashboard') })}</span>
          </div>
        </section>
      )}
    </Shell>
  )
}
