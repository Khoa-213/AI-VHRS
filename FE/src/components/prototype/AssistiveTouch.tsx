import { X } from '@phosphor-icons/react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { ORDER_HREF } from '../../constants'
import { useT } from '../../i18n'
import { STATUS_COLORS } from '../../constants/catalog'
import { Link, usePath } from '../../router/router'
import {
  resetDemo, setPrototypeMode, useOrders, usePrototypeMode,
} from '../../store/store'
import { STAGES, STEPS } from './steps'
import './assistive.css'

const SIZE = 56
const MARGIN = 12
const KEY = 'aivhrs-touch'
const DRAG_PX = 6

interface Pos {
  side: 'left' | 'right'
  y: number
}


const clampY = (y: number) => Math.max(MARGIN, Math.min(window.innerHeight - SIZE - MARGIN, y))

function loadPos(): Pos {
  try {
    const p = JSON.parse(localStorage.getItem(KEY) ?? 'null') as Pos | null
    if (p && (p.side === 'left' || p.side === 'right') && typeof p.y === 'number') return { side: p.side, y: clampY(p.y) }
  } catch {
    // Private mode or bad JSON: use the default.
  }
  return { side: 'right', y: clampY(window.innerHeight - SIZE - 96) }
}

/**
 * Floating round button, like iOS AssistiveTouch. Drag it to any edge; tap it
 * for the prototype tools that drive the order flow. Accounts are real now:
 * sign in on /login, sign out from the account page or the staff and technician rails.
 */
