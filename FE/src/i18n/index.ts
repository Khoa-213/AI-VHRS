import { useCallback, useSyncExternalStore } from 'react'
import { en, type Key } from './en'
import { ja } from './ja'
import { vi } from './vi'

export type Lang = 'en' | 'ja' | 'vi'

export const LANGS: { id: Lang; code: string; name: string; locale: string }[] = [
  { id: 'en', code: 'EN', name: 'English', locale: 'en-GB' },
  { id: 'ja', code: 'JA', name: '日本語', locale: 'ja-JP' },
  { id: 'vi', code: 'VI', name: 'Tiếng Việt', locale: 'vi-VN' },
]

const DICT: Record<Lang, Record<string, string>> = { en, ja, vi }
const KEY = 'aivhrs-lang'
const listeners = new Set<() => void>()

function read(): Lang {
  try {
    const v = localStorage.getItem(KEY)
    if (v === 'en' || v === 'ja' || v === 'vi') return v
  } catch {
    // Storage blocked: fall through to the browser language.
  }
  const nav = typeof navigator !== 'undefined' ? navigator.language.slice(0, 2) : 'en'
  return nav === 'ja' || nav === 'vi' ? nav : 'en'
}

let lang: Lang = read()
document.documentElement.lang = lang

export function setLang(next: Lang) {
  lang = next
  document.documentElement.lang = next
  try {
    localStorage.setItem(KEY, next)
  } catch {
    // The choice lasts for this visit only.
  }
  listeners.forEach((l) => l())
}

const subscribe = (cb: () => void) => {
  listeners.add(cb)
  return () => {
    listeners.delete(cb)
  }
}

export const useLang = (): Lang => useSyncExternalStore(subscribe, () => lang)

export type TFn = (key: Key | (string & {}), vars?: Record<string, string | number>) => string

/** Translator for the current language. Unknown keys fall back to English, then to the key itself. */
export function useT(): TFn {
  const l = useLang()
  return useCallback<TFn>(
    (key, vars) => {
      let s = DICT[l][key] ?? DICT.en[key] ?? key
      if (vars) for (const [k, v] of Object.entries(vars)) s = s.split(`{${k}}`).join(String(v))
      return s
    },
    [l],
  )
}

/** BCP 47 locale for dates and numbers in the current language. */
export function useLocale(): string {
  const l = useLang()
  return LANGS.find((x) => x.id === l)!.locale
}

const SEP = /( · | × )/

function translateName(s: string, l: Lang): string {
  if (l === 'en') return s
  const d = DICT[l]
  const whole = d['n.' + s]
  if (whole) return whole
  if (!SEP.test(s)) return s
  return s
    .split(SEP)
    .map((part) => (part === ' · ' || part === ' × ' ? part : (d['n.' + part] ?? part)))
    .join('')
}

/** Translates catalog names (paper, ink, order titles ...). Unknown text is returned as is. */
export function useTn(): (s: string) => string {
  const l = useLang()
  return useCallback((s: string) => translateName(s, l), [l])
}
