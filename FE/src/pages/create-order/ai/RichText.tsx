import type { ReactNode } from 'react'

/** `**bold**` inside one line. Everything else stays plain text (no HTML is ever injected). */
function inline(line: string): ReactNode[] {
  return line.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith('**') && part.endsWith('**') && part.length > 4 ? <strong key={i}>{part.slice(2, -2)}</strong> : part,
  )
}

const BULLET = /^\s*[-*•]\s+/
const NUMBER = /^\s*\d+[.)]\s+/

/**
 * The assistant's answer, which is written in a small Markdown subset: paragraphs, `- ` / `1. ` lists and `**bold**`.
 * Rendered as React elements, so the text the model wrote can never become markup.
 */
export default function RichText({ text }: { text: string }) {
  const out: ReactNode[] = []
  let list: { ordered: boolean; items: string[] } | null = null
  const flush = () => {
    if (!list) return
    const items = list.items.map((x, i) => <li key={i}>{inline(x)}</li>)
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
    if (raw.trim()) out.push(<p key={out.length}>{inline(raw.trim())}</p>)
  }
  flush()
  return <>{out}</>
}