export default function AssistiveTouch() {
  const t = useT()
  const on = usePrototypeMode()
  const orders = useOrders()
  const path = usePath()
  const [pos, setPos] = useState<Pos>(loadPos)
  const [open, setOpen] = useState(false)
  const [idle, setIdle] = useState(false)
  const btn = useRef<HTMLButtonElement>(null)
  const drag = useRef<{ id: number; sx: number; sy: number; moved: boolean } | null>(null)
  const idleTimer = useRef<number | undefined>(undefined)
  const snapTimer = useRef<number | undefined>(undefined)

  const wake = useCallback(() => {
    setIdle(false)
    window.clearTimeout(idleTimer.current)
    idleTimer.current = window.setTimeout(() => setIdle(true), 3200)
  }, [])

  useEffect(() => {
    wake()
    return () => {
      window.clearTimeout(idleTimer.current)
      window.clearTimeout(snapTimer.current)
    }
  }, [wake])

  useEffect(() => {
    const onResize = () => setPos((p) => ({ ...p, y: clampY(p.y) }))
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false)
        btn.current?.focus()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open])

  const down = (e: React.PointerEvent<HTMLButtonElement>) => {
    if (e.button !== 0) return
    e.currentTarget.setPointerCapture(e.pointerId)
    drag.current = { id: e.pointerId, sx: e.clientX, sy: e.clientY, moved: false }
    window.clearTimeout(snapTimer.current)
    wake()
  }
  const move = (e: React.PointerEvent<HTMLButtonElement>) => {
    const d = drag.current
    const el = btn.current
    if (!d || d.id !== e.pointerId || !el) return
    const dx = e.clientX - d.sx
    const dy = e.clientY - d.sy
    if (!d.moved && Math.hypot(dx, dy) < DRAG_PX) return
    d.moved = true
    el.classList.add('dragging')
    el.style.translate = `${dx}px ${dy}px`
  }
  const up = (e: React.PointerEvent<HTMLButtonElement>) => {
    const d = drag.current
    const el = btn.current
    drag.current = null
    if (!d || !el) return
    el.classList.remove('dragging')
    if (!d.moved) {
      setOpen((o) => !o)
      return
    }
    // Snap to the nearest side, keeping the vertical position the finger left it at.
    const side: Pos['side'] = e.clientX < window.innerWidth / 2 ? 'left' : 'right'
    const y = clampY(pos.y + (e.clientY - d.sy))
    const span = window.innerWidth - SIZE - MARGIN * 2
    const rest = pos.side === 'left' ? 0 : span
    const target = side === 'left' ? 0 : span
    el.style.translate = `${target - rest}px ${y - pos.y}px`
    snapTimer.current = window.setTimeout(() => {
      el.style.translate = ''
      const next = { side, y }
      setPos(next)
      try {
        localStorage.setItem(KEY, JSON.stringify(next))
      } catch {
        // Position just will not persist.
      }
    }, 240)
  }

  const idInPath = /^\/orders\/([^/]+)\//.exec(path)?.[1]
  const order = orders.find((o) => o.id === (idInPath && decodeURIComponent(idInPath))) ?? orders[0]
  const step = order ? STEPS[order.status] : undefined
  const stageIdx = order ? STAGES.indexOf(order.status === 'Rewriting' ? 'Written' : order.status) : -1
  const [color] = order ? STATUS_COLORS[order.status] : ['var(--t1)']

  const panelStyle: React.CSSProperties = {
    [pos.side]: MARGIN,
    ...(pos.y > window.innerHeight / 2 ? { bottom: window.innerHeight - pos.y + 8 } : { top: pos.y + SIZE + 8 }),
  }

  return (
    <div className="at" data-side={pos.side}>
      {open && <div className="at-backdrop" onPointerDown={() => setOpen(false)} />}

      <button
        ref={btn}
        type="button"
        className={`at-btn${idle && !open ? ' idle' : ''}${open ? ' open' : ''}`}
        style={{ top: pos.y, [pos.side]: MARGIN }}
        aria-label={t('at.title')}
        aria-expanded={open}
        aria-haspopup="dialog"
        onPointerDown={down}
        onPointerMove={move}
        onPointerUp={up}
        onPointerCancel={up}
        onPointerEnter={wake}
        onFocus={wake}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            setOpen((o) => !o)
          }
        }}
      >
        <i aria-hidden />
      </button>

      {open && (
        <div className="at-panel" role="dialog" aria-label={t('at.title')} style={panelStyle}>
          <div className="at-head">
            <b>{t('at.title')}</b>
            <button type="button" className="at-x" aria-label={t('common.close')} onClick={() => setOpen(false)}>
              <X size={18} />
            </button>
          </div>

          <section aria-labelledby="at-proto">
            <div className="at-switch-row">
              <h2 id="at-proto">{t('at.mode')}</h2>
              <button
                type="button"
                role="switch"
                aria-checked={on}
                aria-labelledby="at-proto"
                className={`at-switch${on ? ' on' : ''}`}
                onClick={() => setPrototypeMode(!on)}
              >
                <i />
              </button>
            </div>

            {on && order && step && (
              <div className="at-flow">
                <div className="at-order">
                  <span className="vh-mono">{order.id}</span>
                  <span className="vh-chip" style={{ color }}>{t(`status.${order.status}`)}</span>
                </div>
                <ol className="at-stages" aria-label={t('at.progress')}>
                  {STAGES.map((s, i) => (
                    <li key={s} className={i < stageIdx ? 'done' : i === stageIdx ? 'now' : ''} title={t(`status.${s}`)} />
                  ))}
                </ol>
                <p>{t(`step.${order.status}.hint`)}</p>
                <div className="at-actions">
                  {step.simulate && (
                    <button type="button" className="vh-btn vh-btn--primary vh-btn--sm" onClick={() => step.simulate!.run(order)}>
                      {t(`step.${order.status}.sim`)}
                    </button>
                  )}
                  {step.go && (
                    <Link to={step.go.to(order)} className="vh-btn vh-btn--ghost vh-btn--sm" onClick={() => setOpen(false)}>
                      {t(`step.${order.status}.go`)}
                    </Link>
                  )}
                </div>
              </div>
            )}
            {on && !order && (
              <div className="at-flow">
                <p>{t('at.noOrders')}</p>
                <Link to={ORDER_HREF} className="vh-btn vh-btn--ghost vh-btn--sm" onClick={() => setOpen(false)}>{t('at.createOrder')}</Link>
              </div>
            )}

            <div className="at-links">
              <Link to="/" onClick={() => setOpen(false)}>{t('at.landing')}</Link>
              <Link to={ORDER_HREF} onClick={() => setOpen(false)}>{t('at.newOrder')}</Link>
              <Link to="/account/drafts" onClick={() => setOpen(false)}>{t('nav.drafts')}</Link>
              <button type="button" onClick={resetDemo}>{t('at.reset')}</button>
            </div>
          </section>
        </div>
      )}
    </div>
  )
}
