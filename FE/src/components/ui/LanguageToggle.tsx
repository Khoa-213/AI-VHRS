import { Check, Translate } from '@phosphor-icons/react'
import { useEffect, useRef, useState } from 'react'
import { LANGS, setLang, useLang, useT } from '../../i18n'
import './language.css'

/** Icon button next to the theme toggle. Opens a small menu with the three languages. */
export default function LanguageToggle({ className }: { className: string }) {
  const lang = useLang()
  const t = useT()
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!open) return
    const onDown = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false)
        trigger.current?.focus()
      }
    }
    document.addEventListener('pointerdown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const current = LANGS.find((l) => l.id === lang)!

  return (
    <div className="lang" ref={root}>
      <button
        ref={trigger}
        type="button"
        className={`${className} lang-btn`}
        aria-label={`${t('lang.label')}: ${current.name}`}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <Translate size={19} aria-hidden />
        <span className="lang-code">{current.code}</span>
      </button>
      {open && (
        <ul className="lang-menu" role="menu" aria-label={t('lang.label')}>
          {LANGS.map((l) => (
            <li key={l.id} role="none">
              <button
                type="button"
                role="menuitemradio"
                aria-checked={l.id === lang}
                lang={l.id}
                onClick={() => {
                  setLang(l.id)
                  setOpen(false)
                  trigger.current?.focus()
                }}
              >
                <span>{l.name}</span>
                {l.id === lang && <Check size={16} aria-hidden />}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
