import type { ReactNode } from 'react'

/** A fresh answer comes in word by word: the whole text is revealed within this many milliseconds. */
const REVEAL_MS = 1100
const WORD_MS = 28

/** Counts the words as they are wrapped, so each one gets its turn. */
interface Reveal { n: number; step: number }

/** Each word in a span that fades in after the one before it. Spaces stay plain text, so wrapping is unchanged. */
function words(text: string, key: string, r: Reveal): ReactNode[] {
  return text.split(/(\s+)/).map((w, i) =>
    !w || /^\s+$/.test(w) ? w : <span key={`${key}-${i}`} className="oa-w" style={{ animationDelay: `${Math.round(r.n++ * r.step)}ms` }}>{w}</span>,
  )
}

/** `**bold**` inside one line. Everything else stays plain text (no HTML is ever injected). */
function inline(line: string, r: Reveal | null): ReactNode[] {
  return line.split(/(\*\*[^*]+\*\*)/g).map((part, i) => {
    const bold = part.startsWith('**') && part.endsWith('**') && part.length > 4
    const body = bold ? part.slice(2, -2) : part
    const shown = r ? words(body, String(i), r) : body
    return bold ? <strong key={i}>{shown}</strong> : r ? <span key={i}>{shown}</span> : part
  })
}

const BULLET = /^\s*[-*•]\s+/
const NUMBER = /^\s*\d+[.)]\s+/

/**
 * The assistant's answer, which is written in a small Markdown subset: paragraphs, `- ` / `1. ` lists and `**bold**`.
 * Rendered as React elements, so the text the model wrote can never become markup. With `reveal` (the answer that just
 * arrived) the words fade in one after the other.
 */
export default function RichText({ text, reveal = false }: { text: string; reveal?: boolean }) {
  const count = reveal ? text.split(/\s+/).filter(Boolean).length : 0
  const r: Reveal | null = reveal ? { n: 0, step: Math.min(WORD_MS, REVEAL_MS / Math.max(1, count)) } : null
  const out: ReactNode[] = []
  let list: { ordered: boolean; items: string[] } | null = null
  const flush = () => {
    if (!list) return
    const items = list.items.map((x, i) => <li key={i}>{inline(x, r)}</li>)
    out.push(list.ordered ? <ol key={out.length}>{items}</ol> : <ul key={out.length}>{items}</ul>)
    list = null
  }
  for (const raw of text.split('\n')) {
    const ordered = NUMBER.test(raw)
    if (ordered || BULLET.test(raw)) {
      if (list && list.ordered !== ordered) flush()
      list = list ?? { ordered, items: [] }
      list.items.push(raw.replace(ordered ? NUMBER : BULLET, ''))
      continue
    }
    flush()
    if (raw.trim()) out.push(<p key={out.length}>{inline(raw.trim(), r)}</p>)
  }
  flush()
  return <>{out}</>
}
