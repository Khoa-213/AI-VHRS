// Fails when code asks for a translation key that the English dictionary does not define,
// or when a JSX text node / aria-label / placeholder contains hard-coded English.
// The vi and ja dictionaries are typed against en.ts, so `tsc -b` already enforces parity.
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

const SRC = new URL('../src/', import.meta.url).pathname
const walk = (d) =>
  readdirSync(d).flatMap((f) => {
    const p = join(d, f)
    return statSync(p).isDirectory() ? walk(p) : [p]
  })

const en = readFileSync(join(SRC, 'i18n/en.ts'), 'utf8')
const keys = new Set([...en.matchAll(/^\s+['"]([^'"]+)['"]:/gm)].map((m) => m[1]))

// Text that is allowed to stay as is: brand, product and payment names, sample copy.
const ALLOW = [
  /^AI-VHRS$/, /^make your own style$/, /^(VISA|ATM|PAY|zalo|pay|Pay|VietQR|VNPay|MoMo)$/,
  /^(Vietcombank|CTY AI-VHRS|CVC|MM \/ YY|you@example\.com|Nguyễn Văn A|Phường \/ Xã|0901 234 567)$/,
]

const missing = []
const hardcoded = []
for (const file of walk(SRC)) {
  if (!/\.(ts|tsx)$/.test(file) || file.includes('/i18n/')) continue
  const s = readFileSync(file, 'utf8')
  for (const m of s.matchAll(/\bt\(\s*'([^']+)'/g)) if (!keys.has(m[1])) missing.push(`${file}: ${m[1]}`)
  if (!file.endsWith('.tsx')) continue
  for (const m of s.matchAll(/>([^<>{}\n]*[A-Za-z]{3,}[^<>{}\n]*)</g)) {
    const t = m[1].trim()
    if (t && !ALLOW.some((a) => a.test(t))) hardcoded.push(`${file}: "${t}"`)
  }
  for (const m of s.matchAll(/(?:aria-label|placeholder|title|alt)="([^"{}]*[A-Za-z]{3,}[^"{}]*)"/g)) {
    if (!ALLOW.some((a) => a.test(m[1]))) hardcoded.push(`${file}: ${m[0]}`)
  }
}

for (const l of missing) console.error('missing key   ', l)
for (const l of hardcoded) console.error('hard-coded text', l)
if (missing.length || hardcoded.length) process.exit(1)
console.log(`i18n ok: ${keys.size} keys, no missing keys, no hard-coded UI text`)
