import { useState, type RefObject } from 'react'
import { TextItalic, TextStrikethrough, TextUnderline, X } from '@phosphor-icons/react'
import { useT } from '../../i18n'
import { SIZE_MAX, SIZE_MIN, applyStyle, indexAt, length, offsetAt, type Span, type StyleChange } from './textSpans'

/**
 * The toolbar under the message box: select part of the words in the box, then italic, underline, double underline,
 * strikethrough, a letter height of its own, or clear. The box keeps showing plain letters, on purpose: the browser never
 * draws a style, the preview picture (drawn by the backend from the robot's strokes) is the only place a style shows.
 * Below the buttons, the formatted parts are listed in words; one click selects a part in the box, the cross removes it.
 */
export default function TextStyleBar({ box, text, spans, onChange }: {
  box: RefObject<HTMLTextAreaElement | null>
  text: string
  spans: Span[]
  onChange: (spans: Span[]) => void
}) {
  const t = useT()
  const [size, setSize] = useState('')
  const [note, setNote] = useState('')
  const total = length(text)

  /** The selection in the box, as the backend counts characters. */
  const selection = (): [number, number] | null => {
    const el = box.current
    if (!el || el.selectionStart === el.selectionEnd) return null
    return [offsetAt(text, el.selectionStart), offsetAt(text, el.selectionEnd)]
  }

  const change = (what: StyleChange) => {
    const range = selection()
    if (!range) return setNote(t('co.fmt.needSelection'))
    const next = applyStyle(spans, total, range[0], range[1], what)
    if (!next) return setNote(t('co.fmt.tooMany'))
    setNote('')
    onChange(next)
  }

  const applySize = () => {
    const mm = Number(size)
    if (!size.trim() || !Number.isFinite(mm) || mm < SIZE_MIN || mm > SIZE_MAX) return setNote(t('co.fmt.badSize'))
    change({ size: mm })
  }

  const select = (span: Span) => {
    const el = box.current
    if (!el) return
    el.focus()
    el.setSelectionRange(indexAt(text, span.start), indexAt(text, span.end))
  }

  const words = (span: Span): string => {
    const part = [...text.normalize('NFC')].slice(span.start, span.end).join('').replace(/\s+/g, ' ').trim()
    return part.length > 28 ? `${part.slice(0, 28)}…` : part
  }

  // The buttons must not take the focus away from the box, or its selection is lost on some browsers.
  const keep = (e: React.MouseEvent) => e.preventDefault()
  const button = (label: string, icon: React.ReactNode, what: StyleChange, key: string) => (
    <button key={key} type="button" className="co-fmt-btn" onMouseDown={keep} onClick={() => change(what)} aria-label={label} title={label}>
      {icon}<span>{label}</span>
    </button>
  )

  return (
    <div className="co-fmt">
      <span className="co-group-label">{t('co.fmt.title')}</span>
      <div className="co-fmt-row" role="toolbar" aria-label={t('co.fmt.title')}>
        {button(t('co.fmt.italic'), <TextItalic size={16} aria-hidden="true" />, { toggle: 'italic' }, 'i')}
        {button(t('co.fmt.underline'), <TextUnderline size={16} aria-hidden="true" />, { underline: 'single' }, 'u')}
        {button(t('co.fmt.double'), <TextUnderline size={16} weight="bold" aria-hidden="true" />, { underline: 'double' }, 'd')}
        {button(t('co.fmt.strike'), <TextStrikethrough size={16} aria-hidden="true" />, { toggle: 'strike' }, 's')}
        <label className="co-fmt-size">
          <span>{t('co.fmt.size')}</span>
          <input inputMode="decimal" value={size} onChange={(e) => setSize(e.target.value.replace(/[^\d.]/g, '').slice(0, 5))} />
        </label>
        <button type="button" className="co-fmt-btn" onMouseDown={keep} onClick={applySize}>{t('co.fmt.applySize')}</button>
        <button type="button" className="co-fmt-btn" onMouseDown={keep} onClick={() => change({ clear: true })}>{t('co.fmt.clear')}</button>
      </div>
      <span className="co-sub-hint">{t('co.fmt.hint')}</span>
      {note && <span className="co-fmt-note" role="alert">{note}</span>}
      {spans.length > 0 && (
        <div className="co-fmt-list">
          <span className="co-group-label">{t('co.fmt.list')}</span>
          <ul>
            {spans.map((span) => (
              <li key={`${span.start}-${span.end}`}>
                <button type="button" className="co-fmt-part" onClick={() => select(span)}>
                  <span className="co-fmt-words">{words(span)}</span>
                  <span className="co-fmt-tags">
                    {[
                      span.italic && t('co.fmt.italic'),
                      span.underline === 'single' && t('co.fmt.underline'),
                      span.underline === 'double' && t('co.fmt.double'),
                      span.strike && t('co.fmt.strike'),
                      typeof span.size_mm === 'number' && t('co.fmt.sizeMm', { n: span.size_mm }),
                    ].filter(Boolean).join(' · ')}
                  </span>
                </button>
                <button type="button" className="co-fmt-x" aria-label={t('co.fmt.remove')} title={t('co.fmt.remove')}
                  onClick={() => onChange(spans.filter((s) => s !== span))}>
                  <X size={14} aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
          <button type="button" className="vh-link co-fmt-all" onClick={() => onChange([])}>{t('co.fmt.clearAll')}</button>
        </div>
      )}
    </div>
  )
}
