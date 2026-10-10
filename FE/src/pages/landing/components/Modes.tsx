import { ORDER_HREF, svgProps } from '../../../constants'
import Reveal from '../../../components/ui/Reveal'

const MODES = [
  {
    mode: 'text',
    title: 'Text + Single-Line Font',
    copy: 'Type your message, pick a digital calligraphy style, and preview the exact strokes before the pen touches paper.',
    sample: 'An khang thịnh vượng',
    link: 'Browse styles →',
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
    title: 'Upload Handwriting Photo',
    copy: 'Snap or scan any handwritten page. We clean it up, trace each stroke, and turn it into a path the arm can follow.',
    link: 'Start with a photo →',
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
    title: 'iPad Live Canvas Drawing',
    copy: 'Write directly with Apple Pencil. Pressure, speed and stroke order are captured live and replayed by the arm.',
    link: 'Open the canvas →',
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
  return (
    <section id="modes" className="lp-modes">
      <div className="lp-modes-inner">
        <Reveal className="lp-modes-head" dur=".8s">
          <h2 className="lp-h2-modes">Bring your hand. We bring the arm.</h2>
          <p className="lp-modes-lede">
            Every mode ends the same way: a smooth, verified trajectory written in real ink.
          </p>
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
                <h3>{m.title}</h3>
                <p>{m.copy}</p>
              </div>
              {'sample' in m && <div className="lp-sample">{m.sample}</div>}
              <span className="lp-mode-link">{m.link}</span>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  )
}
