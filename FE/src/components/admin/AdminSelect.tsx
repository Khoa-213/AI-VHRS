import { CaretDown, Check } from '@phosphor-icons/react'
import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'
import { createPortal } from 'react-dom'

interface Option { value: string; label: string }

/** Theme-aware select with keyboard navigation and a viewport-bounded popup. */
export default function AdminSelect({ value, onChange, options, label, disabled = false }: {
  value: string; onChange: (value: string) => void; options: Option[]; label: string; disabled?: boolean
}) {
  const id = useId()
  const trigger = useRef<HTMLButtonElement>(null)
  const popup = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const [position, setPosition] = useState({ top: 0, left: 0, width: 0, maxHeight: 280 })
  const selected = options.findIndex((item) => item.value === value)
  const search = useRef({ text: '', at: 0 })
  const expanded = open && !disabled

  const show = () => {
    const el = trigger.current
    if (!el || disabled) return
    const rect = el.getBoundingClientRect()
    const below = window.innerHeight - rect.bottom - 16
    const above = rect.top - 16
    const height = Math.min(280, Math.max(below, above))
    const width = Math.min(Math.max(rect.width, 220), window.innerWidth - 24)
    setPosition({ top: below >= Math.min(280, above) ? rect.bottom + 6 : Math.max(12, rect.top - height - 6), left: Math.max(12, Math.min(rect.left, window.innerWidth - width - 12)), width, maxHeight: height })
    setActive(Math.max(0, selected))
    setOpen(true)
  }

  const choose = (index: number) => {
    if (disabled || !options[index]) return
    onChange(options[index].value)
    setOpen(false)
    trigger.current?.focus()
  }

  useEffect(() => {
    if (!expanded) return
    const outside = (event: PointerEvent) => {
      if (!trigger.current?.contains(event.target as Node) && !popup.current?.contains(event.target as Node)) setOpen(false)
    }
    const close = (event: Event) => { if (!popup.current?.contains(event.target as Node)) setOpen(false) }
    document.addEventListener('pointerdown', outside)
    window.addEventListener('resize', close)
    window.addEventListener('scroll', close, true)
    return () => {
      document.removeEventListener('pointerdown', outside)
      window.removeEventListener('resize', close)
      window.removeEventListener('scroll', close, true)
    }
  }, [expanded])

  useEffect(() => {
    if (expanded) popup.current?.querySelector(`[id="${id}-${active}"]`)?.scrollIntoView({ block: 'nearest' })
  }, [active, expanded, id])

  const keyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === 'Tab') { setOpen(false); return }
    if (event.key === 'Escape') { event.preventDefault(); setOpen(false); return }
    if (['ArrowDown', 'ArrowUp', 'Home', 'End', 'Enter', ' '].includes(event.key)) {
      event.preventDefault()
      if (!expanded) { show(); return }
      if (event.key === 'Enter' || event.key === ' ') choose(active)
      else setActive((n) => event.key === 'Home' ? 0 : event.key === 'End' ? options.length - 1 : (n + (event.key === 'ArrowDown' ? 1 : -1) + options.length) % options.length)
    } else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
      event.preventDefault()
      const now = Date.now()
      search.current.text = (now - search.current.at < 700 ? search.current.text : '') + event.key.toLocaleLowerCase()
      search.current.at = now
      const index = options.findIndex((item) => item.label.toLocaleLowerCase().startsWith(search.current.text))
      if (!expanded) show()
      if (index >= 0) setActive(index)
    }
  }

  return (
    <div className="adm-select">
      <button ref={trigger} type="button" className="adm-select-trigger" role="combobox" aria-label={label} aria-haspopup="listbox" aria-expanded={expanded} aria-controls={expanded ? id : undefined} aria-activedescendant={expanded ? `${id}-${active}` : undefined} disabled={disabled} onKeyDown={keyDown} onBlur={(event) => { if (!popup.current?.contains(event.relatedTarget as Node)) setOpen(false) }} onClick={() => expanded ? setOpen(false) : show()}>
        <span>{options[selected]?.label ?? label}</span><CaretDown size={16} aria-hidden />
      </button>
      {expanded && createPortal(
        <div ref={popup} id={id} role="listbox" aria-label={label} className="adm-select-menu" style={position}>
          {options.map((item, index) => (
            <div key={item.value} id={`${id}-${index}`} role="option" aria-selected={value === item.value} className={`adm-select-option${active === index ? ' active' : ''}`} onPointerMove={() => setActive(index)} onMouseDown={(event) => event.preventDefault()} onClick={(event) => { event.preventDefault(); choose(index) }}>
              <span>{item.label}</span>{value === item.value && <Check size={16} weight="bold" aria-hidden />}
            </div>
          ))}
        </div>, trigger.current?.closest('.adm-app') ?? document.body,
      )}
    </div>
  )
}
