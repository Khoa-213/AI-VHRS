import { useEffect, useRef, useState } from 'react'

/** 0..1 progress of a tall section scrolling past a sticky viewport. */
export function useScrollProgress<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [p, setP] = useState(0)

  useEffect(() => {
    let raf = 0
    const update = () => {
      if (raf) return
      raf = requestAnimationFrame(() => {
        raf = 0
        const el = ref.current
        if (!el) return
        const r = el.getBoundingClientRect()
        const total = Math.max(1, r.height - window.innerHeight)
        const next = Math.min(1, Math.max(0, -r.top / total))
        setP((prev) => (Math.abs(next - prev) > 0.003 ? next : prev))
      })
    }
    document.addEventListener('scroll', update, { passive: true, capture: true })
    window.addEventListener('resize', update)
    update()
    return () => {
      cancelAnimationFrame(raf)
      document.removeEventListener('scroll', update, { capture: true })
      window.removeEventListener('resize', update)
    }
  }, [])

  return { ref, p }
}
