import { ORDER_HREF, svgProps } from '../../../constants'
import Reveal from '../../../components/ui/Reveal'
import { useT } from '../../../i18n'

const MODES = [
  {
    mode: 'text',
    sample: 'An khang thịnh vượng',
    icon: (
      <>
        <polyline points="4 7 4 4 20 4 20 7" />
        <line x1="9" x2="15" y1="20" y2="20" />
        <line x1="12" x2="12" y1="4" y2="20" />
      </>
    ),
  },
  {
    mode: 'upload',
    icon: (
      <>
        <rect width="18" height="18" x="3" y="3" rx="2" />
        <circle cx="9" cy="9" r="2" />
        <path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21" />
      </>
    ),
  },
  {
    mode: 'draw',
    icon: (
      <>
        <path d="M15.707 21.293a1 1 0 0 1-1.414 0l-1.586-1.586a1 1 0 0 1 0-1.414l5.586-5.586a1 1 0 0 1 1.414 0l1.586 1.586a1 1 0 0 1 0 1.414z" />
        <path d="m18 13-1.375-6.874a1 1 0 0 0-.746-.776L3.235 2.028a1 1 0 0 0-1.207 1.207L5.35 15.879a1 1 0 0 0 .776.746L13 18" />
        <path d="m2.3 2.3 7.286 7.286" />
        <circle cx="11" cy="11" r="2" />
      </>
    ),
  },
] as const

export default function Modes() {
  const t = useT()
  return (
    <section id="modes" className="lp-modes">
      <div className="lp-modes-inner">
        <Reveal className="lp-modes-head" dur=".8s">
          <h2 className="lp-h2-modes">{t('lp.modes.title')}</h2>
          <p className="lp-modes-lede">{t('lp.modes.lede')}</p>
        </Reveal>

        <div className="lp-mode-grid">
          {MODES.map((m, i) => (
            <Reveal
              key={m.mode}
              as="a"
              href={`${ORDER_HREF}#mode=${m.mode}`}
              className={`lp-mode-card${i === 0 ? ' lp-mode-card--lead' : ''}`}
              delay={i * 0.12}
              dur=".8s"
            >
              <span className="lp-mode-icon">
                <svg width="28" height="28" viewBox="0 0 24 24" strokeWidth="1.8" {...svgProps}>
                  {m.icon}
                </svg>
              </span>
              <div className="lp-mode-body">
                <h3>{t(`lp.mode.${m.mode}.title`)}</h3>
                <p>{t(`lp.mode.${m.mode}.copy`)}</p>
              </div>
              {'sample' in m && <div className="lp-sample">{m.sample}</div>}
              <span className="lp-mode-link">{t(`lp.mode.${m.mode}.link`)}</span>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  )
}
